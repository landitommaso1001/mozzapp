from flask import Blueprint, render_template, request, url_for, redirect, flash, session
from extensions import db
from models import Product, Order, User
from datetime import datetime, date
from functools import wraps
import random

admin_bp = Blueprint('admin', __name__)

# Security Decorator: Lock out non-admin accounts
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('user_role') != 'admin':
            flash("Accesso negato. Questa zona è riservata agli amministratori del caseificio.", "danger")
            return redirect(url_for('client_bp.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/', methods=['GET', 'POST'])
@admin_required
def index():
    active_tab = request.args.get('active_tab', 'orders')
    
    # Standard Date Range / Dashboard parameters (keep these)
    filter_status = request.args.get('status', '')  
    filter_client_id = request.args.get('client_id', '') 
    filter_date_from = request.args.get('date_from', '') 
    filter_date_to = request.args.get('date_to', '')     
    
    # Analytics-specific Tab query options
    filter_start_date = request.args.get('start_date', '')
    filter_end_date = request.args.get('end_date', '')
    filter_product = request.args.get('product_name', '')

    filter_unpaid_delivered = request.args.get('non_salda_consegnati', '')
    
    # --- NEW PARAMETERS FOR ANALYTICS FILTERING ---
    analytics_client_id = request.args.get('analytics_client_id', '')
    analytics_payment_status = request.args.get('analytics_payment_status', '')
    # -----------------------------------------------
    
    filter_format = "" # Neutralized from previous hotfix

    # Base query for orders
    order_query = Order.query
    if filter_status:
        order_query = order_query.filter_by(status=filter_status)
    if filter_date_from:
        order_query = order_query.filter(Order.date >= filter_date_from)
    if filter_date_to:
        order_query = order_query.filter(Order.date <= filter_date_to)
    if filter_client_id:
        if filter_client_id == 'banco':
            order_query = order_query.filter(Order.user_id == None)
        else:
            order_query = order_query.filter_by(user_id=int(filter_client_id))
    if filter_unpaid_delivered == '1':
        order_query = order_query.filter_by(status='Consegnato', payment_status='Da Saldare')
    elif filter_status:
        order_query = order_query.filter_by(status=filter_status)

    admin_orders = order_query.order_by(Order.serial_id.desc()).all()
    catalog_products = Product.query.all()
    client_list = User.query.filter_by(role='client').all()
    
    # Catalog compilation logic (including our string correction step)
    catalog_map = {}
    for p in catalog_products:
        if p.sizes_raw:
            formats = []
            for f in p.sizes_raw.split(','):
                clean_f = f.strip()
                if ":" in clean_f:
                    clean_f = clean_f.split(":")[0].strip()
                if clean_f:
                    formats.append(clean_f)
            catalog_map[p.name] = formats
        else:
            catalog_map[p.name] = []

    # Financial card calculations (remains global / unfiltered)
    total_revenue = 0.0
    paid_revenue = 0.0
    unpaid_revenue = 0.0
    all_unfiltered_orders = Order.query.all()
    for o in all_unfiltered_orders:
        if o.status == 'Annullato':
            continue
        total_revenue += o.total
        if o.payment_status == 'Pagato':
            paid_revenue += o.total
        else:
            unpaid_revenue += o.total

    # Secondary calculation structures
    product_summary = {}
    grand_total_qty = 0
    grand_total_kg = 0.0
    grand_total_revenue = 0.0

    # Secondary loop for rendering dynamic metrics items matching filters
    for o in admin_orders:
        if o.status == 'Annullato':
            continue
            
        # 1. Evaluate Date Range criteria constraints
        order_date_valid = True
        if filter_start_date or filter_end_date:
            try:
                o_date = datetime.strptime(o.date, "%Y-%m-%d")
                if filter_start_date and o_date < datetime.strptime(filter_start_date, "%Y-%m-%d"): 
                    order_date_valid = False
                if filter_end_date and o_date > datetime.strptime(filter_end_date, "%Y-%m-%d"): 
                    order_date_valid = False
            except Exception:
                pass
        if not order_date_valid:
            continue

        # 2. NEW: Evaluate Analytics Client Dropdown constraint
        if analytics_client_id:
            if analytics_client_id == 'banco' and o.user_id is not None:
                continue
            elif analytics_client_id != 'banco' and o.user_id != int(analytics_client_id):
                continue

        # 3. NEW: Evaluate Analytics Payment Status Dropdown constraint
        if analytics_payment_status and o.payment_status != analytics_payment_status:
            continue

        # Parse valid order entries matching requirements
        if o.items:
            for item in o.items.split(','):
                item = item.strip()
                if not item or 'x' not in item: continue
                try:
                    qty_str, full_name = item.split('x', 1)
                    qty = int(qty_str.strip())
                    full_name = full_name.strip()
                    
                    prod_matched = False
                    matched_prod_obj = None
                    for p in catalog_products:
                        if p.name.lower() in full_name.lower():
                            matched_prod_obj = p
                            break
                    
                    p_name = matched_prod_obj.name if matched_prod_obj else full_name
                    if not filter_product or filter_product.lower() in p_name.lower():
                        prod_matched = True
                        
                    if prod_matched:
                        computed_weight = parse_format_weight_kg(full_name, qty)
                        unit_price = parse_admin_format_price(full_name, matched_prod_obj)
                        computed_revenue = unit_price * qty
                        
                        if full_name not in product_summary:
                            product_summary[full_name] = {'qty': 0, 'kg': 0.0, 'revenue': 0.0}
                        
                        product_summary[full_name]['qty'] += qty
                        product_summary[full_name]['kg'] += computed_weight
                        product_summary[full_name]['revenue'] += computed_revenue
                        
                        grand_total_qty += qty
                        grand_total_kg += computed_weight
                        grand_total_revenue += computed_revenue
                        
                except ValueError: 
                    continue

    return render_template(
        'admin.html',
        orders=admin_orders,
        products=catalog_products,
        clients=client_list,
        active_tab=active_tab,
        view='admin',
        total_revenue=total_revenue,
        paid_revenue=paid_revenue,
        unpaid_revenue=unpaid_revenue,
        product_summary=product_summary,
        grand_total_qty=grand_total_qty,
        grand_total_kg=grand_total_kg,
        grand_total_revenue=grand_total_revenue,
        start_date=filter_start_date,
        end_date=filter_end_date,
        product_name=filter_product,
        format_name="",
        # Pass new variables to retain dropdown choices on page render
        analytics_client_id=analytics_client_id,
        analytics_payment_status=analytics_payment_status,
        catalog_map=catalog_map,
        non_salda_consegnati=filter_unpaid_delivered,
        current_status=filter_status,      
        current_client_id=filter_client_id,
        current_date_from=filter_date_from, 
        current_date_to=filter_date_to
    )




@admin_bp.route('/order/update_status', methods=['POST'])
@admin_required
def update_order_status():
    order_id = request.args.get('order_id')
    new_status = request.args.get('new_status')
    
    status = request.args.get('status', '')
    client_id = request.args.get('client_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    order = Order.query.filter_by(id=order_id).first_or_404()
    try:
        if new_status == 'Confermato':
            order.time = request.form.get('delivery_time')
        order.status = new_status
        db.session.commit()
        flash(f"Ordine #{order_id} aggiornato a '{new_status}'!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
        
    return redirect(url_for('admin.index', active_tab='orders', status=status, client_id=client_id, date_from=date_from, date_to=date_to))

@admin_bp.route('/order/mark_paid', methods=['POST'])
@admin_required
def mark_order_paid():
    order_id = request.args.get('order_id')
    
    status = request.args.get('status', '')
    client_id = request.args.get('client_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    order = Order.query.filter_by(id=order_id).first_or_404()
    try:
        order.payment_status = 'Pagato'
        db.session.commit()
        flash(f"Pagamento per l'ordine #{order_id} registrato!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
        
    return redirect(url_for('admin.index', active_tab='orders', status=status, client_id=client_id, date_from=date_from, date_to=date_to))

@admin_bp.route('/order/cancel', methods=['POST'])
@admin_required
def cancel_order():
    order_id = request.args.get('order_id')
    
    status = request.args.get('status', '')
    client_id = request.args.get('client_id', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')
    
    order = Order.query.filter_by(id=order_id).first_or_404()
    try:
        order.status = 'Annullato'
        order.payment_status = 'Annullato'
        db.session.commit()
        flash(f"Ordine #{order_id} annullato.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
        
    return redirect(url_for('admin.index', active_tab='orders', status=status, client_id=client_id, date_from=date_from, date_to=date_to))



@admin_bp.route('/client/create', methods=['POST'])
@admin_required
def create_client():
    name = request.form.get('name')
    phone = request.form.get('phone')
    password = request.form.get('password')
    if User.query.filter_by(phone=phone).first():
        flash("Errore: Questo numero di telefono appartiene già ad un utente registrato.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))
    new_client = User(name=name, phone=phone, role='client')
    new_client.set_password(password)
    db.session.add(new_client)
    db.session.commit()
    flash(f"Cliente '{name}' registrato con successo.", "success")
    return redirect(url_for('admin.index', active_tab='users_management'))

def parse_format_weight_kg(item_string, qty):
    lower_str = item_string.lower()
    if 'g' in lower_str or 'gr' in lower_str:
        digits = "".join([c for c in lower_str if c.isdigit()])
        if digits:
            grams = float(digits)
            if grams >= 100 and grams <= 5000: return (grams / 1000.0) * qty
    if 'piccolo' in lower_str or 'vaschetta' in lower_str: return 0.25 * qty
    elif 'grande' in lower_str: return 1.0 * qty
    return 1.0 * qty

def parse_admin_format_price(full_item_name, product_obj):
    if not product_obj or not product_obj.sizes_raw: return product_obj.price_per_kg if product_obj else 0.0
    for fmt in product_obj.sizes_raw.split(','):
        clean_fmt = fmt.strip()
        if not clean_fmt: continue
        if ":" in clean_fmt:
            try:
                fmt_label, raw_price = clean_fmt.split(":")
                if fmt_label.strip().lower() in full_item_name.lower(): return float(raw_price)
            except ValueError: continue
        else:
            if clean_fmt.lower() in full_item_name.lower():
                weight_str = "".join([c for c in clean_fmt if c.isdigit()])
                if weight_str and ('g' in clean_fmt.lower() or 'gr' in clean_fmt.lower()):
                    grams = float(weight_str)
                    return (grams / 1000.0) * product_obj.price_per_kg
    return product_obj.price_per_kg

@admin_bp.route('/product/save_all', methods=['POST'])
@admin_required
def save_all_products():
    try:
        product_ids = request.form.getlist('product_id')
        names = request.form.getlist('name')
        prices = request.form.getlist('price')
        formats_list = request.form.getlist('formats')
        for i in range(len(product_ids)):
            p_id = int(product_ids[i])
            product = Product.query.get(p_id)
            if product:
                product.name = names[i].strip()
                product.price_per_kg = float(prices[i]) if prices[i] else 0.0
                product.sizes_raw = formats_list[i].strip()
        db.session.commit()
        flash("Tutti i prodotti del catalogo sono stati aggiornati con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il salvataggio collettivo: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='catalog'))

@admin_bp.route('/product/add', methods=['POST'])
@admin_required
def add_product():
    try:
        name = request.form.get('name')
        price = float(request.form.get('price', 0.0))
        formats = request.form.get('formats', '')
        new_product = Product(name=name, price_per_kg=price, sizes_raw=formats, available=True)
        db.session.add(new_product)
        db.session.commit()
        flash(f"Prodotto '{name}' aggiunto!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='catalog'))

@admin_bp.route('/product/delete/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        db.session.delete(product)
        db.session.commit()
        flash(f"Prodotto '{product.name}' eliminato.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='catalog'))

@admin_bp.route('/database/reset_orders', methods=['POST'])
@admin_required
def reset_orders():
    try:
        Order.query.delete()
        db.session.commit()
        flash("Storico ordini azzerato con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante lo svuotamento degli ordini: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='reset_data'))

@admin_bp.route('/database/reset_clients', methods=['POST'])
@admin_required
def reset_clients():
    try:
        User.query.filter_by(role='client').delete()
        db.session.commit()
        flash("Anagrafica clienti svuotata con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione dei clienti: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='reset_data'))



@admin_bp.route('/profile/admin/password', methods=['POST'])
@admin_required
def change_admin_password():
    from flask import current_app
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    if old_password != current_app.config.get('ADMIN_PASSWORD'):
        flash("Errore: La password attuale non è corretta.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))
    if not new_password or len(new_password.strip()) < 6:
        flash("Errore: La nuova password deve contenere almeno 6 caratteri.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))
    current_app.config['ADMIN_PASSWORD'] = new_password.strip()
    flash("Password Amministratore aggiornata con successo per questa sessione!", "success")
    return redirect(url_for('admin.index', active_tab='users_management'))

@admin_bp.route('/client/delete/<int:client_id>', methods=['POST'])
@admin_required
def delete_client(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    try:
        associated_orders = Order.query.filter_by(user_id=client.id).all()
        for o in associated_orders: o.user_id = None
        db.session.delete(client)
        db.session.commit()
        flash(f"Profilo cliente '{client.name}' eliminato.", "warning")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='users_management'))

@admin_bp.route('/client/update/<int:client_id>', methods=['POST'])
@admin_required
def update_client(client_id):
    client = User.query.filter_by(id=client_id, role='client').first_or_404()
    new_name = request.form.get('name')
    new_phone = request.form.get('phone')
    new_password = request.form.get('password')
    try:
        if new_name and new_name.strip(): 
            client.name = new_name.strip()
        if new_phone and new_phone.strip() != client.phone:
            existing = User.query.filter_by(phone=new_phone.strip()).first()
            if existing:
                flash(f"Errore: Il numero {new_phone} appartiene già ad un altro cliente.", "danger")
                return redirect(url_for('admin.index', active_tab='users_management'))
            client.phone = new_phone.strip()
        if new_password and new_password.strip():
            clean_pass = new_password.strip()
            if len(clean_pass) >= 4:
                client.set_password(clean_pass)
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(client, "password_hash")
                flash(f"Password per '{client.name}' modificata con successo!", "success")
            else:
                flash(f"Modifica Fallita: Almeno 4 caratteri richiesta.", "danger")
                return redirect(url_for('admin.index', active_tab='users_management'))
        db.session.commit()
        flash(f"Dati anagrafici di '{client.name}' salvati correttamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='users_management'))
