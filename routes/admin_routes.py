from flask import Blueprint, render_template, request, url_for, redirect, flash, session, Response
from extensions import db
from models import Product, Order, User
from datetime import datetime, date
from functools import wraps
import random
import calendar
import csv
import io
import json


admin_bp = Blueprint('admin', __name__)
SYSTEM_CONFIG_PHONES = ('_whatsapp_config', '_admin_config')

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
    # 🌟 FETCH WHATSAPP CONFIG RETAINER ROW
    whatsapp_row = User.query.filter_by(phone='_whatsapp_config').first()
    whatsapp_numbers_config_string = whatsapp_row.name if whatsapp_row else ""
    whatsapp_enabled = (whatsapp_row.price_category == 'ENABLED') if whatsapp_row else True

    catalog_products = Product.query.order_by(db.func.lower(Product.name).asc()).all()
    client_list = User.query.filter_by(role='client').order_by(User.name.asc()).all()

    active_tab = request.args.get('active_tab', 'orders')
    
    filter_status = request.args.get('status', '')  
    filter_client_id = request.args.get('client_id', '') 
    filter_date_from = request.args.get('date_from', '') 
    filter_date_to = request.args.get('date_to', '')     
    
    filter_start_date = request.args.get('start_date', '')
    filter_end_date = request.args.get('end_date', '')
    filter_product = request.args.get('product_name', '')
    filter_unpaid_delivered = request.args.get('non_salda_consegnati', '')
    
    analytics_client_id = request.args.get('analytics_client_id', '')
    analytics_payment_status = request.args.get('analytics_payment_status', '')

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
    
    for o in admin_orders:
        if o.client and "(" in o.client and ")" in o.client:
            try:
                name_part, rest = o.client.split("(", 1)
                phone_part = rest.replace(")", "").strip()
                o.formatted_client_name = name_part.strip()
                o.formatted_client_phone = phone_part
            except Exception:
                o.formatted_client_name = o.client
                o.formatted_client_phone = ""
        else:
            o.formatted_client_name = o.client if o.client else "Vendita Diretta / Banco"
            o.formatted_client_phone = ""

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

    total_revenue = 0.0
    paid_revenue = 0.0
    unpaid_revenue = 0.0
    all_unfiltered_orders = Order.query.all()
    for o in all_unfiltered_orders:
        if o.status == 'Annullato':
            continue
        total_revenue += o.total
        if o.payment_status == 'Saldato':
            paid_revenue += o.total
        else:
            unpaid_revenue += o.total

    # 📂 Overwrite your admin index matching calculation loops with this structure:
    product_summary = {}
    grand_total_qty = 0
    grand_total_kg = 0.0
    grand_total_revenue = 0.0

    for o in admin_orders:
        if o.status == 'Annullato':
            continue
            
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

        if analytics_client_id:
            if analytics_client_id == 'banco' and o.user_id is not None:
                continue
            elif analytics_client_id != 'banco' and o.user_id != int(analytics_client_id):
                continue

        if analytics_payment_status and o.payment_status != analytics_payment_status:
            continue

        # Extract assigned pricing layer context dynamically
        order_client_category = 'Privato'
        if o.user_id:
            buyer_user = User.query.get(o.user_id)
            if buyer_user:
                order_client_category = buyer_user.price_category


        if o.items:
            for item in o.items.split(','):
                item = item.strip()
                if not item or 'x' not in item: continue
                try:
                    qty_str, full_name = item.split('x', 1)
                    qty = int(qty_str.strip())
                    full_name = full_name.strip()
                    
                    # 🌟 FIX 1: Sort by name length descending so "Mozzarella Cassa" is checked before "Mozzarella"
                    sorted_catalog = sorted(catalog_products, key=lambda x: len(x.name), reverse=True)
                    
                    matched_prod_obj = None
                    for p in sorted_catalog:
                        if p.name.lower() in full_name.lower():
                            matched_prod_obj = p
                            break
                    
                    p_name = matched_prod_obj.name if matched_prod_obj else full_name
                    
                    if not filter_product or filter_product.strip().lower() == p_name.strip().lower():
                        computed_weight = parse_format_weight_kg(full_name, qty)
                        
                        # 🌟 FIX 2: Direct matrix parsing from the actual matched database item row object rules string
                        unit_price = 0.0
                        if matched_prod_obj and matched_prod_obj.sizes_raw:
                            rules_dict = {}
                            
                            # Clear whitespace and parse category options cleanly

                            for rule in matched_prod_obj.sizes_raw.split(","):
                                if ":" in rule:
                                    try:
                                        k, v = rule.split(":", 1)
                                        rules_dict[k.strip().lower()] = float(v.strip())
                                    except (ValueError, IndexError):
                                        continue  # Skips malformed category rules safely
                                                        
                            target_key = str(order_client_category).strip().lower()
                            if target_key in rules_dict:
                                unit_price = rules_dict[target_key]
                            elif 'privato' in rules_dict:
                                unit_price = rules_dict['privato']
                        
                        # Dynamic fallback if pricing extraction returns zero
                        if unit_price == 0.0:
                            # 🧮 Fallback calculations attempt to extract price if it was saved inside pricing rules as a single numeric flat price string
                            if matched_prod_obj and matched_prod_obj.sizes_raw and ":" not in matched_prod_obj.sizes_raw:
                                try:
                                    unit_price = float(matched_prod_obj.sizes_raw.strip())
                                except ValueError:
                                    unit_price = 5.0
                            else:
                                unit_price = 5.0  
                            
                        computed_revenue = unit_price * qty
                        
                        # 🌟 FIX 3: Extract the layout size label text straight out of parentheses inside full_name 
                        # This ensures it shows "(12 Kg)" instead of defaulting to product.price_per_kg text labels
                        fmt_label_extracted = ""
                        if "(" in full_name and ")" in full_name:
                            fmt_label_extracted = full_name.split("(")[-1].split(")")[0].strip()
                        else:
                            fmt_label_extracted = matched_prod_obj.price_per_kg if matched_prod_obj else ""
                            
                        display_row_name = f"{p_name} ({fmt_label_extracted})"
                        
                        if display_row_name not in product_summary:
                            product_summary[display_row_name] = {'qty': 0, 'kg': 0.0, 'revenue': 0.0}
                        
                        product_summary[display_row_name]['qty'] += qty
                        product_summary[display_row_name]['kg'] += computed_weight
                        product_summary[display_row_name]['revenue'] += computed_revenue
                        
                        grand_total_qty += qty
                        grand_total_kg += computed_weight
                        grand_total_revenue += computed_revenue
                        
                except ValueError: 
                    continue

    # ================= MONTHLY CLIENT LEDGER (SCHEDA MENSILE) =================
    monthly_client_id = request.args.get('monthly_client_id', '')
    monthly_year = int(request.args.get('monthly_year', date.today().year))
    monthly_month = int(request.args.get('monthly_month', date.today().month))
    group1_products = request.args.getlist('group1')
    group2_products = request.args.getlist('group2')

    monthly_rows = []
    group1_total_kg = 0.0
    group2_total_kg = 0.0
    selected_monthly_client_name = ""

    if active_tab == 'monthly_ledger' and monthly_client_id:
        if monthly_client_id == 'banco':
            selected_monthly_client_name = "Vendita Diretta / Banco"
        else:
            c_obj = User.query.get(int(monthly_client_id))
            selected_monthly_client_name = c_obj.name if c_obj else "Cliente"

        # Determine exact number of days in the chosen month/year
        _, num_days = calendar.monthrange(monthly_year, monthly_month)
        month_prefix = f"{monthly_year:04d}-{monthly_month:02d}-"

        # Fetch only Consegnato orders for this client and month
        ledger_query = Order.query.filter(
            Order.status == 'Consegnato',
            Order.date.startswith(month_prefix)
        )
        if monthly_client_id == 'banco':
            ledger_query = ledger_query.filter(Order.user_id == None)
        else:
            ledger_query = ledger_query.filter_by(user_id=int(monthly_client_id))

        month_orders = ledger_query.all()

        # Map daily weights: day_int -> {'g1': float, 'g2': float}
        daily_map = {d: {'g1': 0.0, 'g2': 0.0} for d in range(1, num_days + 1)}
        sorted_catalog = sorted(catalog_products, key=lambda x: len(x.name), reverse=True)

        for o in month_orders:
            try:
                day_num = int(o.date.split('-')[2])
            except Exception:
                continue
            if day_num not in daily_map or not o.items:
                continue

            for item in o.items.split(','):
                item = item.strip()
                if not item or 'x' not in item:
                    continue
                try:
                    qty_str, full_name = item.split('x', 1)
                    qty = int(qty_str.strip())
                    full_name = full_name.strip()

                    matched_prod = next((p for p in sorted_catalog if p.name.lower() in full_name.lower()), None)
                    p_name = matched_prod.name if matched_prod else full_name
                    item_kg = parse_format_weight_kg(full_name, qty)

                    if p_name in group1_products:
                        daily_map[day_num]['g1'] += item_kg
                    if p_name in group2_products:
                        daily_map[day_num]['g2'] += item_kg
                except ValueError:
                    continue

        for d in range(1, num_days + 1):
            g1_val = daily_map[d]['g1']
            g2_val = daily_map[d]['g2']
            group1_total_kg += g1_val
            group2_total_kg += g2_val
            monthly_rows.append({
                'day_str': f"{d:02d}/{monthly_month:02d}/{monthly_year}",
                'g1_kg': f"{g1_val:.2f}" if g1_val > 0 else "",
                'g2_kg': f"{g2_val:.2f}" if g2_val > 0 else ""
            })


    count_query = Order.query
    if filter_date_from:
        count_query = count_query.filter(Order.date >= filter_date_from)
    if filter_date_to:
        count_query = count_query.filter(Order.date <= filter_date_to)
    if filter_client_id:
        if filter_client_id == 'banco':
            count_query = count_query.filter(Order.user_id == None)
        else:
            count_query = count_query.filter_by(user_id=int(filter_client_id))

    all_current_orders = count_query.all()
    
    counters = {
        'all': len([o for o in all_current_orders if o.status != 'Annullato']),
        'ricezione': len([o for o in all_current_orders if o.status == 'Da Confermare']),
        'confermato': len([o for o in all_current_orders if o.status == 'Confermato']),
        'pronto': len([o for o in all_current_orders if o.status == 'Pronto']),
        'consegnato': len([o for o in all_current_orders if o.status == 'Consegnato' and o.payment_status == 'Saldato']),
        'non_salda': len([o for o in all_current_orders if o.status == 'Consegnato' and o.payment_status == 'Da Saldare'])
    }

    # 📲 OPTIONAL CLIENT WHATSAPP CONFIRMATION PAYLOAD
    wa_client_confirm_data = None
    confirm_order_id = request.args.get('whatsapp_confirm_order_id', '').strip()
    if whatsapp_enabled and confirm_order_id:
        confirmed_order = Order.query.filter_by(id=confirm_order_id).first()
        if confirmed_order and confirmed_order.user_id:
            target_client = User.query.get(confirmed_order.user_id)
            if target_client and target_client.phone:
                digits_only = "".join([c for c in target_client.phone if c.isdigit()])
                # Skip generic blueprint phones (1111, 2222, 3333, 4444)
                if len(digits_only) >= 8:
                    if not digits_only.startswith('39') and len(digits_only) <= 10:
                        digits_only = '39' + digits_only
                    try:
                        euro_date = datetime.strptime(str(confirmed_order.date).strip(), "%Y-%m-%d").strftime("%d.%m.%Y")
                    except Exception:
                        euro_date = confirmed_order.date
                    items_lines = "\n".join([f"- {i.strip()}" for i in (confirmed_order.items or "").split(',') if i.strip()])
                    msg_text = (
                        f"*Caseificio Vicedomini - Ordine Confermato*\n"
                        f"*ID:* {confirmed_order.id}\n"
                        f"*Cliente:* {target_client.name}\n"
                        f"*Data Consegna:* {euro_date}\n"
                        f"*Orario Previsto:* {confirmed_order.time or 'Da definire'}\n"
                        f"*Prodotti:*\n{items_lines}\n"
                        f"*Totale:* EUR {confirmed_order.total:.2f}"
                    )
                    wa_client_confirm_data = {
                        'order_id': confirmed_order.id,
                        'client_name': target_client.name,
                        'phone': digits_only,
                        'message': msg_text
                    }

    return render_template(
        'admin.html',
        orders=admin_orders,
        products=catalog_products,
        clients=client_list,
        active_tab=active_tab,
        view='admin',
        counters=counters,
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
        analytics_client_id=analytics_client_id,
        analytics_payment_status=analytics_payment_status,
        catalog_map=catalog_map,
        non_salda_consegnati=filter_unpaid_delivered,
        current_status=filter_status,      
        current_client_id=filter_client_id,
        current_date_from=filter_date_from, 
        current_date_to=filter_date_to,
        whatsapp_numbers_config_string=whatsapp_numbers_config_string,
        monthly_client_id=monthly_client_id,
        monthly_year=monthly_year,
        monthly_month=monthly_month,
        group1_products=group1_products,
        group2_products=group2_products,
        monthly_rows=monthly_rows,
        group1_total_kg=group1_total_kg,
        group2_total_kg=group2_total_kg,
        selected_monthly_client_name=selected_monthly_client_name,
        whatsapp_enabled=whatsapp_enabled,

    )


@admin_bp.route('/order/update_status', methods=['POST'])
@admin_required
def update_order_status():
    order_id = request.form.get('order_id')
    new_status = request.form.get('new_status')
    
    status = request.form.get('status', '')
    client_id = request.form.get('client_id', '')
    date_from = request.form.get('date_from', '')
    date_to = request.form.get('date_to', '')
    
    order = Order.query.filter_by(id=order_id).first_or_404()
    try:
        if new_status == 'Confermato':
            order.time = request.form.get('delivery_time')
        order.status = new_status
        db.session.commit()
        flash(f"Ordine #{order_id} aggiornato!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
        
    confirm_wa_id = order_id if new_status == 'Confermato' else ''
    return redirect(url_for(
        'admin.index',
        active_tab='orders',
        status=status,
        client_id=client_id,
        date_from=date_from,
        date_to=date_to,
        whatsapp_confirm_order_id=confirm_wa_id
    ))
        
    return redirect(url_for('admin.index', active_tab='orders', status=status, client_id=client_id, date_from=date_from, date_to=date_to))

@admin_bp.route('/order/mark_paid', methods=['POST'])
@admin_required
def mark_order_paid():
    order_id = request.form.get('order_id')
    
    status = request.form.get('status', '')
    client_id = request.form.get('client_id', '')
    date_from = request.form.get('date_from', '')
    date_to = request.form.get('date_to', '')
    
    order = Order.query.filter_by(id=order_id).first_or_404()
    try:
        order.payment_status = 'Saldato'
        db.session.commit()
        flash(f"Pagamento per l'ordine #{order_id} registrato come Saldato!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
        
    return redirect(url_for('admin.index', active_tab='orders', status=status, client_id=client_id, date_from=date_from, date_to=date_to))

@admin_bp.route('/order/cancel', methods=['POST'])
@admin_required
def cancel_order():
    order_id = request.form.get('order_id')
    
    status = request.form.get('status', '')
    client_id = request.form.get('client_id', '')
    date_from = request.form.get('date_from', '')
    date_to = request.form.get('date_to', '')
    
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
    category = request.form.get('price_category', 'Privato') # 🌟 Capture form category
    
    if User.query.filter_by(phone=phone).first():
        flash("Errore: Questo numero di telefono appartiene già ad un utente registrato.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))
        
    new_client = User(name=name, phone=phone, role='client', price_category=category)
    new_client.set_password(password)
    db.session.add(new_client)
    db.session.commit()
    flash(f"Cliente '{name}' registrato con successo.", "success")
    return redirect(url_for('admin.index', active_tab='users_management'))

# 📂 Replace your admin view format parsers in routes/admin_routes.py with these:

# 📂 Replace these helper functions at the bottom of routes/admin_routes.py

def parse_format_weight_kg(item_string, qty):
    """
    Safely extracts only the package volume number inside parentheses 
    to prevent quantity prefixes from corrupting the calculation loop arithmetic.
    """
    lower_str = item_string.lower()
    
    # Isolate only the text inside parentheses (e.g., "(12 kg)" -> "12 kg")
    if "(" in lower_str and ")" in lower_str:
        inner_content = lower_str.split("(")[-1].split(")")[0]
    else:
        inner_content = lower_str

    # Extract digits cleanly from just that isolated section
    digits = "".join([c for c in inner_content if c.isdigit() or c == '.'])
    if digits:
        try:
            weight_val = float(digits)
            if 'kg' in lower_str:
                return weight_val * qty
            if 'g' in lower_str or 'gr' in lower_str:
                return (weight_val / 1000.0) * qty
        except ValueError:
            pass
            
    if 'piccolo' in lower_str or 'vaschetta' in lower_str: return 0.25 * qty
    elif 'grande' in lower_str: return 1.0 * qty
    return 1.0 * qty


def parse_admin_format_price(full_item_name, product_obj, client_category='Privato'):
    """
    Extracts the assigned single scalar value rule directly from 
    the active matrix row configuration string layout.
    """
    if not product_obj or not product_obj.sizes_raw: 
        return 0.0
        
    try:
        rules_dict = {}
        # Parse the comma rules string: e.g., "Privato:100.00, Ristorante:90.00"
        for rule in product_obj.sizes_raw.split(","):
            if ":" in rule:
                k, v = rule.split(":", 1)
                rules_dict[k.strip().lower()] = float(v.strip())
        
        target_key = str(client_category).strip().lower()
        
        if target_key in rules_dict: 
            return rules_dict[target_key]
        if 'privato' in rules_dict: 
            return rules_dict['privato']
            
    except Exception:
        pass
        
    return 0.0



# 📂 Overwrite these three catalog management routes inside routes/admin_routes.py:

@admin_bp.route('/product/save_all', methods=['POST'])
@admin_required
def save_all_products():
    try:
        all_products = Product.query.all()
        for product in all_products:
            form_name = request.form.get(f'name_{product.id}')
            form_format_label = request.form.get(f'price_{product.id}') # 🌟 Captures the Formato label string
            form_tier_rules = request.form.get(f'formats_{product.id}')   # Captures the categories price rules string
            
            if form_name is not None:
                product.name = form_name.strip()
            if form_format_label is not None:
                product.price_per_kg = form_format_label.strip() # Saved as string
            if form_tier_rules is not None:
                product.sizes_raw = form_tier_rules.strip()
                
            db.session.add(product)
            
        db.session.commit()
        flash("Tutti i prodotti e formati del listino sono stati aggiornati con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il salvataggio collettivo: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='catalog'))


@admin_bp.route('/product/add', methods=['POST'])
@admin_required
def add_product():
    try:
        name = request.form.get('name')
        format_label = request.form.get('price') # 🌟 Formato text input
        tier_rules = request.form.get('formats') # Rules text input
        
        new_product = Product(name=name, price_per_kg=format_label, sizes_raw=tier_rules, available=True)
        db.session.add(new_product)
        db.session.commit()
        flash(f"Articolo '{name}' con formato '{format_label}' aggiunto con successo!", "success")
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
        User.query.filter(
            User.role == 'client',
            ~User.phone.in_(SYSTEM_CONFIG_PHONES)
        ).delete(synchronize_session=False)
        db.session.commit()
        flash("Anagrafica clienti svuotata con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante l'eliminazione dei clienti: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='reset_data'))

@admin_bp.route('/database/reset_cancelled', methods=['POST'])
@admin_required
def reset_cancelled():
    try:
        Order.query.filter_by(status='Annullato').delete()
        db.session.commit()
        flash("Ordini annullati rimossi con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante la pulizia degli ordini annullati: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='reset_data'))

@admin_bp.route('/database/reset_completed', methods=['POST'])
@admin_required
def reset_completed():
    try:
        Order.query.filter_by(status='Consegnato', payment_status='Saldato').delete()
        db.session.commit()
        flash("Ordini consegnati e saldati archiviati/rimossi con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante la pulizia degli ordini completati: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='reset_data'))

@admin_bp.route('/profile/admin/password', methods=['POST'])
@admin_required
def change_admin_password():
    from flask import current_app
    old_password = request.form.get('old_password', '').strip()
    new_password = request.form.get('new_password', '').strip()

    admin_config = User.query.filter_by(phone='_admin_config').first()

    # Verify current password (check DB override first, fallback to env config)
    if admin_config:
        valid_old = admin_config.check_password(old_password)
    else:
        valid_old = (old_password == current_app.config.get('ADMIN_PASSWORD'))

    if not valid_old:
        flash("Errore: La password attuale non è corretta.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))

    if not new_password or len(new_password) < 6:
        flash("Errore: La nuova password deve contenere almeno 6 caratteri.", "danger")
        return redirect(url_for('admin.index', active_tab='users_management'))

    try:
        if not admin_config:
            admin_config = User(name='Admin Config', phone='_admin_config', role='admin')
            db.session.add(admin_config)
        admin_config.set_password(new_password)
        db.session.commit()
        flash("Password Amministratore salvata in modo permanente!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il salvataggio: {str(e)}", "danger")

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
    new_category = request.form.get('price_category') # 🌟 Capture layout dropdown category
    
    try:
        if new_name and new_name.strip(): 
            client.name = new_name.strip()
        if new_category:
            client.price_category = new_category.strip() # 🌟 Update model tier state
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
        
        db.session.commit()
        flash(f"Dati anagrafici di '{client.name}' salvati correttamente.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore: {str(e)}", "danger")
    return redirect(url_for('admin.index', active_tab='users_management'))

@admin_bp.route('/emergency-override', methods=['GET'])
def emergency_override():
    # 🔒 SECURE RECOVERY TOKEN CHECK
    secret_token = request.args.get('token', '')
    
    # Change 'SecretVicedomini2026' to any secret phrase you want
    if secret_token == 'SecretVicedomini2026':
        session['user_id'] = 0  
        session['user_name'] = "Admin Emergency Recovery"
        session['user_role'] = 'admin'
        session['user_category'] = 'Admin'
        flash("⚡ Accesso di Emergenza Amministratore Eseguito con Successo!", "success")
        return redirect(url_for('admin.index'))
        
    flash("Token di emergenza non valido.", "danger")
    return redirect(url_for('client_bp.login'))

@admin_bp.route('/settings/whatsapp/save', methods=['POST'])
@admin_required
def save_notification_settings():
    numbers_string = request.form.get('whatsapp_numbers', '').strip()
    is_enabled = 'ENABLED' if request.form.get('whatsapp_enabled') == '1' else 'DISABLED'
    
    # Locate or create the special persistent config tracker row
    config_row = User.query.filter_by(phone='_whatsapp_config').first()
    if not config_row:
        config_row = User(name=numbers_string, phone='_whatsapp_config', role='admin', price_category=is_enabled)
        config_row.set_password('system_secure_config_holder')
        db.session.add(config_row)
    else:
        config_row.name = numbers_string
        config_row.price_category = is_enabled
        
    try:
        db.session.commit()
        flash("Impostazioni notifiche WhatsApp aggiornate con successo!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il salvataggio: {str(e)}", "danger")
        
    return redirect(url_for('admin.index', active_tab='users_management'))

@admin_bp.route('/monthly-ledger/export', methods=['GET'])
@admin_required
def export_monthly_ledger():
    monthly_client_id = request.args.get('monthly_client_id', '')
    monthly_year = int(request.args.get('monthly_year', date.today().year))
    monthly_month = int(request.args.get('monthly_month', date.today().month))
    group1_products = request.args.getlist('group1')
    group2_products = request.args.getlist('group2')

    if not monthly_client_id:
        flash("Seleziona un cliente prima di esportare.", "warning")
        return redirect(url_for('admin.index', active_tab='monthly_ledger'))

    if monthly_client_id == 'banco':
        client_name = "Vendita_Diretta_Banco"
    else:
        c_obj = User.query.get(int(monthly_client_id))
        client_name = c_obj.name.replace(" ", "_") if c_obj else "Cliente"

    _, num_days = calendar.monthrange(monthly_year, monthly_month)
    month_prefix = f"{monthly_year:04d}-{monthly_month:02d}-"

    ledger_query = Order.query.filter(Order.status == 'Consegnato', Order.date.startswith(month_prefix))
    if monthly_client_id == 'banco':
        ledger_query = ledger_query.filter(Order.user_id == None)
    else:
        ledger_query = ledger_query.filter_by(user_id=int(monthly_client_id))

    catalog_products = Product.query.all()
    sorted_catalog = sorted(catalog_products, key=lambda x: len(x.name), reverse=True)
    daily_map = {d: {'g1': 0.0, 'g2': 0.0} for d in range(1, num_days + 1)}

    for o in ledger_query.all():
        try:
            day_num = int(o.date.split('-')[2])
        except Exception:
            continue
        if day_num not in daily_map or not o.items:
            continue
        for item in o.items.split(','):
            item = item.strip()
            if not item or 'x' not in item:
                continue
            try:
                qty_str, full_name = item.split('x', 1)
                qty = int(qty_str.strip())
                full_name = full_name.strip()
                matched_prod = next((p for p in sorted_catalog if p.name.lower() in full_name.lower()), None)
                p_name = matched_prod.name if matched_prod else full_name
                item_kg = parse_format_weight_kg(full_name, qty)
                if p_name in group1_products:
                    daily_map[day_num]['g1'] += item_kg
                if p_name in group2_products:
                    daily_map[day_num]['g2'] += item_kg
            except ValueError:
                continue

    output = io.StringIO()
    # Add Excel separator hint so Excel always splits columns properly
    output.write("sep=;\n")
    writer = csv.writer(output, delimiter=';')
    
    # Include the client and month/year title at the top of the sheet
    writer.writerow([f"Caseificio Vicedomini - Scheda Consegne {monthly_month:02d}/{monthly_year}", f"Cliente: {client_name.replace('_', ' ')}", ""])
    writer.writerow([])

    # Use ' - ' instead of commas inside the header so it never splits columns
    g1_header = "Gruppo 1 (" + " - ".join(group1_products) + ") Kg" if group1_products else "Gruppo 1 (Kg)"
    g2_header = "Gruppo 2 (" + " - ".join(group2_products) + ") Kg" if group2_products else "Gruppo 2 (Kg)"
    writer.writerow(["Data", g1_header, g2_header])

    tot_g1, tot_g2 = 0.0, 0.0
    for d in range(1, num_days + 1):
        g1_v = daily_map[d]['g1']
        g2_v = daily_map[d]['g2']
        tot_g1 += g1_v
        tot_g2 += g2_v
        writer.writerow([
            f"{d:02d}/{monthly_month:02d}/{monthly_year}",
            f"{g1_v:.2f}".replace('.', ',') if g1_v > 0 else "",
            f"{g2_v:.2f}".replace('.', ',') if g2_v > 0 else ""
        ])
    writer.writerow(["TOTALE MESE", f"{tot_g1:.2f}".replace('.', ','), f"{tot_g2:.2f}".replace('.', ',')])

    filename = f"Scheda_{client_name}_{monthly_month:02d}_{monthly_year}.csv"
    return Response(
        output.getvalue().encode('utf-8-sig'),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@admin_bp.route('/database/backup', methods=['GET'])
@admin_required
def export_database_backup():
    try:
        backup_payload = {
            "exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "users": [
                {
                    "id": u.id,
                    "name": u.name,
                    "phone": u.phone,
                    "password_hash": u.password_hash,
                    "role": u.role,
                    "price_category": u.price_category
                }
                for u in User.query.all()
            ],
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price_per_kg": p.price_per_kg,
                    "sizes_raw": p.sizes_raw,
                    "available": p.available
                }
                for p in Product.query.all()
            ],
            "orders": [
                {
                    "id": o.id,
                    "user_id": o.user_id,
                    "client": o.client,
                    "date": o.date,
                    "items": o.items,
                    "total": o.total,
                    "time": o.time,
                    "status": o.status,
                    "payment_status": o.payment_status
                }
                for o in Order.query.all()
            ]
        }

        filename = f"MozzApp_Backup_{datetime.now().strftime('%d_%m_%Y_%H%M')}.json"
        return Response(
            json.dumps(backup_payload, indent=2, ensure_ascii=False),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        flash(f"Errore durante la creazione del backup: {str(e)}", "danger")
        return redirect(url_for('admin.index', active_tab='reset_data'))


@admin_bp.route('/database/restore', methods=['POST'])
@admin_required
def restore_database_backup():
    uploaded_file = request.files.get('backup_file')
    if not uploaded_file or not uploaded_file.filename.endswith('.json'):
        flash("Seleziona un file di backup valido in formato .json.", "danger")
        return redirect(url_for('admin.index', active_tab='reset_data'))

    try:
        data = json.load(uploaded_file)

        # 1. Restore Users & System Configs
        phone_to_new_user_id = {}
        for u_data in data.get("users", []):
            existing_user = User.query.filter_by(phone=u_data["phone"]).first()
            if existing_user:
                phone_to_new_user_id[u_data["id"]] = existing_user.id
                # Sync system configuration rows from backup if present
                if u_data["phone"] in SYSTEM_CONFIG_PHONES:
                    existing_user.name = u_data["name"]
                    existing_user.password_hash = u_data["password_hash"]
                    existing_user.price_category = u_data.get("price_category", existing_user.price_category)
            else:
                new_u = User(
                    name=u_data["name"],
                    phone=u_data["phone"],
                    password_hash=u_data["password_hash"],
                    role=u_data.get("role", "client"),
                    price_category=u_data.get("price_category", "Privato")
                )
                db.session.add(new_u)
                db.session.flush()
                phone_to_new_user_id[u_data["id"]] = new_u.id

        # 2. Restore Products (skip duplicates by name)
        for p_data in data.get("products", []):
            if not Product.query.filter_by(name=p_data["name"]).first():
                new_p = Product(
                    name=p_data["name"],
                    price_per_kg=p_data["price_per_kg"],
                    sizes_raw=p_data.get("sizes_raw"),
                    available=p_data.get("available", True)
                )
                db.session.add(new_p)

        # 3. Restore Orders (skip duplicates by order ID)
        restored_orders_count = 0
        for o_data in data.get("orders", []):
            if not Order.query.filter_by(id=o_data["id"]).first():
                mapped_uid = phone_to_new_user_id.get(o_data.get("user_id"))
                new_o = Order(
                    id=o_data["id"],
                    user_id=mapped_uid,
                    client=o_data["client"],
                    date=o_data.get("date"),
                    items=o_data.get("items"),
                    total=o_data.get("total", 0.0),
                    time=o_data.get("time", ""),
                    status=o_data.get("status", "Da Confermare"),
                    payment_status=o_data.get("payment_status", "Da Saldare")
                )
                db.session.add(new_o)
                restored_orders_count += 1

        db.session.commit()
        flash(f"Ripristino completato! Importati {restored_orders_count} nuovi ordini e sincronizzati clienti e listino.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Errore durante il ripristino del backup: {str(e)}", "danger")

    return redirect(url_for('admin.index', active_tab='reset_data'))
