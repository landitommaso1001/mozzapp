import random
from datetime import date
from flask import Blueprint, render_template, request, url_for, redirect, flash, session, current_app
from extensions import db
from models import User, Product, Order

client_bp = Blueprint('client_bp', __name__)

def parse_format_details(format_rules_string, format_label_name, client_category):
    if not format_rules_string or not client_category:
        return None, 0.0

    try:
        rules_dict = {}
        # Parses the pricing field string rules: e.g., "Privato:5.00, Ristorante:4.00"
        for rule in format_rules_string.split(","):
            if ":" in rule:
                k, v = rule.split(":", 1)
                rules_dict[k.strip().lower()] = float(v.strip())
        
        target_key = str(client_category).strip().lower()
        
        # 🌟 STRICT EXPLICIT MATCH: Return the defined layout data ONLY if category matches
        if target_key in rules_dict:
            # Returns the custom Formato string text as the name layout identifier
            return format_label_name, rules_dict[target_key]
            
    except Exception:
        pass

    # If the active tier is not defined inside this rules line, hide it entirely!
    return None, 0.0




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
        raw_selected_id = request.form.get('admin_target_client_id', '-1')
    else:
        raw_selected_id = request.args.get('selected_client_id', '-1')
        
    selected_client_id = int(raw_selected_id) if str(raw_selected_id).replace('-', '').isdigit() else -1
    
    catalog_products = Product.query.filter_by(available=True).all()
    all_clients = User.query.filter_by(role='client').all() if is_admin else []

    current_category = None
    if is_admin:
        if selected_client_id > 0:
            active_client_obj = User.query.get(selected_client_id)
            if active_client_obj:
                current_category = active_client_obj.price_category
    else:
        current_category = session.get('user_category', 'Privato')

    if request.method == 'POST':
        if is_admin and selected_client_id <= 0:
            flash("Errore: Seleziona un cliente specifico o una categoria generica prima di inviare l'ordine.", "error")
            return redirect(url_for('client_bp.index'))

        item_strings = []
        calculated_total = 0.0
        
        if is_admin:
            target_user = User.query.get(selected_client_id)
            order_user_id = target_user.id if target_user else None
            order_client_name = f"{target_user.name} ({target_user.phone})" if target_user else "Cliente Banco"
        else:
            order_user_id = user_id
            current_user_obj = User.query.get(user_id)
            order_client_name = f"{current_user_obj.name} ({current_user_obj.phone})" if current_user_obj else session['user_name']
        
     # 📂 Replace the product form iteration loop inside routes/client_routes.py:

        for product in catalog_products:
            # 🌟 FIX 1: Run the helper function ONCE per product using its standalone sizes_raw rules string
            fmt_name, fmt_price = parse_format_details(product.sizes_raw, product.price_per_kg, current_category)
            
            # If the product isn't assigned a price for this category, skip it cleanly!
            if not fmt_name or fmt_price <= 0.0:
                continue
                
            # Construct the clean HTML input element key match
            qty_key = f"qty_{product.id}_{fmt_name}"
            qty = int(request.form.get(qty_key, 0)) if request.form.get(qty_key) else 0
            
            if qty > 0:
                # 📝 FIX 2: Human-readable manifest builder -> Output: "2x Mozzarella (500 gr)"
                item_strings.append(f"{qty}x {product.name} ({fmt_name})")
                
                # 🧮 FIX 3: Pure scalar calculation (Prevents the 3x-4x multiplication bug entirely)
                calculated_total += qty * fmt_price

        if not item_strings:
            flash("Seleziona almeno un prodotto prima di inviare l'ordine.", "error")
            return redirect(url_for('client_bp.index', selected_client_id=selected_client_id))

        chosen_delivery_date = request.form.get('delivery_date') or date.today().strftime("%Y-%m-%d")
            
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
        return redirect(url_for('client_bp.index', selected_client_id=selected_client_id) if is_admin else url_for('client_bp.index'))

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
    if current_category:
        for product in catalog_products:
            parsed_formats = []
            if product.sizes_raw:
                # 🌟 FIX: Process the rules string intact instead of fracturing it prematurely
                f_name, f_price = parse_format_details(product.sizes_raw, product.price_per_kg, current_category)
                if f_name and f_price > 0.0:
                    parsed_formats.append({'name': f_name, 'price': f_price})
            
            if parsed_formats:
                enriched_products.append({
                    'id': product.id, 
                    'name': product.name, 
                    'price_per_kg': product.price_per_kg, 
                    'parsed_formats': parsed_formats
                })

    my_orders = Order.query.order_by(Order.serial_id.desc()).all() if is_admin else Order.query.filter_by(user_id=user_id).order_by(Order.serial_id.desc()).all()
    
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
    order = Order.query.filter_by(id=order_id).first_or_404() if is_admin else Order.query.filter_by(id=order_id, user_id=session['user_id']).first_or_404()
        
    if order.status == 'Da Confermare': 
        order.status = 'Annullato'
        order.payment_status = 'Annullato'
        db.session.commit()
        flash(f"Ordine {order_id} annullato con successo.", "success")
    else:
        flash("Impossibile annullare l'ordine.", "error")
    return redirect(url_for('client_bp.index', selected_client_id=request.form.get('hidden_selected_client_id', '0')) if is_admin else url_for('client_bp.index'))

