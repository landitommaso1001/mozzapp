import random
from datetime import date
from flask import Blueprint, render_template, request, url_for, redirect, flash, session, current_app
from extensions import db
from models import User, Product, Order

client_bp = Blueprint('client_bp', __name__)

def parse_format_details(format_string, price_per_kg, client_category='Privato'):
    clean_fmt = format_string.strip()
    if not clean_fmt:
        return None, 0.0
        
    # 🏛️ Step A: Absolute Fallback for Over-The-Counter Sales (Vendita Diretta / Banco)
    if client_category == 'Banco':
        if ":" in clean_fmt:
            try:
                name, pricing_rules = clean_fmt.split(":", 1)
                name = name.strip()
                if "," in pricing_rules or ":" in pricing_rules:
                    rules_dict = {}
                    for rule in pricing_rules.split(","):
                        if ":" in rule:
                            k, v = rule.split(":", 1)
                            rules_dict[k.strip().lower()] = float(v.strip())
                    return name, rules_dict.get('privato', price_per_kg)
                return name, float(pricing_rules.strip())
            except ValueError:
                pass
        
        # Metric Weights Engine Fallback
        lower_str = clean_fmt.lower()
        weight_digits = "".join([c for c in lower_str if c.isdigit() or c == '.'])
        if weight_digits:
            try:
                weight_val = float(weight_digits)
                if "kg" in lower_str: return clean_fmt, weight_val * price_per_kg
                if "gr" in lower_str or "g" in lower_str: return clean_fmt, (weight_val / 1000.0) * price_per_kg
            except ValueError: pass
        return clean_fmt, price_per_kg

    # 🛒 Step B: Active Logged-In Customer Selective Filtering
    if ":" in clean_fmt:
        try:
            name, pricing_rules = clean_fmt.split(":", 1)
            name = name.strip()
            
            if "," in pricing_rules or ":" in pricing_rules:
                rules_dict = {}
                for rule in pricing_rules.split(","):
                    if ":" in rule:
                        k, v = rule.split(":", 1)
                        rules_dict[k.strip().lower()] = float(v.strip())
                
                target_key = str(client_category).strip().lower()
                
                # 🌟 SELECTION GATE: Return name and price ONLY if category matches
                if target_key in rules_dict:
                    return name, rules_dict[target_key]
                
                # If rule has colon tiers but this customer category is NOT listed, return None to hide it!
                return None, 0.0
            
            return name, float(pricing_rules.strip())
        except ValueError:
            return clean_fmt, price_per_kg

    # Step C: Standard weight sizing strings with no colons (Visible to all)
    lower_str = clean_fmt.lower()
    weight_digits = "".join([c for c in lower_str if c.isdigit() or c == '.'])
    if weight_digits:
        try:
            weight_val = float(weight_digits)
            if "kg" in lower_str: return clean_fmt, weight_val * price_per_kg
            if "gr" in lower_str or "g" in lower_str: return clean_fmt, (weight_val / 1000.0) * price_per_kg
        except ValueError: pass

    return clean_fmt, price_per_kg
@client_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        static_admin_phone = current_app.config.get('ADMIN_PHONE')
        static_admin_password = current_app.config.get('ADMIN_PASSWORD')
        
        if phone == static_admin_phone and password == static_admin_password:
            session['user_id'] = 0  
            session['user_name'] = current_app.config.get('ADMIN_NAME', 'Admin')
            session['user_role'] = 'admin'
            session['user_category'] = 'Admin'
            flash(f"Accesso Amministratore Eseguito. Benvenuto {session['user_name']}!", "success")
            return redirect(url_for('admin.index'))
            
        user = User.query.filter_by(phone=phone).first()
        if user and user.check_password(password):
            if user.role == 'admin':
                flash("Accesso non autorizzato.", "error")
                return redirect(url_for('client_bp.login'))
                
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = 'client'
            session['user_category'] = user.price_category
            
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
            
        new_user = User(name=name, phone=phone, role='client', price_category='Privato')
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
    
    if request.method == 'POST':
        raw_selected_id = request.form.get('admin_target_client_id', '0')
    else:
        raw_selected_id = request.args.get('selected_client_id', '0')
        
    selected_client_id = int(raw_selected_id) if str(raw_selected_id).isdigit() else 0
    
    catalog_products = Product.query.filter_by(available=True).all()
    all_clients = User.query.filter_by(role='client').all() if is_admin else []

    # 🌟 Resolve exact category context
    if is_admin:
        if selected_client_id > 0:
            active_client_obj = User.query.get(selected_client_id)
            current_category = active_client_obj.price_category if active_client_obj else 'Privato'
        else:
            current_category = 'Banco'
    else:
        current_category = session.get('user_category', 'Privato')

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
                    selected_client_id = target_user.id
                else:
                    order_user_id = None
                    order_client_name = "Vendita Diretta / Banco"
                    selected_client_id = 0
            else:
                order_user_id = None
                order_client_name = "Vendita Diretta / Banco"
                selected_client_id = 0
        else:
            order_user_id = user_id
            current_user_obj = User.query.get(user_id)
            if current_user_obj:
                order_client_name = f"{current_user_obj.name} ({current_user_obj.phone})"
            else:
                order_client_name = session['user_name']
        
        for product in catalog_products:
            if product.sizes_raw:
                formats = product.sizes_raw.split(',')
                for fmt in formats:
                    fmt_name, fmt_price = parse_format_details(fmt, product.price_per_kg, current_category)
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
            if is_admin:
                return redirect(url_for('client_bp.index', selected_client_id=selected_client_id))
            return redirect(url_for('client_bp.index'))

        chosen_delivery_date = request.form.get('delivery_date')
        if not chosen_delivery_date:
            chosen_delivery_date = date.today().strftime("%Y-%m-%d")
            
        new_order = Order(
            id=f"ORD-{random.randint(1000, 9999)}",
            user_id=order_user_id,
            client=order_client_name,
            date=chosen_delivery_date,
            items=", ".join(item_strings),
            total=calculated_total,
            status='Da Confermare', 
            payment_status='Da Saldare',
            time=""
        )
        db.session.add(new_order)
        db.session.commit()
        flash(f"Ordine inoltrato con successo per '{order_client_name}'!", 'success')
        
        if is_admin:
            return redirect(url_for('client_bp.index', selected_client_id=selected_client_id))
        return redirect(url_for('client_bp.index'))
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
                f_name, f_price = parse_format_details(fmt, product.price_per_kg, current_category)
                # 🌟 SECURITY GATEWAY: Only append formats that successfully resolve a name
                if f_name:
                    parsed_formats.append({'name': f_name, 'price': f_price})
        enriched_products.append({'id': product.id, 'name': product.name, 'price_per_kg': product.price_per_kg, 'parsed_formats': parsed_formats})

    if is_admin:
        my_orders = Order.query.order_by(Order.serial_id.desc()).all()
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
        selected_client_id=selected_client_id
    )

@client_bp.route('/order/cancel/<path:order_id>', methods=['POST'])
def cancel_order(order_id):
    if 'user_id' not in session: 
        return redirect(url_for('client_bp.login'))
    
    is_admin = (session.get('user_role') == 'admin')
    if is_admin:
        order = Order.query.filter_by(id=order_id).first_or_404()
    else:
        order = Order.query.filter_by(id=order_id, user_id=session['user_id']).first_or_404()
        
    if order.status == 'Da Confermare': 
        order.status = 'Annullato'
        order.payment_status = 'Annullato'
        db.session.commit()
        flash(f"Ordine {order_id} annullato con successo.", "success")
    else:
        flash("Impossibile annullare l'ordine.", "error")
        
    if is_admin:
        selected_client = request.form.get('hidden_selected_client_id', '0')
        return redirect(url_for('client_bp.index', selected_client_id=selected_client))
        
    return redirect(url_for('client_bp.index'))
