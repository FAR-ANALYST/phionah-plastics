import os
import io
import csv
import json
from datetime import datetime
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, Response)
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "garphy-secure-key-2026")

# ─────────────────────────────────────────────
#  SUPABASE
# ─────────────────────────────────────────────
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30."
    "DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

CATEGORIES = [
    "TOILETRIES",
    "BEDDINGS",
    "PLASTICS AND KITCHENWARE",
    "CLEANING ESSENTIALS",
]

# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def safe_int(val, default=0):
    try:
        return int(val or default)
    except (ValueError, TypeError):
        return default


def parse_images(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if raw.startswith('['):
            try:
                return json.loads(raw)
            except Exception:
                pass
        if raw:
            return [raw]
    return []


def prepare_orders(raw_list):
    out = []
    for o in (raw_list or []):
        o['item_images']    = parse_images(o.get('item_images'))
        o['item_name']      = o.get('item_name')      or ''
        o['username']       = o.get('username')       or 'Unknown'
        o['phone']          = o.get('phone')          or '—'
        o['location']       = o.get('location')       or '—'
        o['status']         = o.get('status')         or 'ORDER RECEIVED'
        o['notes']          = o.get('notes')          or ''
        o['payment_method'] = o.get('payment_method') or '—'
        o['total_price']    = safe_int(o.get('total_price'))
        o['amount_paid']    = safe_int(o.get('amount_paid'))
        o['balance']        = safe_int(o.get('balance'))
        out.append(o)
    return out


# ─────────────────────────────────────────────
#  CUSTOMER STOREFRONT
# ─────────────────────────────────────────────

@app.route('/')
def index():
    try:
        res      = supabase.table("products").select("*").execute()
        products = res.data if res.data is not None else []

        categories = {}
        for p in products:
            cat = p.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)

        return render_template('index.html', categories=categories)
    except Exception as e:
        print(f"[INDEX ERROR] {e}")
        return "Store temporarily offline. Please try again shortly.", 500


@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username', '').strip()
        phone    = request.form.get('phone',    '').strip()
        location = request.form.get('location', '').strip()
        method   = request.form.get('payment_method', '')
        notes    = request.form.get('notes',    '').strip()
        paid     = safe_int(request.form.get('amount_paid', 0))

        res_prod = supabase.table("products").select("*").execute()
        products = res_prod.data if res_prod.data is not None else []

        selected_items, item_imgs, calc_total = [], [], 0
        for p in products:
            qty = safe_int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                calc_total += p['price'] * qty
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p.get('image_url', ''))

        if not selected_items:
            return redirect(url_for('index'))

        balance = max(0, calc_total - paid)

        result = supabase.table("orders").insert({
            "username":       username,
            "phone":          phone,
            "location":       location,
            "item_name":      ", ".join(selected_items),
            "item_images":    item_imgs,
            "total_price":    calc_total,
            "amount_paid":    paid,
            "balance":        balance,
            "status":         "ORDER RECEIVED",
            "payment_method": method,
            "notes":          notes,
        }).execute()

        # Get the new order id for receipt
        order_id = result.data[0]['id'] if result.data else None

        return redirect(url_for(
            'receipt',
            order_id=order_id,
        ))
    except Exception as e:
        print(f"[PLACE ORDER ERROR] {e}")
        return f"Order failed: {str(e)}", 500


@app.route('/receipt/<int:order_id>')
def receipt(order_id):
    """Shows a printable receipt after order placement."""
    try:
        res   = supabase.table("orders").select("*").eq("id", order_id).execute()
        order = prepare_orders(res.data)[0] if res.data else None
        if not order:
            return redirect(url_for('index'))
        return render_template('receipt.html', order=order)
    except Exception as e:
        print(f"[RECEIPT ERROR] {e}")
        return redirect(url_for('index'))


@app.route('/check_status')
def check_status():
    """JSON endpoint — returns latest order status for a phone number."""
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({"error": "Please enter your phone number."})
    try:
        res = (
            supabase.table("orders")
            .select("id, status, item_name, total_price, created_at")
            .eq("phone", phone)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            o = res.data[0]
            return jsonify({
                "found":       True,
                "status":      o.get('status', ''),
                "item_name":   o.get('item_name', ''),
                "total_price": o.get('total_price', 0),
                "order_id":    o.get('id', ''),
            })
        return jsonify({"found": False, "error": "No order found for this number."})
    except Exception as e:
        print(f"[CHECK STATUS ERROR] {e}")
        return jsonify({"error": "Status check failed — please try again."})


# ─────────────────────────────────────────────
#  ADMIN PANEL
# ─────────────────────────────────────────────

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    load_error = None
    orders     = []
    inv_by_cat = {}

    try:
        order_res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
        orders    = prepare_orders(order_res.data)
        print(f"[ADMIN] {len(orders)} order(s) loaded.")
    except Exception as e:
        load_error = str(e)
        print(f"[ADMIN ORDER ERROR] {e}")

    try:
        prod_res = supabase.table("products").select("*").execute()
        prods    = prod_res.data if prod_res.data is not None else []
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inv_by_cat:
                inv_by_cat[cat] = []
            inv_by_cat[cat].append(p)
    except Exception as e:
        print(f"[ADMIN PRODUCT ERROR] {e}")

    # ── Dashboard stats ──
    total_revenue = sum(o['total_price'] for o in orders)
    total_orders  = len(orders)
    paid_revenue  = sum(o['amount_paid'] for o in orders)
    outstanding   = sum(o['balance']     for o in orders)
    status_counts = {
        "ORDER RECEIVED": sum(1 for o in orders if o['status'] == 'ORDER RECEIVED'),
        "ON THE WAY":     sum(1 for o in orders if o['status'] == 'ON THE WAY'),
        "DELIVERED":      sum(1 for o in orders if o['status'] == 'DELIVERED'),
    }

    return render_template(
        'admin.html',
        orders=orders,
        inventory_by_cat=inv_by_cat,
        load_error=load_error,
        categories=CATEGORIES,
        stats={
            "total_revenue": total_revenue,
            "total_orders":  total_orders,
            "paid_revenue":  paid_revenue,
            "outstanding":   outstanding,
            "status_counts": status_counts,
        },
    )


@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    """Update order status — never crashes, always returns JSON or redirects."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        new_status = request.form.get('status', '').strip()
        if not new_status:
            print(f"[UPDATE STATUS] Empty status received for order {order_id}")
            return redirect(url_for('admin', tab='orders'))

        supabase.table("orders") \
                .update({"status": new_status}) \
                .eq("id", order_id) \
                .execute()
        print(f"[STATUS OK] Order {order_id} → {new_status}")
    except Exception as e:
        print(f"[UPDATE STATUS ERROR] order {order_id}: {e}")
    # Always redirect — never crash
    return redirect(url_for('admin', tab='orders'))


@app.route('/edit_product/<int:p_id>', methods=['POST'])
def edit_product(p_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        update_data = {
            "name":        request.form.get('name',        '').strip(),
            "price":       safe_int(request.form.get('price')),
            "category":    request.form.get('category',    '').strip(),
            "description": request.form.get('description', '').strip(),
        }
        file = request.files.get('product_image')
        if file and file.filename:
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path     = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            update_data["image_url"] = supabase.storage.from_("product-images").get_public_url(path)
        supabase.table("products").update(update_data).eq("id", p_id).execute()
        print(f"[EDIT] Product {p_id} updated.")
    except Exception as e:
        print(f"[EDIT PRODUCT ERROR] {p_id}: {e}")
    return redirect(url_for('admin', tab='inventory'))


@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        supabase.table("products").delete().eq("id", p_id).execute()
        print(f"[DELETE] Product {p_id} removed.")
    except Exception as e:
        print(f"[DELETE PRODUCT ERROR] {p_id}: {e}")
    return redirect(url_for('admin', tab='inventory'))


@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        file = request.files.get('product_image')
        if file and file.filename:
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path     = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            img_url  = supabase.storage.from_("product-images").get_public_url(path)
            supabase.table("products").insert({
                "name":        request.form.get('name',        '').strip(),
                "category":    request.form.get('category',    '').strip(),
                "price":       safe_int(request.form.get('price')),
                "description": request.form.get('description', '').strip(),
                "image_url":   img_url,
            }).execute()
            print("[ADD] Product added.")
    except Exception as e:
        print(f"[ADD PRODUCT ERROR] {e}")
    return redirect(url_for('admin', tab='inventory'))


@app.route('/export_orders_csv')
def export_orders_csv():
    """Download all orders as a CSV file."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        res    = supabase.table("orders").select("*").order("created_at", desc=True).execute()
        orders = prepare_orders(res.data)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "Order ID", "Date", "Customer Name", "Phone", "Location",
            "Items Ordered", "Total Price (UGX)", "Amount Paid (UGX)",
            "Balance (UGX)", "Payment Method", "Status", "Notes"
        ])

        for o in orders:
            writer.writerow([
                o.get('id', ''),
                o.get('created_at', '')[:19].replace('T', ' ') if o.get('created_at') else '',
                o.get('username', ''),
                o.get('phone', ''),
                o.get('location', ''),
                o.get('item_name', ''),
                o.get('total_price', 0),
                o.get('amount_paid', 0),
                o.get('balance', 0),
                o.get('payment_method', ''),
                o.get('status', ''),
                o.get('notes', ''),
            ])

        output.seek(0)
        filename = f"garphy_orders_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        print(f"[CSV EXPORT ERROR] {e}")
        return redirect(url_for('admin', tab='orders'))


# ─────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form.get('password') == 'phiona-plastics':
            session['logged_in'] = True
            return redirect(url_for('admin'))
        error = "Incorrect password. Please try again."
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
