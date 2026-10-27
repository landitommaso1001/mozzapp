from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='client', nullable=False) # 'client' or 'admin'
    
    # Relationship to cleanly pull orders associated with this user
    orders = db.relationship('Order', backref='customer', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    @property
    def is_admin(self):
        return self.role == 'admin'

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    price_per_kg = db.Column(db.Float, nullable=False)
    sizes_raw = db.Column(db.String(200), nullable=True)
    available = db.Column(db.Boolean, default=True)

class Order(db.Model):
    __tablename__ = 'orders'
    serial_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id = db.Column(db.String(20), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Linked to User
    client = db.Column(db.String(100), nullable=False) # Fallback / display name
    date = db.Column(db.String(20), nullable=True)
    items = db.Column(db.String(500), nullable=True)
    total = db.Column(db.Float, default=0.0)
    time = db.Column(db.String(20), nullable=True)
    status = db.Column(db.String(20), default='In Ricezione')
    payment_status = db.Column(db.String(20), default='Da Saldare')
