import random
from datetime import date
from flask import Blueprint, render_template, request, url_for, redirect, flash, session, current_app
from extensions import db
from models import User, Product, Order

# Define the blueprint object before initializing routes to prevent NameError
client_bp = Blueprint('client_bp', __name__)

def parse_format_details(format_string, price_per_kg):
    clean_fmt = format_string.strip()
    if not clean_fmt:
        return None, 0.0
    if ":" in clean_fmt:
        try:
            name, raw_price = clean_fmt.split(":")
            return name.strip(), float(raw_price)
        except ValueError:
            return clean_fmt, 0.0
    weight_str = "".join([c for c in clean_fmt if c.isdigit()])
    if weight_str and ("g" in clean_fmt.lower() or "gr" in clean_fmt.lower()):
        grams = float(weight_str)
        return clean_fmt, (grams / 1000.0) * price_per_kg
    return clean_fmt, price_per_kg

@client_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        # 1. Check against Static Admin Credentials Configuration
        static_admin_phone = current_app.config.get('ADMIN_PHONE')
        static_admin_password = current_app.config.get('ADMIN_PASSWORD')
        
        if phone == static_admin_phone and password == static_admin_password:
            session['user_id'] = 0  # Hardcoded placeholder ID for static admin
            session['user_name'] = current_app.config.get('ADMIN_NAME', 'Admin')
            session['user_role'] = 'admin'
            flash(f"Accesso Amministratore Eseguito. Benvenuto {session['user_name']}!", "success")
            return redirect(url_for('admin.index'))
            
        # 2. Check standard client users database table
        user = User.query.filter_by(phone=phone).first()
        if user and user.check_password(password):
            if user.role == 'admin':
                flash("Accesso non autorizzato.", "error")
                return redirect(url_for('client_bp.login'))
                
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = 'client'
            
            flash(f"Bentornato, {user.name}!", "success")
            return redirect(url_for('client_bp.index'))
            
        flash("Credenziali non valide. Riprova.", "error")
    return render_template('login.html')

@client_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        if User.query.filter_by(phone=phone).first():
            flash("Questo numero di telefono è già registrato.", "error")
            return redirect(url_for('client_bp.register'))
            
        new_user = User(name=name, phone=phone, role='client')
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registrazione completata! Effettua il login.", "success")
        return redirect(url_for('client_bp.login'))
    return render_template('register.html')

@client_bp.route('/logout')
def logout():
    session.clear()
    flash("Sessione chiusa correttamente.", "success")
    return redirect(url_for('client_bp.login'))
@client_bp.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('client_bp.login'))
        
    user_id = session['user_id']
    is_admin = (session.get('user_role') == 'admin')
    catalog_products = Product.query.filter_by(available=True).all()
    all_clients = User.query.filter_by(role='client').all() if is_admin else []

    if request.method == 'POST':
        item_strings = []
        calculated_total = 0.0
        
        raw_target_id = request.form.get('admin_target_client_id')
        
        if is_admin:
            if raw_target_id and str(raw_target_id).isdigit() and int(raw_target_id) > 0:
                target_user = User.query.get(int(raw_target_id))
                if target_user:
                    order_user_id = target_user.id
                    order_client_name = f"{target_user.name} ({target_user.phone})"
                else:
                    order_user_id = None
                    order_client_name = "Vendita Diretta / Banco"
            else:
                order_user_id = None
                order_client_name = "Vendita Diretta / Banco"
        else:
            order_user_id = user_id
            order_client_name = session['user_name']
        
        for product in catalog_products:
            if product.sizes_raw:
                formats = product.sizes_raw.split(',')
                for fmt in formats:
                    fmt_name, fmt_price = parse_format_details(fmt, product.price_per_kg)
                    if not fmt_name: continue
                    
                    qty_key = f"qty_{product.id}_{fmt_name}"
                    qty = int(request.form.get(qty_key, 0)) if request.form.get(qty_key) else 0
                    if qty > 0:
                        item_strings.append(f"{qty}x {product.name} ({fmt_name})")
                        calculated_total += qty * fmt_price
            else:
                qty_key = f"qty_{product.id}_default"
                qty = int(request.form.get(qty_key, 0)) if request.form.get(qty_key) else 0
                if qty > 0:
                    item_strings.append(f"{qty}x {product.name}")
                    calculated_total += qty * product.price_per_kg
        
        if not item_strings:
            flash("Seleziona almeno un prodotto prima di inviare l'ordine.", "error")
            return redirect(url_for('client_bp.index'))
            
        new_order = Order(
            id=f"ORD-{random.randint(1000, 9999)}",
            user_id=order_user_id,
            client=order_client_name,
            date=date.today().strftime("%Y-%m-%d"),
            items=", ".join(item_strings),
            total=calculated_total,
            status='In Ricezione',
            payment_status='In Attesa',
            time=""
        )
        db.session.add(new_order)
        db.session.commit()
        flash(f"Ordine inoltrato con successo per '{order_client_name}'!", 'success')
        
        if is_admin:
            return redirect(url_for('admin.index', active_tab='orders'))
        return redirect(url_for('client_bp.index'))

    # Reorder functionality parser
    prefilled_items = {}
    reorder_id = request.args.get('reorder')
    if reorder_id:
        old_order = Order.query.filter_by(id=reorder_id).first()
        if old_order and (is_admin or old_order.user_id == user_id) and old_order.items:
            for part in old_order.items.split(','):
                part = part.strip()
                if not part or 'x' not in part: continue
                try:
                    qty_str, item_name = part.split('x', 1)
                    prefilled_items[item_name.strip()] = int(qty_str.strip())
                except ValueError: continue

    enriched_products = []
    for product in catalog_products:
        parsed_formats = []
        if product.sizes_raw:
            for fmt in product.sizes_raw.split(','):
                f_name, f_price = parse_format_details(fmt, product.price_per_kg)
                if f_name: parsed_formats.append({'name': f_name, 'price': f_price})
        enriched_products.append({'id': product.id, 'name': product.name, 'price_per_kg': product.price_per_kg, 'parsed_formats': parsed_formats})

    # 🌟 NEW LOGIC: Dynamic Filter context processing for Admin
    selected_client_id = request.args.get('selected_client_id', '0')
    
    if is_admin:
        if selected_client_id and selected_client_id.isdigit() and int(selected_client_id) > 0:
            # Filter history strictly to the selected user row match
            my_orders = Order.query.filter_by(user_id=int(selected_client_id)).order_by(Order.serial_id.desc()).all()
        else:
            # Show internal/direct sales orders (where user_id is null or 0)
            my_orders = Order.query.filter(Order.user_id == None).order_by(Order.serial_id.desc()).all()
    else:
        my_orders = Order.query.filter_by(user_id=user_id).order_by(Order.serial_id.desc()).all()
    
    return render_template(
        'client.html', 
        orders=my_orders, 
        products=enriched_products, 
        view='client', 
        prefilled_items=prefilled_items,
        is_admin=is_admin,
        all_clients=all_clients,
        selected_client_id=int(selected_client_id)
    )

@client_bp.route('/order/cancel/<path:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session: return redirect(url_for('client_bp.login'))
    
    is_admin = (session.get('user_role') == 'admin')
    if is_admin:
        order = Order.query.filter_by(id=order_id).first_or_404()
    else:
        order = Order.query.filter_by(id=order_id, user_id=session['user_id']).first_or_404()
        
    if order.status == 'In Ricezione':
        order.status = 'Annullato'
        db.session.commit()
        flash(f"Ordine {order_id} annullato.", "success")
    else:
        flash("Impossibile annullare l'ordine.", "error")
        
    if is_admin:
        return redirect(url_for('admin.index', active_tab='orders'))
    return redirect(url_for('client_bp.index'))
