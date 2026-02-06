# AE Price Tracker - Flask Web Application
from flask import Flask, render_template, request, jsonify, abort, redirect, url_for
from flask_login import LoginManager, login_user, logout_user, current_user, login_required
from authlib.integrations.flask_client import OAuth
from models import db, Product, PriceHistory, PriceAlert, User
from scraper import fetch_product_data
from scheduler import init_scheduler, shutdown_scheduler
from emailer import send_alert_confirmation, send_price_alert
from datetime import datetime, timezone
import os
import atexit
import uuid
import threading
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

# Security settings for production
if os.environ.get('FLASK_ENV') == 'production':
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    # Trust Railway's reverse proxy for HTTPS detection
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Initialize database
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login_prompt'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Initialize OAuth
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# Initialize scheduler
init_scheduler(app)
atexit.register(shutdown_scheduler)

def init_db():
    """Initialize database with necessary configuration"""
    # SQLite-specific pragma (only for local dev)
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        with app.app_context():
            @db.event.listens_for(db.engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    # Auto-migrate: Add missing columns if they don't exist
    with app.app_context():
        try:
            from sqlalchemy import text, inspect
            inspector = inspect(db.engine)
            
            # Check products table
            columns = [c['name'] for c in inspector.get_columns('products')]
            if 'is_available' not in columns:
                print("Auto-migrating: Adding is_available column to products table...")
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE products ADD COLUMN is_available BOOLEAN DEFAULT 1"))
                print("is_available migration successful.")
            
            # Check price_alerts table
            columns = [c['name'] for c in inspector.get_columns('price_alerts')]
            if 'token' not in columns:
                print("Auto-migrating: Adding token column to price_alerts table...")
                with db.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE price_alerts ADD COLUMN token VARCHAR(100)"))
                print("token migration successful.")
                
        except Exception as e:
            print(f"Auto-migration warning (this may be normal if columns exist): {e}")

    with app.app_context():
        db.create_all()

# Ensure database is initialized on startup (all environments)
init_db()

# ============ Page Routes ============

@app.route('/')
def index():
    """Main page"""
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('index.html', products=products, user=current_user)


# ============ Auth Routes ============

@app.route('/auth/google/login')
def google_login():
    """Redirect to Google OAuth"""
    redirect_uri = url_for('google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth/google/callback')
def google_callback():
    """Handle Google OAuth callback"""
    try:
        token = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            return redirect(url_for('index'))
        
        # Find existing user by google_id or email
        user = User.query.filter(
            (User.google_id == user_info['sub']) | 
            (User.email == user_info['email'])
        ).first()
        
        if user:
            # Update existing user with Google info
            user.google_id = user_info['sub']
            user.name = user_info.get('name')
            user.picture = user_info.get('picture')
        else:
            # Create new user
            user = User(
                google_id=user_info['sub'],
                email=user_info['email'],
                name=user_info.get('name'),
                picture=user_info.get('picture')
            )
            db.session.add(user)
        
        db.session.commit()
        login_user(user)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"OAuth error: {e}")
        return redirect(url_for('index'))


@app.route('/auth/logout')
def logout():
    """Log out current user"""
    logout_user()
    return redirect(url_for('index'))


@app.route('/login-prompt')
def login_prompt():
    """Show login prompt when authentication is required"""
    return redirect(url_for('index'))


@app.route('/api/user')
def get_current_user():
    """Get current logged-in user info"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': current_user.to_dict()
        })
    return jsonify({'authenticated': False})


@app.route('/api/user/products')
def get_user_products():
    """Get products tracked by the logged-in user"""
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not authenticated'}), 401
    
    # Get all products this user is tracking
    products = current_user.tracked_products
    return jsonify([p.to_dict() for p in products])


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
    
    # Check if already tracking this product globally
    existing = Product.query.filter_by(url=url).first()
    
    if existing:
        # If user is logged in, associate the existing product with them
        if current_user.is_authenticated:
            if existing not in current_user.tracked_products:
                current_user.tracked_products.append(existing)
                db.session.commit()
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
            image_url=product_data.get('image_url'),
            is_available=product_data.get('is_available', True)
        )
        db.session.add(product)
        db.session.flush()  # Get the ID
        
        # Associate with logged-in user
        if current_user.is_authenticated:
            current_user.tracked_products.append(product)
        
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
    target_price = data.get('target_price')
    
    # For logged-in users, use their verified email
    if current_user.is_authenticated:
        email = current_user.email
        user_id = current_user.id
    else:
        email = data.get('email', '').strip()
        user_id = None
    
    if not all([product_id, email, target_price]):
        return jsonify({'error': 'product_id, email, and target_price are required'}), 400
    
    try:
        try:
            target_price = float(target_price)
        except ValueError:
            return jsonify({'error': 'Invalid target price'}), 400
            
        product = db.session.get(Product, product_id)
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        # Check if alert already exists (match by email or user_id)
        if user_id:
            existing = PriceAlert.query.filter_by(
                product_id=product_id,
                user_id=user_id,
                triggered=False
            ).first()
        else:
            existing = PriceAlert.query.filter_by(
                product_id=product_id,
                email=email,
                triggered=False
            ).first()
        
        if existing:
            # Update existing alert
            existing.target_price = target_price
            existing.user_id = user_id  # Update user_id if they logged in
            
            # Ensure it has a token for unsubscription
            if not existing.token:
                existing.token = str(uuid.uuid4())
                
            db.session.commit()
            
            # Send confirmation for update
            # Send confirmation in background thread to prevent UI hangs
            threading.Thread(
                target=send_alert_confirmation, 
                args=(email, product.name, product.url, target_price, existing.token)
            ).start()
            
            return jsonify({
                'message': 'Alert updated successfully',
                'alert': existing.to_dict()
            })
        
        # Create new alert with secure token
        alert = PriceAlert(
            product_id=product_id,
            email=email,
            user_id=user_id,
            target_price=target_price,
            token=str(uuid.uuid4())
        )
        db.session.add(alert)
        db.session.commit()
        
        # Send confirmation for new alert
        # Send confirmation in background thread to prevent UI hangs
        threading.Thread(
            target=send_alert_confirmation, 
            args=(email, product.name, product.url, target_price, alert.token)
        ).start()
        
        return jsonify({
            'message': 'Alert created successfully',
            'alert': alert.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        print(f"Alert creation error: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500


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
    if not product_data:
        return jsonify({'error': 'Could not fetch product data'}), 400
    
    # Allow refresh even if price is missing (e.g. out of stock)
    current_price = product_data.get('current_price')
    list_price = product_data.get('list_price')
    is_available = product_data.get('is_available', True)
    
    # Update is_available
    product.is_available = is_available
    
    # Add to history if price changed and exists
    if current_price is not None and current_price != product.current_price:
        price_entry = PriceHistory(
            product_id=product.id,
            price=current_price
        )
        db.session.add(price_entry)
        product.current_price = current_price
    if list_price is not None:
        product.list_price = list_price
    product.last_checked = datetime.now(timezone.utc)
    
    # Check if any alerts should be triggered

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

    print("\n" + "="*50)
    print("  AE Price Tracker - Web Application")
    print("  Running at: http://127.0.0.1:5001")
    print("="*50 + "\n")
    
    # Enable reloader for better dev experience
    app.run(debug=True, use_reloader=True, port=5001)
