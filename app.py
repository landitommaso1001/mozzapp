import os
from flask import Flask
from extensions import db
from models import Product, Order, User
from routes.client_routes import client_bp
from routes.admin_routes import admin_bp
from datetime import timedelta



app = Flask(__name__)

from datetime import datetime, timedelta
import os
from flask import Flask
from extensions import db
# ... other imports ...

app = Flask(__name__)

# 🌟 Add this filter helper right here
@app.template_filter('format_euro_date')
def format_euro_date(date_str):
    if not date_str:
        return ""
    try:
        # Converts 'YYYY-MM-DD' into 'dd.mm.yyyy'
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        return date_str # Fallback in case of custom manual entries


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


def seed_system_accounts():
    """
    Safely creates the fallback generic blueprint customer categorizations
    without attempting to load deprecated product lists or numeric weights.
    """
    from models import User
    from extensions import db
    
    # Check if a client user profile already exists to prevent duplication
    if not User.query.filter_by(role='client').first():
        print("👥 Seeding clear framework system tier blueprints...")
        
        system_blueprints = [
            {"name": "Vendite Privati Generiche", "phone": "1111", "cat": "Privato"},
            {"name": "Ristoranti Generici / Banco", "phone": "2222", "cat": "Ristorante"},
            {"name": "Alimentari Generici / Banco", "phone": "3333", "cat": "Alimentari"},
            {"name": "Prezzi Speciali Generici", "phone": "4444", "cat": "Special"}
        ]
        
        for bp in system_blueprints:
            user = User(
                name=bp["name"],
                phone=bp["phone"],
                role='client',
                price_category=bp["cat"]
            )
            user.set_password("password123")  # Replace with your secure default credentials
            db.session.add(user)
            
        db.session.commit()
        print("✅ Blueprint customer rows registered securely.")



# 📂 Place this structural correction block at the bottom of app.py

with app.app_context():
    try:
        from sqlalchemy import text
        print("🔧 Dropping legacy column metrics constraints on Postgres...")
        
        # 🌟 SURGICAL TYPE-CAST: Switches the column type to text string characters permanently
        db.session.execute(text("ALTER TABLE products ALTER COLUMN price_per_kg TYPE VARCHAR(50);"))
        
        # Ensure your custom category column is explicitly initialized
        db.session.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS price_category VARCHAR(50) DEFAULT 'Privato' NOT NULL;"))
        db.session.commit()
        print("✅ Postgres string columns adjusted successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"💡 Database tuning notice: {e}")

    # Standard safe schema builder remains here
    db.create_all()


if __name__ == '__main__':
    app.run(debug=True)
    


if __name__ == '__main__':
    # Local fallback debugger runner engine
    app.run(debug=True)
