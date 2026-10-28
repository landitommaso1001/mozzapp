import os
from flask import Flask
from extensions import db
from models import Product, Order, User
from routes.client_routes import client_bp
from routes.admin_routes import admin_bp
from datetime import timedelta



app = Flask(__name__)

# 🔒 Core Security & Production Configuration
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret_mozzarella")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///dairy.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 📱 Live Admin Authentication Variables (Reads directly from Render Environment Config)
app.config['ADMIN_PHONE'] = os.environ.get("ADMIN_PHONE", "1234567890")
app.config['ADMIN_PASSWORD'] = os.environ.get("ADMIN_PASSWORD", "1234567890") 
app.config['ADMIN_NAME'] = "admin"

# Add this inside your app configuration block
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# Initialize SQLAlchemy with our Flask App context layer
db.init_app(app)

# 🗺 Register App Blueprint Modalities Natively
app.register_blueprint(client_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')


# 🌱 Database Seeder Routine
def seed_data():
    """ Automatically sets up master credentials and sample catalog records if tables are empty. """
    # 1. Sync and instantiate the master Admin profile securely using the environment configs
    if User.query.count() == 0:
        admin_user = User(
            name=app.config['ADMIN_NAME'], 
            phone=app.config['ADMIN_PHONE'], 
            role="admin"
        )
        admin_user.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin_user)
        
    # 2. Establish product baseline entries
    if Product.query.count() == 0:
        p1 = Product(name="Mozzarella", price_per_kg=10.0, sizes_raw="500 gr, 1000 gr", available=True)
        p2 = Product(name="Provola", price_per_kg=10.0, sizes_raw="500 gr, 1000 gr", available=True)
        db.session.add_all([p1, p2])
        
    # Commit changes permanently to db tracking files
    db.session.commit()


# 🚀 Automated Schema Staging & Thread-Safe Initialisation Execution
with app.app_context():
    db.create_all()
    seed_data()


if __name__ == '__main__':
    # Local fallback debugger runner engine
    app.run(debug=True)
