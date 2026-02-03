# Database Models
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone

db = SQLAlchemy()


# Association table for User <-> Product (Many-to-Many)
# Allows users to "track" products without setting specific alerts
user_products = db.Table('user_products',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    db.Column('product_id', db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), primary_key=True),
    db.Column('added_at', db.DateTime, default=lambda: datetime.now(timezone.utc))
)

class User(db.Model):
    """User account for syncing data across devices"""
    __tablename__ = 'users'
    __table_args__ = {'sqlite_autoincrement': True}
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True) # Nullable for now, used later
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    # Products this user is "watching"
    tracked_products = db.relationship('Product', secondary=user_products, 
                                     lazy='subquery',
                                     backref=db.backref('followers', lazy=True))
    
    # Alerts created by this user
    alerts = db.relationship('PriceAlert', backref='user', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }


class Product(db.Model):
    """Tracked product from American Eagle"""
    __tablename__ = 'products'
    # Force SQLite to check FOREIGN KEYS (via app config) and never reuse IDs
    __table_args__ = {'sqlite_autoincrement': True}
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), unique=True, nullable=False)
    name = db.Column(db.String(300), nullable=False)
    current_price = db.Column(db.Float, nullable=True)
    list_price = db.Column(db.Float, nullable=True)
    image_url = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_checked = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships with CASCADE DELETE
    # cascade="all, delete-orphan" handles SQLAlchemy session deletes
    # passive_deletes=True tells SQLAlchemy to let the DB handle it if possible (requires DB setup)
    price_history = db.relationship('PriceHistory', backref='product', lazy=True, 
                                  order_by='PriceHistory.timestamp',
                                  cascade="all, delete-orphan")
    alerts = db.relationship('PriceAlert', backref='product', lazy=True,
                           cascade="all, delete-orphan")
    
    @property
    def is_on_sale(self):
        if self.current_price and self.list_price:
            return self.current_price < self.list_price
        return False
    
    @property
    def discount_percentage(self):
        if self.is_on_sale:
            return round((1 - self.current_price / self.list_price) * 100)
        return 0

    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'name': self.name,
            'current_price': self.current_price,
            'list_price': self.list_price,
            'is_on_sale': self.is_on_sale,
            'discount_percentage': self.discount_percentage,
            'image_url': self.image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'price_history': [ph.to_dict() for ph in self.price_history],
            'alerts': [a.to_dict() for a in self.alerts]
        }


class PriceHistory(db.Model):
    """Historical price snapshots"""
    __tablename__ = 'price_history'
    
    id = db.Column(db.Integer, primary_key=True)
    # Define OnDelete behavior for DB level
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    def to_dict(self):
        return {
            'id': self.id,
            'price': self.price,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class PriceAlert(db.Model):
    """User price alerts"""
    __tablename__ = 'price_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    # Define OnDelete behavior for DB level
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    # Link to user (optional for now, to support guest alerts)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=True)
    email = db.Column(db.String(200), nullable=False)
    target_price = db.Column(db.Float, nullable=False)
    triggered = db.Column(db.Boolean, default=False)
    token = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    triggered_at = db.Column(db.DateTime, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'target_price': self.target_price,
            'triggered': self.triggered,
            'token': self.token,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'user_id': self.user_id
        }
