# Email Notification Service
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os

import json

# Email configuration - fetched from price_config.json or environment variables
def get_config():
    # Default values
    config = {
        'server': os.environ.get('SMTP_SERVER', 'smtp.gmail.com'),
        'port': int(os.environ.get('SMTP_PORT', 587)),
        'email': os.environ.get('SENDER_EMAIL', ''),
        'password': os.environ.get('SENDER_PASSWORD', ''),
        'base_url': os.environ.get('BASE_URL', os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'http://127.0.0.1:5001'))
    }
    
    # Try to load from price_config.json
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'price_config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                data = json.load(f)
                email_data = data.get('email', {})
                if email_data.get('sender'):
                    config['email'] = email_data['sender']
                if email_data.get('password'):
                    config['password'] = email_data['password']
                # Allow overriding port/server if added to JSON later
                if email_data.get('smtp_server'):
                    config['server'] = email_data['smtp_server']
                if email_data.get('smtp_port'):
                    config['port'] = int(email_data['smtp_port'])
    except Exception as e:
        print(f"Error reading price_config.json for email: {e}")
        
    return config




def send_price_alert(recipient_email, product_name, product_url, target_price, current_price, list_price=None, token=None):
    """
    Send a price alert email to the user.
    """
    config = get_config()
    base_url = config['base_url'].rstrip('/')
    if not base_url.startswith('http'):
        base_url = f"https://{base_url}"
    unsub_link = f"{base_url}/unsubscribe/{token}" if token else None
    
    is_on_sale = list_price and current_price < list_price
    discount = round((1 - current_price / list_price) * 100) if is_on_sale else 0

    if not config['email'] or not config['password']:
        print(f"""
        ========== PRICE ALERT (Email not configured) ==========
        To: {recipient_email}
        Product: {product_name}
        URL: {product_url}
        Target Price: ${target_price:.2f}
        Current Price: ${current_price:.2f}
        List Price: {f'${list_price:.2f}' if list_price else 'N/A'}
        Sale: {'Yes (' + str(discount) + '% off)' if is_on_sale else 'No'}
        =========================================================
        """)
        return True
    
    try:
        subject = f"🎉 Price Alert: {product_name} is now ${current_price:.2f}!"
        
        sale_badge_html = f'<span style="background: #ef4444; color: white; padding: 4px 8px; border-radius: 4px; font-size: 14px; margin-left: 10px;">-{discount}% OFF</span>' if is_on_sale else ''
        
        price_display_html = f"""
                <p style="font-size: 24px; margin: 10px 0;">
                    {f'<span style="color: #6b7280; text-decoration: line-through; font-size: 18px;">${list_price:.2f}</span>' if is_on_sale else ''}
                    <span style="color: #059669; font-weight: bold;">${current_price:.2f}</span>
                    {sale_badge_html}
                </p>
        """

        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h1 style="color: #2563eb;">Price Drop Alert! 🎉</h1>
            
            <div style="background: #f3f4f6; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <h2 style="margin: 0 0 10px 0; color: #1f2937;">{product_name}</h2>
                
                {price_display_html}
                
                <p style="color: #059669; font-weight: bold;">
                    It's now below your target of ${target_price:.2f}!
                </p>
            </div>
            
            <a href="{product_url}" style="display: inline-block; background: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                Buy Now
            </a>
            
            <p style="color: #6b7280; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                This alert was sent by AE Price Tracker at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
            {f'<p style="text-align: center;"><a href="{unsub_link}" style="color: #94a3b8; font-size: 11px;">Stop receiving these alerts</a></p>' if unsub_link else ''}
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['email']
        msg['To'] = recipient_email
        
        msg.attach(MIMEText(html_body, 'html'))
        
        # Connect and send
        server = smtplib.SMTP(config['server'], config['port'])
        server.starttls()
        server.login(config['email'], config['password'])
        server.send_message(msg)
        server.quit()
        
        print(f"Price alert email sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False


def send_alert_confirmation(recipient_email, product_name, product_url, target_price, token=None):
    """
    Send an email confirming that the price alert has been set.
    """
    config = get_config()
    base_url = config['base_url'].rstrip('/')
    if not base_url.startswith('http'):
        base_url = f"https://{base_url}"
    unsub_link = f"{base_url}/unsubscribe/{token}" if token else None

    if not config['email'] or not config['password']:
        print(f"""
        ========== ALERT CONFIRMED (Email not configured) ==========
        To: {recipient_email}
        Product: {product_name}
        URL: {product_url}
        Target Price: ${target_price:.2f}
        =============================================================
        """)
        return True

    try:
        subject = f"🔔 Alert Set: Tracking {product_name}"
        
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; color: #1f2937;">
            <h1 style="color: #2563eb;">Price Alert Set! 🔔</h1>
            
            <p>We've started tracking the price of <strong>{product_name}</strong> for you.</p>
            
            <div style="background: #f3f4f6; padding: 20px; border-radius: 10px; margin: 20px 0;">
                <p style="margin: 0; font-size: 16px;">
                    We'll email you immediately when the price drops to or below:
                </p>
                <p style="font-size: 28px; font-weight: bold; margin: 10px 0; color: #10b981;">
                    ${target_price:.2f}
                </p>
            </div>
            
            <p>You can view the product anytime here:</p>
            <a href="{product_url}" style="display: inline-block; background: #2563eb; color: white; padding: 12px 24px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                View Product
            </a>
            
            <p style="color: #6b7280; font-size: 12px; margin-top: 30px; border-top: 1px solid #e5e7eb; padding-top: 20px;">
                This confirmation was sent by AE Price Tracker. You'll receive another email when your target price is reached.
            </p>
            {f'<p style="text-align: center;"><a href="{unsub_link}" style="color: #94a3b8; font-size: 11px;">Remove this alert</a></p>' if unsub_link else ''}
        </body>
        </html>
        """
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = config['email']
        msg['To'] = recipient_email
        
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP(config['server'], config['port'])
        server.starttls()
        server.login(config['email'], config['password'])
        server.send_message(msg)
        server.quit()
        
        print(f"Confirmation email sent to {recipient_email}")
        return True
        
    except Exception as e:
        print(f"Error sending confirmation email: {str(e)}")
        return False
