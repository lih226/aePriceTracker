import unittest
import json
from unittest.mock import patch
import os

# Set test environment to avoid scheduler starting
# Set test environment to avoid scheduler starting
os.environ['WERKZEUG_RUN_MAIN'] = 'true'
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import app, db
from models import Product, PriceAlert, PriceHistory, User, user_products
import flask_login

class TestAEPriceTracker(unittest.TestCase):
    def setUp(self):
        """Set up test client and in-memory database"""
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        # Create a test client
        self.client = app.test_client()
        
        # Create database tables
        with app.app_context():
            db.create_all()

    def tearDown(self):
        """Clean up database after tests"""
        with app.app_context():
            db.session.remove()
            db.drop_all()

    @patch('app.fetch_product_data')
    def test_track_product_success(self, mock_fetch):
        """Test successfully tracking a new product"""
        print("\n[TEST] Tracking a new product...")
        # Mock scraper response
        mock_fetch.return_value = {
            'name': 'Test Hoodie',
            'current_price': 49.95,
            'list_price': 59.95,
            'image_url': 'http://example.com/image.jpg'
        }
        
        payload = {
            'url': 'https://www.ae.com/us/en/p/test-hoodie'
        }
        
        response = self.client.post('/api/track', 
                                  data=json.dumps(payload),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['message'], 'Product added successfully')
        self.assertEqual(data['product']['name'], 'Test Hoodie')
        
        # Verify db persistence
        with app.app_context():
            product = db.session.query(Product).first()
            self.assertIsNotNone(product)
            self.assertEqual(product.name, 'Test Hoodie')
        print("  -> Success: Product added to database correctly.")

    @patch('app.fetch_product_data')
    def test_track_product_duplicate(self, mock_fetch):
        """Test tracking a duplicate product"""
        print("\n[TEST] Handling duplicate product submission...")
        # Setup initial product
        with app.app_context():
            p = Product(url='https://www.ae.com/us/en/p/test', name='Existing', current_price=10.0)
            db.session.add(p)
            db.session.commit()

        response = self.client.post('/api/track', 
                                  data=json.dumps({'url': 'https://www.ae.com/us/en/p/test'}),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['message'], 'Product already tracked')
        print("  -> Success: Duplicate product correctly identified.")

    @patch('app.fetch_product_data')
    @patch('app.send_alert_confirmation')
    def test_create_alert(self, mock_email, mock_fetch):
        """Test creating a price alert"""
        print("\n[TEST] Creating a price alert...")
        # Setup product
        with app.app_context():
            p = Product(url='https://www.ae.com/us/en/p/test', name='Test Item', current_price=50.0)
            db.session.add(p)
            db.session.commit()
            product_id = p.id

        payload = {
            'product_id': product_id,
            'email': 'test@example.com',
            'target_price': 45.00
        }
        
        response = self.client.post('/api/alert', 
                                  data=json.dumps(payload),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['message'], 'Alert created successfully')
        
        # Verify tokens are generated
        self.assertIsNotNone(data['alert']['token'])
        
        # Check DB
        with app.app_context():
            alert = PriceAlert.query.filter_by(email='test@example.com').first()
            self.assertIsNotNone(alert)
            self.assertEqual(alert.target_price, 45.00)
        print("  -> Success: Alert created in DB with unsubscribe token.")

    @patch('app.send_alert_confirmation') 
    def test_unsubscribe(self, mock_email):
        """Test unsubscribing from alerts"""
        print("\n[TEST] Unsubscribing via token...")
        # Setup alert with a known token
        token = "unique-test-token"
        with app.app_context():
            p = Product(url='http://test', name='Test', current_price=10)
            db.session.add(p)
            db.session.commit()
            
            a = PriceAlert(product_id=p.id, email='test@test.com', target_price=5, token=token)
            db.session.add(a)
            db.session.commit()

        # Call unsubscribe endpoint
        response = self.client.get(f'/unsubscribe/{token}')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Successfully Unsubscribed', response.data)
        
        # Verify db deletion
        with app.app_context():
            alert = PriceAlert.query.filter_by(token=token).first()
            self.assertIsNone(alert)
        print("  -> Success: Alert removed from database.")

    def test_delete_product(self):
        """Test deleting a product"""
        print("\n[TEST] Deleting product and checking cascading deletion...")
        with app.app_context():
            p = Product(url='http://test', name='Delete Me', current_price=10)
            db.session.add(p)
            db.session.commit()
            pid = p.id
            
            # Add an alert too, to test cascade
            a = PriceAlert(product_id=pid, email='test@test.com', target_price=5)
            db.session.add(a)
            db.session.commit()

        response = self.client.delete(f'/api/product/{pid}')
        self.assertEqual(response.status_code, 200)
        
        # Verify product is gone
        with app.app_context():
            p = db.session.get(Product, pid)
            self.assertIsNone(p)
            
            # Verify alert is gone (cascade delete)
            alerts = PriceAlert.query.filter_by(product_id=pid).all()
            self.assertEqual(len(alerts), 0)
        print("  -> Success: Product and its alerts deleted successfully.")

    @patch('app.fetch_product_data')
    @patch('app.send_price_alert')
    def test_price_refresh_trigger_alert(self, mock_send_email, mock_fetch):
        """Test refreshing a product triggers an alert if price drops"""
        print("\n[TEST] Refreshing price and triggering alert logic...")
        with app.app_context():
            p = Product(url='http://test', name='Refresher', current_price=100.0)
            db.session.add(p)
            db.session.commit()
            pid = p.id
            
            # Add alert for $60
            a = PriceAlert(product_id=pid, email='alert@test.com', target_price=60.0, token='xyz')
            db.session.add(a)
            db.session.commit()

        # Mock price dropping to $50
        mock_fetch.return_value = {
            'name': 'Refresher',
            'current_price': 50.0,
            'list_price': 100.0,
            'image_url': 'img.jpg'
        }
        
        response = self.client.post(f'/api/refresh/{pid}')
        self.assertEqual(response.status_code, 200)
        
        # Check if email mock was called
        mock_send_email.assert_called_once()
        
        # Check DB updated
        with app.app_context():
            p = db.session.get(Product, pid)
            self.assertEqual(p.current_price, 50.0)
            
            a = PriceAlert.query.filter_by(email='alert@test.com').first()
            self.assertTrue(a.triggered)
        print("  -> Success: Price updated and alert triggered.")

    def test_track_product_invalid_input(self):
        """Test tracking with missing or invalid data"""
        print("\n[TEST] Testing invalid input handling...")
        
        # 1. Missing URL
        response = self.client.post('/api/track', 
                                  data=json.dumps({}),
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'URL is required', response.data)
        
        # 2. Invalid Target Price for Alert
        response = self.client.post('/api/alert', 
                                  data=json.dumps({
                                      'product_id': 1,
                                      'email': 'test@test.com',
                                      'target_price': 'not-a-number'
                                  }),
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)
        print("  -> Success: Invalid inputs correctly rejected.")

    @patch('app.fetch_product_data')
    def test_price_history_logic(self, mock_fetch):
        """Test proper recording of price history timestamps"""
        print("\n[TEST] Verifying price history logic...")
        with app.app_context():
            p = Product(url='http://history-test', name='History Item', current_price=100.0)
            db.session.add(p)
            db.session.commit()
            pid = p.id
            
            # Initial history
            ph = PriceHistory(product_id=pid, price=100.0)
            db.session.add(ph)
            db.session.commit()

        # 1. Refresh with SAME price (should NOT add history)
        mock_fetch.return_value = {
            'name': 'History Item', 'current_price': 100.0, 'list_price': 100.0, 'image_url': 'img.jpg'
        }
        self.client.post(f'/api/refresh/{pid}')
        
        with app.app_context():
            history_count = PriceHistory.query.filter_by(product_id=pid).count()
            self.assertEqual(history_count, 1) # Still just the initial one

        # 2. Refresh with NEW price (SHOULD add history)
        mock_fetch.return_value = {
            'name': 'History Item', 'current_price': 90.0, 'list_price': 100.0, 'image_url': 'img.jpg'
        }
        self.client.post(f'/api/refresh/{pid}')
        
        with app.app_context():
            history_count = PriceHistory.query.filter_by(product_id=pid).count()
            self.assertEqual(history_count, 2)
            latest = PriceHistory.query.filter_by(product_id=pid).order_by(PriceHistory.timestamp.desc()).first()
            self.assertEqual(latest.price, 90.0)
        print("  -> Success: Price history recorded only when price actually changes.")

    def test_api_endpoints(self):
        """Test GET endpoints for product lists and details"""
        print("\n[TEST] Verifying API list and detail endpoints...")
        with app.app_context():
            p1 = Product(url='http://1', name='Item 1', current_price=10)
            p2 = Product(url='http://2', name='Item 2', current_price=20)
            db.session.add_all([p1, p2])
            db.session.commit()
            pid = p1.id

        # Test List
        response = self.client.get('/api/products')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(len(data) >= 2)
        
        # Test Detail
        response = self.client.get(f'/api/product/{pid}')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['name'], 'Item 1')
        print("  -> Success: API endpoints return correct JSON structures.")

    @patch('app.fetch_product_data')
    def test_stateless_scrape(self, mock_fetch):
        """Test the stateless /api/scrape endpoint"""
        print("\n[TEST] Verifying stateless scrape endpoint...")
        
        # Mock successful scrape
        mock_fetch.return_value = {
            'name': 'Stateless Hoodie',
            'current_price': 29.99,
            'list_price': 49.99,
            'image_url': 'http://stateless.com/img.jpg'
        }

        # Send request
        payload = {'url': 'https://www.ae.com/us/en/p/stateless-hoodie'}
        response = self.client.post('/api/scrape', 
                                  data=json.dumps(payload),
                                  content_type='application/json')

        # Assertions
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        
        # Check response structure
        self.assertEqual(data['name'], 'Stateless Hoodie')
        self.assertEqual(data['current_price'], 29.99)
        
        # KEY ASSERTION: Ensure NOTHING was saved to DB
        with app.app_context():
            count = Product.query.filter_by(name='Stateless Hoodie').count()
            self.assertEqual(count, 0, "Stateless scrape should NOT save to DB")
            
        print("  -> Success: Scrape returned data and DB remains empty.")

    @patch('authlib.integrations.flask_client.FlaskOAuth2App.authorize_access_token')
    def test_google_login_new_user(self, mock_token):
        """Test Google login flow for a new user"""
        print("\n[TEST] Verifying Google OAuth login (new user)...")
        # Mock Google OAuth response
        mock_token.return_value = {
            'userinfo': {
                'sub': 'google-123',
                'email': 'newuser@gmail.com',
                'name': 'New User',
                'picture': 'http://avatar.com/p.jpg'
            }
        }

        # Simulate callback
        response = self.client.get('/auth/google/callback', follow_redirects=True)
        self.assertEqual(response.status_code, 200)

        # Verify DB entry
        with app.app_context():
            user = User.query.filter_by(google_id='google-123').first()
            self.assertIsNotNone(user)
            self.assertEqual(user.email, 'newuser@gmail.com')
        print("  -> Success: New user created from OAuth data.")

    def test_user_product_sync(self):
        """Test that products tracked by user are correctly synced/retrieved"""
        print("\n[TEST] Verifying user-specific product sync...")
        with app.app_context():
            # Create user
            u = User(email='sync@test.com', name='Sync User')
            db.session.add(u)
            
            # Create product
            p = Product(url='http://sync-test', name='Synced Product', current_price=10)
            db.session.add(p)
            db.session.commit()
            
            # Manually associate
            u.tracked_products.append(p)
            db.session.commit()
            uid = u.id

        # Simulate login by setting session manually in test
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(uid)
            sess['_fresh'] = True

        # Fetch user products
        response = self.client.get('/api/user/products')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data[0]['name'], 'Synced Product')
        print("  -> Success: Logged-in user correctly retrieves their synced products.")

    def test_authenticated_alert_flow(self):
        """Test that alert creation for logged-in users uses their email automatically"""
        print("\n[TEST] Verifying authenticated alert creation...")
        with app.app_context():
            u = User(email='auth@test.com', name='Auth User')
            db.session.add(u)
            p = Product(url='http://auth-test', name='Auth Product', current_price=10)
            db.session.add(p)
            db.session.commit()
            uid = u.id
            pid = p.id

        # Login
        with self.client.session_transaction() as sess:
            sess['_user_id'] = str(uid)

        # Create alert (don't provide email in payload)
        payload = {
            'product_id': pid,
            'target_price': 5.0
        }
        # Note: app.py create_alert handles missing email for auth'd users
        
        response = self.client.post('/api/alert', 
                                  data=json.dumps(payload),
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data['alert']['email'], 'auth@test.com')
        self.assertEqual(data['alert']['user_id'], uid)
        print("  -> Success: Authenticated alert correctly linked to user account and email.")


if __name__ == '__main__':
    unittest.main()
