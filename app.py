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
    """Normalise item_images regardless of how Supabase returns it."""
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
        return [raw] if raw else []
    return []


def prepare_orders(raw_list):
    """Sanitise every order dict so the template never raises a KeyError."""
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


def fetch_orders():
    """
    Try to fetch orders in three stages so a missing column never
    blocks the whole admin page.

    Returns (orders_list, error_string_or_None)
    """
    # Stage 1 — preferred: ordered by created_at
    try:
        res = (supabase.table("orders")
               .select("*")
               .order("created_at", desc=True)
               .execute())
        if res.data is not None:
            print(f"[ORDERS] Loaded {len(res.data)} order(s) (ordered).")
            return prepare_orders(res.data), None
    except Exception as e1:
        print(f"[ORDERS stage-1 fail] {e1}")

    # Stage 2 — fallback: no ordering (avoids missing-column errors)
    try:
        res = supabase.table("orders").select("*").execute()
        if res.data is not None:
            print(f"[ORDERS] Loaded {len(res.data)} order(s) (unordered).")
            return prepare_orders(res.data), None
    except Exception as e2:
        print(f"[ORDERS stage-2 fail] {e2}")
        return [], str(e2)

    return [], "Unknown error — check Render logs."


def fetch_products():
    """Fetch products, return (list, error_or_None)."""
    try:
        res = supabase.table("products").select("*").execute()
        data = res.data if res.data is not None else []
        print(f"[PRODUCTS] Loaded {len(data)} product(s).")
        return data, None
    except Exception as e:
        print(f"[PRODUCTS error] {e}")
        return [], str(e)


# ─────────────────────────────────────────────
#  DEBUG ROUTE  (admin-only, remove in production if desired)
# ─────────────────────────────────────────────

@app.route('/admin/debug')
def admin_debug():
    """
    Shows raw Supabase responses so you can diagnose column/RLS issues.
    Visit: https://your-app.onrender.com/admin/debug
    """
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    results = {}

    # Test orders table
    for attempt, fn in [
        ("orders_ordered",   lambda: supabase.table("orders").select("*").order("created_at", desc=True).limit(3).execute()),
        ("orders_plain",     lambda: supabase.table("orders").select("*").limit(3).execute()),
        ("orders_cols",      lambda: supabase.table("orders").select("id,username,phone,status").limit(1).execute()),
        ("products_plain",   lambda: supabase.table("products").select("*").limit(3).execute()),
    ]:
        try:
            r = fn()
            results[attempt] = {"ok": True, "count": len(r.data or []), "sample": (r.data or [])[:1]}
        except Exception as ex:
            results[attempt] = {"ok": False, "error": str(ex)}

    return jsonify(results)


# ─────────────────────────────────────────────
#  CUSTOMER STOREFRONT
# ─────────────────────────────────────────────

@app.route('/')
def index():
    try:
        prods, _ = fetch_products()
        categories = {}
        for p in prods:
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

        prods, _ = fetch_products()
        selected_items, item_imgs, calc_total = [], [], 0
        for p in prods:
            qty = safe_int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                calc_total += p['price'] * qty
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p.get('image_url', ''))

        if not selected_items:
            return redirect(url_for('index'))

        result = supabase.table("orders").insert({
            "username":       username,
            "phone":          phone,
            "location":       location,
            "item_name":      ", ".join(selected_items),
            "item_images":    item_imgs,
            "total_price":    calc_total,
            "amount_paid":    paid,
            "balance":        max(0, calc_total - paid),
            "status":         "ORDER RECEIVED",
            "payment_method": method,
            "notes":          notes,
        }).execute()

        order_id = result.data[0]['id'] if result.data else None
        return redirect(url_for('receipt', order_id=order_id))
    except Exception as e:
        print(f"[PLACE ORDER ERROR] {e}")
        return f"Order failed: {str(e)}", 500


@app.route('/receipt/<int:order_id>')
def receipt(order_id):
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
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({"error": "Please enter your phone number."})
    try:
        # Try ordered first, fall back to plain select
        try:
            res = (supabase.table("orders")
                   .select("id, status, item_name, total_price, created_at")
                   .eq("phone", phone)
                   .order("created_at", desc=True)
                   .limit(1)
                   .execute())
        except Exception:
            res = (supabase.table("orders")
                   .select("id, status, item_name, total_price")
                   .eq("phone", phone)
                   .limit(1)
                   .execute())

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
        return jsonify({"error": f"Check failed: {str(e)}"})


# ─────────────────────────────────────────────
#  ADMIN PANEL
# ─────────────────────────────────────────────

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    orders,     load_error    = fetch_orders()
    prods,      product_error = fetch_products()

    inv_by_cat = {}
    for p in prods:
        cat = p.get('category', 'Other')
        if cat not in inv_by_cat:
            inv_by_cat[cat] = []
        inv_by_cat[cat].append(p)

    # Combine errors for display
    all_errors = []
    if load_error:    all_errors.append(f"Orders: {load_error}")
    if product_error: all_errors.append(f"Products: {product_error}")

    stats = {
        "total_revenue": sum(o['total_price'] for o in orders),
        "total_orders":  len(orders),
        "paid_revenue":  sum(o['amount_paid'] for o in orders),
        "outstanding":   sum(o['balance']     for o in orders),
        "status_counts": {
            "ORDER RECEIVED": sum(1 for o in orders if o['status'] == 'ORDER RECEIVED'),
            "ON THE WAY":     sum(1 for o in orders if o['status'] == 'ON THE WAY'),
            "DELIVERED":      sum(1 for o in orders if o['status'] == 'DELIVERED'),
        },
    }

    return render_template(
        'admin.html',
        orders=orders,
        inventory_by_cat=inv_by_cat,
        load_error=" | ".join(all_errors) if all_errors else None,
        categories=CATEGORIES,
        stats=stats,
    )


@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        new_status = (request.form.get('status') or '').strip()
        if not new_status:
            print(f"[UPDATE STATUS] Empty status for order {order_id} — skipped.")
            return redirect(url_for('admin', tab='orders'))
        supabase.table("orders") \
                .update({"status": new_status}) \
                .eq("id", order_id) \
                .execute()
        print(f"[STATUS OK] Order {order_id} → '{new_status}'")
    except Exception as e:
        print(f"[UPDATE STATUS ERROR] order {order_id}: {e}")
    # Always redirect — never let the browser see a crash
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
            update_data["image_url"] = (supabase.storage
                                        .from_("product-images")
                                        .get_public_url(path))
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
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        orders, _ = fetch_orders()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Order ID", "Date", "Customer Name", "Phone", "Location",
            "Items Ordered", "Total Price (UGX)", "Amount Paid (UGX)",
            "Balance (UGX)", "Payment Method", "Status", "Notes"
        ])
        for o in orders:
            date_raw = o.get('created_at', '')
            date_str = date_raw[:19].replace('T', ' ') if date_raw else ''
            writer.writerow([
                o.get('id', ''),
                date_str,
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
