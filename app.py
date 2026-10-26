import os
from flask import Flask
from extensions import db
from models import Product, Order, User
from routes.client_routes import client_bp
from routes.admin_routes import admin_bp

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "fallback_secret_mozzarella")
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///dairy.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

app.register_blueprint(client_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')

if __name__ == '__main__':
    app.run(debug=True)
