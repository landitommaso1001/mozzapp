import os
from flask import Flask, redirect, url_for, session
from extensions import db
from models import Product, Order, User
from routes.client_routes import client_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)

# Production configuration keys
app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret_mozzarella")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///dairy.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ADMIN_PHONE'] = os.environ.get("ADMIN_PHONE", "1234567890")
app.config['ADMIN_PASSWORD'] = os.environ.get("ADMIN_PASSWORD", "1234567890") 
app.config['ADMIN_NAME'] = "admin"

db.init_app(app)

# 1. FIXED: Enforce a global root interceptor route before loading blueprints
@app.route('/')

def global_root_index():
    if 'user_id' not in session:
        return redirect('/login')
    
    # If already logged in, route them based on their profile role using your native query view format
    if session.get('user_role') == 'admin':
        return redirect('/admin/?active_tab=orders')
    return redirect('/?view=client')

# Register Feature Packets
app.register_blueprint(client_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')

def seed_data():
    if User.query.count() == 0:
        admin_user = User(name="admin", phone="1234567890", role="admin")
        admin_user.set_password("1234567890")
        db.session.add(admin_user)
        
    if Product.query.count() == 0:
        p1 = Product(name="Mozzarella", price_per_kg=10.0, sizes_raw="500 gr, 1000 gr", available=True)
        p2 = Product(name="Provola", price_per_kg=10.0, sizes_raw="500 gr, 1000 gr", available=True)
        db.session.add_all([p1, p2])
        
    if Order.query.count() == 0:
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == '__main__':
    app.run(debug=True)
