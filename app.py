# AE Price Tracker - Flask Web Application
from flask import Flask, render_template, request, jsonify, abort
from models import db, Product, PriceHistory, PriceAlert
from scraper import fetch_product_data
from scheduler import init_scheduler, shutdown_scheduler
from datetime import datetime, timezone
import atexit
import uuid

import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Database configuration - Railway uses postgres://, SQLAlchemy needs postgresql://
database_url = os.environ.get('DATABASE_URL', 'sqlite:///price_tracker.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-please-change')

# Initialize database
db.init_app(app)

# Initialize scheduler for both development and production
init_scheduler(app)
atexit.register(shutdown_scheduler)

def init_db():
    """Initialize database with necessary configuration"""
    with app.app_context():
        # SQLite-specific pragma (only for local dev)
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            @db.event.listens_for(db.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        db.create_all()


# ============ Page Routes ============

@app.route('/')
def index():
    """Main page"""
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('index.html', products=products)


# ============ API Routes ============


@app.route('/api/scrape', methods=['POST'])
def scrape_product_data():
    """Stateless endpoint to fetch product data without saving"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
        
    product_data = fetch_product_data(url)
    if not product_data:
        return jsonify({'error': 'Could not fetch product data'}), 400
        
    return jsonify(product_data)


@app.route('/api/track', methods=['POST'])
def track_product():
    """Add a new product to track"""
    data = request.get_json()
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    # Check if already tracking
    existing = Product.query.filter_by(url=url).first()
    if existing:
        return jsonify({
            'message': 'Product already tracked',
            'product': existing.to_dict()
        })
    
    # Fetch product data
    product_data = fetch_product_data(url)
    if not product_data:
        return jsonify({'error': 'Could not fetch product data. Please check the URL.'}), 400
    
    # Validate product data
    if not product_data.get('name'):
        return jsonify({'error': 'Could not extract product name'}), 400

    try:
        # Create product
        current_price = product_data.get('current_price')
        list_price = product_data.get('list_price')
        
        product = Product(
            url=url,
            name=product_data['name'],
            current_price=current_price,
            list_price=list_price,
            image_url=product_data.get('image_url')
        )
        db.session.add(product)
        db.session.flush()  # Get the ID
        
        # Add initial price to history
        if current_price:
            price_entry = PriceHistory(
                product_id=product.id,
                price=current_price
            )
            db.session.add(price_entry)
        
        db.session.commit()

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    
    return jsonify({
        'message': 'Product added successfully',
        'product': product.to_dict()
    })


@app.route('/api/product/<int:product_id>')
def get_product(product_id):
    """Get product details with price history"""
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    return jsonify(product.to_dict())


@app.route('/api/products')
def list_products():
    """List all tracked products"""
    products = Product.query.order_by(Product.created_at.desc()).all()
    return jsonify([p.to_dict() for p in products])


@app.route('/api/alert', methods=['POST'])
def create_alert():
    """Create a price alert for a product"""
    data = request.get_json()
    
    product_id = data.get('product_id')
    email = data.get('email', '').strip()
    target_price = data.get('target_price')
    
    if not all([product_id, email, target_price]):
        return jsonify({'error': 'product_id, email, and target_price are required'}), 400
    
    try:
        target_price = float(target_price)
    except ValueError:
        return jsonify({'error': 'Invalid target price'}), 400
    
    from emailer import send_alert_confirmation
    
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    
    # Check if alert already exists
    existing = PriceAlert.query.filter_by(
        product_id=product_id,
        email=email,
        triggered=False
    ).first()
    
    if existing:
        # Update existing alert
        existing.target_price = target_price
        
        # Ensure it has a token for unsubscription
        if not existing.token:
            existing.token = str(uuid.uuid4())
            
        db.session.commit()
        
        # Send confirmation for update
        send_alert_confirmation(email, product.name, product.url, target_price, existing.token)
        
        return jsonify({
            'message': 'Alert updated successfully',
            'alert': existing.to_dict()
        })
    
    # Create new alert with secure token
    alert = PriceAlert(
        product_id=product_id,
        email=email,
        target_price=target_price,
        token=str(uuid.uuid4())
    )
    db.session.add(alert)
    db.session.commit()
    
    # Send confirmation for new alert
    send_alert_confirmation(email, product.name, product.url, target_price, alert.token)
    
    return jsonify({
        'message': 'Alert created successfully',
        'alert': alert.to_dict()
    })


@app.route('/api/product/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    """Delete a product and its history"""
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    
    # Delete related data
    PriceHistory.query.filter_by(product_id=product_id).delete()
    PriceAlert.query.filter_by(product_id=product_id).delete()
    db.session.delete(product)
    db.session.commit()
    
    return jsonify({'message': 'Product deleted successfully'})


@app.route('/api/refresh/<int:product_id>', methods=['POST'])
def refresh_product(product_id):
    """Manually refresh a product's price"""
    product = db.session.get(Product, product_id)
    if not product:
        abort(404)
    
    product_data = fetch_product_data(product.url)
    if not product_data or product_data.get('current_price') is None:
        return jsonify({'error': 'Could not fetch current price'}), 400
    
    current_price = product_data['current_price']
    list_price = product_data.get('list_price')
    
    # Add to history if price changed
    if current_price != product.current_price:
        price_entry = PriceHistory(
            product_id=product.id,
            price=current_price
        )
        db.session.add(price_entry)
    
    product.current_price = current_price
    product.list_price = list_price
    product.last_checked = datetime.now(timezone.utc)
    
    # Check if any alerts should be triggered
    from emailer import send_price_alert
    active_alerts = PriceAlert.query.filter_by(
        product_id=product.id,
        triggered=False
    ).all()
    
    for alert in active_alerts:
        if current_price <= alert.target_price:
            # Ensure alert has a token
            if not alert.token:
                alert.token = str(uuid.uuid4())
                
            send_price_alert(
                recipient_email=alert.email,
                product_name=product.name,
                product_url=product.url,
                target_price=alert.target_price,
                current_price=current_price,
                list_price=product.list_price,
                token=alert.token
            )
            alert.triggered = True
            alert.triggered_at = datetime.now(timezone.utc)

    db.session.commit()
    
    return jsonify({
        'message': 'Price updated',
        'product': product.to_dict()
    })


@app.route('/unsubscribe/<string:token>', methods=['GET'])
def unsubscribe(token):
    """Remove a price alert using its unique token"""
    alert = PriceAlert.query.filter_by(token=token).first()
    
    if not alert:
        return render_template('unsubscribe.html', success=False, message="Invalid or expired unsubscribe link.")
    
    # Get product info before deleting for the confirmation message
    product_name = alert.product.name
    
    db.session.delete(alert)
    db.session.commit()
    
    return render_template('unsubscribe.html', success=True, product_name=product_name)


@app.route('/api/scheduler-status')
def scheduler_status():
    """Check if the scheduler is running and show next run times"""
    from scheduler import scheduler
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            'id': job.id,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
            'trigger': str(job.trigger)
        })
    
    return jsonify({
        'scheduler_running': scheduler.running,
        'jobs': jobs
    })


@app.route('/api/test-scheduler', methods=['POST'])
def test_scheduler():
    """Manually trigger the price checking routine for testing"""
    from scheduler import update_all_prices
    
    try:
        update_all_prices(app)
        return jsonify({'message': 'Price check completed successfully'})
    except Exception as e:
        return jsonify({'error': f'Price check failed: {str(e)}'}), 500

# ============ Run App ============

if __name__ == '__main__':
    import os
    
    # Initialize database only in development
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        init_db()
    
    print("\n" + "="*50)
    print("  AE Price Tracker - Web Application")
    print("  Running at: http://127.0.0.1:5001")
    print("="*50 + "\n")
    
    # Enable reloader for better dev experience
    app.run(debug=True, use_reloader=True, port=5001)
