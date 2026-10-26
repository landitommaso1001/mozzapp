import os
from flask import Flask
from extensions import db
from models import Product, Order, User
from routes.client_routes import client_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)

# 🌟 PRODUCTION UPGRADE: Secure keys from environment variables
app.secret_key = os.environ.get("SECRET_KEY", "fallback_local_secret_mozzarella")

# 🌟 POSTGRESQL SWITCH: Read Neon link online, fall back to SQLite locally
default_db_uri = 'sqlite:///dairy.db'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", default_db_uri)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Static Admin Credentials Configuration
app.config['ADMIN_PHONE'] = os.environ.get("ADMIN_PHONE", "3755234419")
app.config['ADMIN_PASSWORD'] = os.environ.get("ADMIN_PASSWORD", "3755234419") 
app.config['ADMIN_NAME'] = "admin"

db.init_app(app)

# 🌟 PRODUCTION STABILIZATION: Run table creation outside of the __main__ block
with app.app_context():
    db.create_all()
    seed_data()

# Register Feature Packets
app.register_blueprint(client_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')

def seed_data():
    # Seed default Admin account if no users exist
    if User.query.count() == 0:
        admin_user = User(name="Direttore Caseificio", phone="3331234567", role="admin")
        admin_user.set_password("adminpass123")
        db.session.add(admin_user)
        
    if Product.query.count() == 0:
        p1 = Product(name="Mozzarella di Bufala", price_per_kg=15.0, sizes_raw="Vaschetta Bocconcini (250g), Pezzatura Grande (500g)", available=True)
        p2 = Product(name="Burrata Fresca", price_per_kg=18.0, sizes_raw="Standard (200g)", available=True)
        db.session.add_all([p1, p2])
        
    if Order.query.count() == 0:
        o1 = Order(id="ORD-501", client="Mario Rossi", date="2026-10-17", items="2x Mozzarella di Bufala", total=30.0, status="In Ricezione", payment_status="In Attesa", time="")
        o2 = Order(id="ORD-120", client="Mario Rossi", date="2026-10-10", items="3x Burrata Fresca", total=54.0, status="Consegnato", payment_status="Pagato", time="09:00")
        db.session.add_all([o1, o2])
    db.session.commit()

if __name__ == '__main__':
    app.run(debug=True)
