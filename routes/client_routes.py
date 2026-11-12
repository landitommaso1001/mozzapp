import random
from datetime import date, datetime
from flask import Blueprint, render_template, request, url_for, redirect, flash, session, current_app
from extensions import db
from models import User, Product, Order

client_bp = Blueprint('client_bp', __name__)

def parse_format_details(format_rules_string, format_label_name, client_category):
    if not format_rules_string or not client_category:
        return None, 0.0

    try:
        rules_dict = {}
        for rule in format_rules_string.split(","):
            if ":" in rule:
                k, v = rule.split(":", 1)
                rules_dict[k.strip().lower()] = float(v.strip())
        
        target_key = str(client_category).strip().lower()
        
        if target_key in rules_dict:
            return format_label_name, rules_dict[target_key]
            
    except Exception:
        pass

    return None, 0.0


@client_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        
        static_admin_phone = current_app.config.get('ADMIN_PHONE')
        static_admin_password = current_app.config.get('ADMIN_PASSWORD')

        if phone == static_admin_phone:
            admin_config = User.query.filter_by(phone='_admin_config').first()
            is_valid_admin = (
                admin_config.check_password(password)
                if admin_config
                else (password == static_admin_password)
            )
            if is_valid_admin:
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
    all_clients = User.query.filter_by(role='client').order_by(User.name.asc()).all() if is_admin else []

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

        for product in catalog_products:
            fmt_name, fmt_price = parse_format_details(product.sizes_raw, product.price_per_kg, current_category)
            if not fmt_name or fmt_price <= 0.0:
                continue
                
            qty_key = f"qty_{product.id}_{fmt_name}"
            qty = int(request.form.get(qty_key, 0)) if request.form.get(qty_key) else 0
            
            if qty > 0:
                item_strings.append(f"{qty}x {product.name} ({fmt_name})")
                calculated_total += qty * fmt_price

        if not item_strings:
            flash("Seleziona almeno un prodotto prima di inviare l'ordine.", "error")
            return redirect(url_for('client_bp.index', selected_client_id=selected_client_id))

        now_ts = datetime.now()
        chosen_delivery_date = request.form.get('delivery_date') or date.today().strftime("%Y-%m-%d")
        
        try:
            parsed_delivery_date = datetime.strptime(chosen_delivery_date, "%Y-%m-%d")
            date_prefix = parsed_delivery_date.strftime("%d.%m.%Y") + "-" + now_ts.strftime("%H.%M")
        except Exception:
            date_prefix = now_ts.strftime("%d.%m.%Y-%H.%M")

        daily_order_count = Order.query.filter_by(date=chosen_delivery_date).count()
        progressive_suffix = f"{daily_order_count + 1:03d}"
        custom_meaningful_id = f"{date_prefix}-{progressive_suffix}"
            
        new_order = Order(
            id=custom_meaningful_id,
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
        
        items_payload = ", ".join(item_strings)
        
        if is_admin:
            return redirect(url_for('client_bp.index', selected_client_id=selected_client_id, whatsapp_notify='1', last_order_id=custom_meaningful_id, order_items_summary=items_payload))
        else:
            return redirect(url_for('client_bp.index', whatsapp_notify='1', last_order_id=custom_meaningful_id, order_items_summary=items_payload))

    # 🌟 FIX: Smart reorder check that auto-restores client parameters for administrators
    prefilled_items = {}
    reorder_id = request.args.get('reorder')
    if reorder_id:
        old_order = Order.query.filter_by(id=reorder_id).first()
        if old_order and (is_admin or old_order.user_id == user_id) and old_order.items:
            # If an admin clicked reorder and no client is selected yet, lock onto the original order's client
            if is_admin and selected_client_id <= 0 and old_order.user_id:
                selected_client_id = old_order.user_id
                # Force update the current category tier logic right away
                active_client_obj = User.query.get(selected_client_id)
                if active_client_obj:
                    current_category = active_client_obj.price_category

            for part in old_order.items.split(','):
                part = part.strip()
                if not part or 'x' not in part: 
                    continue
                try:
                    qty_str, item_name = part.split('x', 1)
                    clean_item_name = item_name.strip()
                    prefilled_items[clean_item_name] = int(qty_str.strip())
                except ValueError: 
                    continue

    enriched_products = []
    if current_category:
        for product in catalog_products:
            parsed_formats = []
            if product.sizes_raw:
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
    
    whatsapp_row = User.query.filter_by(phone='_whatsapp_config').first()
    whatsapp_enabled = (whatsapp_row.price_category == 'ENABLED') if whatsapp_row else True
    active_notification_lines = []
    if whatsapp_enabled and whatsapp_row and whatsapp_row.name:
        for idx, entry in enumerate(whatsapp_row.name.split(','), start=1):
            entry = entry.strip()
            if not entry:
                continue
            if ':' in entry:
                label, num = entry.split(':', 1)
                clean_label = label.strip() or f"Linea #{idx}"
                clean_num = num.strip()
            else:
                clean_label = f"Linea #{idx}"
                clean_num = entry
            if clean_num:
                active_notification_lines.append({'label': clean_label, 'number': clean_num})

    whatsapp_message_text = ""
    last_order_id = request.args.get('last_order_id')
    if request.args.get('whatsapp_notify') == '1' and last_order_id:
        recent_order = Order.query.filter_by(id=last_order_id).first()
        if recent_order:
            # Strip whitespace and convert YYYY-MM-DD to European DD.MM.YYYY format
            try:
                clean_date_str = str(recent_order.date).strip()
                euro_delivery_date = datetime.strptime(clean_date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
            except Exception:
                euro_delivery_date = recent_order.date

            items_lines = "\n".join([f"- {item.strip()}" for item in recent_order.items.split(',') if item.strip()])
            whatsapp_message_text = (
                f"*Nuovo Ordine MozzApp*\n"
                f"*ID:* {recent_order.id}\n"
                f"*Cliente:* {recent_order.client}\n"
                f"*Data Consegna:* {euro_delivery_date}\n"
                f"*Prodotti:*\n{items_lines}\n"
                f"*Totale:* EUR {recent_order.total:.2f}"
            )


    return render_template(
        'client.html', 
        orders=my_orders, 
        products=enriched_products, 
        view='client', 
        prefilled_items=prefilled_items,
        is_admin=is_admin,
        all_clients=all_clients,
        selected_client_id=selected_client_id,
        active_notification_lines=active_notification_lines,
        whatsapp_message_text=whatsapp_message_text
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
