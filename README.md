# AE Price Tracker

Tracks prices of American Eagle products and notifies you when they drop. Sync your data across devices with Google Sign-In.

## Features
*   **Real-time Tracking**: Scrapes American Eagle product pages for current prices, sale statuses, and stock info.
*   **Price History**: Visualizes price trends over time with interactive charts.
*   **Smart Alerts**: Set target prices and get email notifications when prices drop.
*   **Google Sync**: Sign in to sync your tracked products and alerts across multiple browsers and devices.
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

3.  **Environment Setup**:
    Create a `.env` file from the example:
    ```bash
    cp .env.example .env
    ```
    Set your `SECRET_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET`.

## Running the Application

Start the Flask development server:

```bash
python3 app.py
```

The application will be available at [http://127.0.0.1:5001](http://127.0.0.1:5001).

> **Note**: The app runs on port 5001 by default to avoid conflicts with common MacOS services.

## Usage

1.  **Track a Product**: Copy a URL from `ae.com` and paste it into the search bar. Click "Track Price".
2.  **Google Sign-In**: Click "Sign in with Google" to enable cross-device synchronization and verified email alerts.
3.  **Set Alerts**: Click the bell icon on a product card to set a target price.
4.  **Manage Alerts**: Use the "Unsubscribe" link in the alert modal or your email to remove an alert.

## Configuration

### Google OAuth (Required for Sync)
1.  Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
2.  Create OAuth 2.0 Web Client credentials.
3.  Add `http://localhost:5001/auth/google/callback` (Local) and `https://your-app.railway.app/auth/google/callback` (Production) to Authorized Redirect URis.
4.  Update `.env` or Railway environment variables with your Client ID and Secret.

#### Troubleshooting Redirect URI Mismatch
If you see a `redirect_uri_mismatch` error on Railway:
- **HTTPS**: Ensure your Authorized Redirect URI in Google Console starts with `https://`.
- **Environment**: Set `FLASK_ENV=production` in Railway to enable HTTPS enforcement in the code.
- **Matching**: The domain in Google Console must exactly match your Railway project domain.

### Email Settings
To enable email notifications, set the following in your `.env` or `price_config.json`:
- `SENDER_EMAIL`
- `SENDER_PASSWORD`
- `SMTP_SERVER` (default: smtp.gmail.com)
- `SMTP_PORT` (default: 587)

## Database Schema
The application uses a scalable database structure:
1.  **Users Table**: Stores synced account data from Google.
2.  **Products Table**: Stores unique product data and price history.
3.  **User-Product Association**: Links users to their tracked dashboard items.
4.  **Price Alerts**: Tracks target prices and unsubscription tokens.

## Testing
Verify the logic with the included test suites:
```bash
# Test scraper logic
python3 test_scraper_logic.py

# Test full application flow
python3 test_app_flow.py
```

## Project Structure
*   `app.py`: Main Flask application and API routes.
*   `models.py`: Database models (User, Product, PriceHistory, PriceAlert).
*   `scraper.py`: Logic for extracting data from AE websites.
*   `scheduler.py`: Background job for daily price checks (9:00 AM).
*   `emailer.py`: Handles sending email notifications.
*   `static/`: CSS and JavaScript.
*   `templates/`: HTML templates.
