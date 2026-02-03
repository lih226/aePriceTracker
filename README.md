# AE Price Tracker

Tracks prices of American Eagle products and notifies you when they drop.

## Features
*   **Real-time Tracking**: Scrapes American Eagle product pages for current prices, sale statuses, and stock info.
*   **Price History**: Visualizes price trends over time with interactive charts.
*   **Smart Alerts**: Set target prices and get email notifications when prices drop.
*   **Sale Detection**: Automatically detects sale items, calculates discount percentages, and displays original list prices.
*   **Responsive UI**: Modern, glassmorphism-inspired interface that works great on desktop and mobile.

## Prerequisites
*   Python 3.8+
*   Pip (Python package manager)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/yourusername/aePriceTracker.git
    cd aePriceTracker
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the Application

Start the Flask development server:

```bash
python app.py
```

The application will be available at [http://127.0.0.1:5001](http://127.0.0.1:5001).

> **Note**: The app runs on port 5001 to avoid conflicts with MacOS AirPlay Receiver updates.
> **Note**: Stop and re-run the server using:
  ```bash
  lsof -i :5001 -t | xargs kill -9 && python app.py
  ```

## Usage

1.  **Track a Product**: Copy a URL from `ae.com` and paste it into the search bar. Click "Track Price".
2.  **View Details**: Click on any tracked product to view its price history chart and detailed info.
3.  **Set Alerts**: Click the bell icon on a product card to set a target price and your email. You'll be notified when the price hits your target.
4.  **Delete**: Click the trash icon to stop tracking a product.

## Testing & Verification

### Running Tests
To verify the scraper logic against sample HTML files:

```bash
python test_scraper_logic.py
```

To run the **full application integration tests** (testing tracking, alerts, and database operations):

```bash
python test_app_flow.py
```

### Checking the Database
You can inspect the database directly using `sqlite3` or Python.

**1. Inspecting Tracked Items (Command Line):**

```bash
# Check all tracked products
sqlite3 instance/price_tracker.db "SELECT id, name, current_price, list_price FROM products;"
```

**2. Inspecting Alerts:**

```bash
# Check active alerts
sqlite3 instance/price_tracker.db "SELECT id, product_id, email, target_price, triggered FROM price_alerts;"
```

**3. Deleting Items (Command Line):**

```bash
# Delete a product by ID (e.g., ID 12)
sqlite3 instance/price_tracker.db "DELETE FROM products WHERE id = 12;"

# Delete an alert by ID (e.g., ID 4)
sqlite3 instance/price_tracker.db "DELETE FROM price_alerts WHERE id = 4;"

# Manually update a price (to test UI or simulate data)
sqlite3 instance/price_tracker.db "UPDATE products SET current_price = 15.00 WHERE id = 12;"
```

**4. Using Python Shell:**
You can also interact with the database using the Flask shell:

```bash
python3
>>> from app import app, db
>>> from models import Product, PriceAlert
>>> 
>>> with app.app_context():
...     # List all products
...     products = Product.query.all()
...     for p in products:
...         print(f"{p.id}: {p.name} - ${p.current_price}")
...
...     # Check alerts
...     alerts = PriceAlert.query.all()
...     print(f"Total alerts: {len(alerts)}")
```

## Configuration

### Email Settings
To enable email notifications, create a `price_config.json` file in the root directory (or use environment variables):

```json
{
    "email": {
        "sender": "your_email@gmail.com",
        "password": "your_app_password",
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587
    }
}
```

> **Security Note**: Never commit `price_config.json` to version control.

## Database Schema & Scalability
The application uses a scalable SQLite database designed for future multi-user synchronization:

1.  **Users Table**: Stores account credentials (ready for login implementation).
2.  **Products Table**: Stores unique product data (URL, price history) shared across all users.
3.  **User-Product Association**: A "Many-to-Many" link allowing multiple users to track the same product on their personal dashboards.
4.  **Flexible Alerts**: Price alerts can be linked to specific user accounts or remain anonymous (email-only) for guest usage.

This structure allows the app to scale from a single-device tracker to a cloud-synced service where users can view their tracked items across mobile and desktop.

## Project Structure
*   `app.py`: Main Flask application and API routes.
*   `models.py`: Database models (User, Product, PriceHistory, PriceAlert).
*   `scraper.py`: Logic for extracting data from AE websites.
*   `scheduler.py`: Background job to check prices periodically.
*   `emailer.py`: Handles sending email notifications.
*   `static/`: CSS, JavaScript, and assets.
*   `templates/`: HTML templates.
