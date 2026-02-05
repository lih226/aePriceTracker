from app import app
from models import db, Product
from scraper import fetch_product_data
from datetime import datetime, timezone

def refresh_all():
    with app.app_context():
        products = Product.query.all()
        print(f"Refreshing {len(products)} products...")
        for p in products:
            print(f"Checking {p.name}...")
            data = fetch_product_data(p.url)
            if data:
                # Update is_available and last_checked regardless of price
                p.is_available = data.get('is_available', True)
                p.last_checked = datetime.now(timezone.utc)
                
                if data.get('current_price'):
                    p.current_price = data['current_price']
                    p.list_price = data.get('list_price') or data['current_price']
                    print(f"  Updated: ${p.current_price} (List: ${p.list_price}, Available: {p.is_available})")
                else:
                    print(f"  Updated status (Available: {p.is_available}), but no price found.")
        db.session.commit()
        print("Done!")

if __name__ == '__main__':
    refresh_all()
