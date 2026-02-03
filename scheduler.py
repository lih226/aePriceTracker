# Background Scheduler for Price Checks
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone


scheduler = BackgroundScheduler()
_scheduler_initialized = False


def update_all_prices(app):
    """Check all tracked products and update prices"""
    from models import db, Product, PriceHistory, PriceAlert
    from scraper import fetch_product_data
    from emailer import send_price_alert
    
    with app.app_context():
        print(f"\n[{datetime.now()}] Running scheduled price check...")
        
        products = Product.query.all()
        
        for product in products:
            try:
                print(f"  Checking: {product.name}...")
                data = fetch_product_data(product.url)
                
                if data and data.get('price'):
                    current_price = data['price']
                    
                    # Add to price history if price changed
                    if current_price != product.current_price:
                        price_entry = PriceHistory(
                            product_id=product.id,
                            price=current_price
                        )
                        db.session.add(price_entry)
                        print(f"    Price changed: ${product.current_price} → ${current_price}")
                    
                    # Update product
                    product.current_price = current_price
                    product.last_checked = datetime.now(timezone.utc)
                    
                    # Check alerts
                    active_alerts = PriceAlert.query.filter_by(
                        product_id=product.id,
                        triggered=False
                    ).all()
                    
                    for alert in active_alerts:
                        if current_price <= alert.target_price:
                            # Ensure alert has a token
                            if not alert.token:
                                import uuid
                                alert.token = str(uuid.uuid4())
                                
                            # Alert triggered!
                            send_price_alert(
                                recipient_email=alert.email,
                                product_name=product.name,
                                product_url=product.url,
                                target_price=alert.target_price,
                                current_price=current_price,
                                token=alert.token
                            )
                            alert.triggered = True
                            alert.triggered_at = datetime.now(timezone.utc)
                            print(f"    Alert triggered for {alert.email} (target: ${alert.target_price})")
                
                else:
                    print(f"    Could not fetch price for {product.name}")
                    
            except Exception as e:
                print(f"    Error checking {product.name}: {str(e)}")
        
        db.session.commit()
        print(f"[{datetime.now()}] Price check complete.\n")


def init_scheduler(app):
    """Initialize the scheduler with daily price checks"""
    global _scheduler_initialized
    if _scheduler_initialized:
        return  # Already initialized
    
    # Run every day at 9:00 AM
    scheduler.add_job(
        func=lambda: update_all_prices(app),
        trigger='cron',
        hour=9,
        minute=0,
        id='daily_price_check',
        replace_existing=True
    )
    
    scheduler.start()
    _scheduler_initialized = True
    print("Background scheduler started - checking prices daily at 9:00 AM")


def shutdown_scheduler():
    """Shutdown the scheduler gracefully"""
    if scheduler.running:
        scheduler.shutdown()
