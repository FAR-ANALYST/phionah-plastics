import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

# ─────────────────────────────────────────────
#  SUPABASE CONFIGURATION
# ─────────────────────────────────────────────
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30."
    "DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ─────────────────────────────────────────────
#  CUSTOMER STOREFRONT
# ─────────────────────────────────────────────

@app.route('/')
def index():
    """Main store page — fetches and groups products by category."""
    try:
        res      = supabase.table("products").select("*").execute()
        products = res.data if res.data is not None else []

        categories = {}
        for p in products:
            cat = p.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)

        return render_template(
            'index.html',
            categories=categories,
            success=request.args.get('success'),
            method=request.args.get('method'),
        )
    except Exception as e:
        print(f"Index Error: {e}")
        return "Store temporarily offline. Please try again later.", 500


@app.route('/place_order', methods=['POST'])
def place_order():
    """Handles order submission — saves items, notes, payment info to Supabase."""
    try:
        username = request.form.get('username', '').strip()
        phone    = request.form.get('phone',    '').strip()
        location = request.form.get('location', '').strip()
        method   = request.form.get('payment_method', '')
        notes    = request.form.get('notes',    '').strip()

        try:
            paid = int(request.form.get('amount_paid', 0) or 0)
        except (ValueError, TypeError):
            paid = 0

        res_prod = supabase.table("products").select("*").execute()
        products = res_prod.data if res_prod.data is not None else []

        selected_items, item_imgs, calc_total = [], [], 0

        for p in products:
            try:
                qty = int(request.form.get(f"qty_{p['id']}", 0) or 0)
            except (ValueError, TypeError):
                qty = 0
            if qty > 0:
                calc_total += p['price'] * qty
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p.get('image_url', ''))

        if not selected_items:
            return redirect(url_for('index'))

        order_data = {
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
        }

        supabase.table("orders").insert(order_data).execute()

        return redirect(url_for(
            'index',
            success='true',
            method=method,
            user=username,
            total=calc_total,
        ))
    except Exception as e:
        print(f"Order Placement Error: {e}")
        return f"Order failed: {str(e)}", 500


@app.route('/get_status')
def get_status():
    """Live order-status lookup for customers."""
    phone = request.args.get('phone', '').strip()
    if not phone:
        return jsonify({"status": "Please enter your phone number."})
    try:
        res = (
            supabase.table("orders")
            .select("status")
            .eq("phone", phone)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        status = res.data[0]['status'] if res.data else "No order found for this number."
        return jsonify({"status": status})
    except Exception as e:
        print(f"Status Check Error: {e}")
        return jsonify({"status": "Status check failed. Try again."})


# ─────────────────────────────────────────────
#  ADMIN PANEL
# ─────────────────────────────────────────────

@app.route('/admin')
def admin():
    """Full dashboard — Orders tab + Inventory tab."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        order_res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
        orders    = order_res.data if order_res.data is not None else []

        prod_res  = supabase.table("products").select("*").execute()
        prods     = prod_res.data  if prod_res.data  is not None else []

        inv_by_cat = {}
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inv_by_cat:
                inv_by_cat[cat] = []
            inv_by_cat[cat].append(p)

        return render_template('admin.html', orders=orders, inventory_by_cat=inv_by_cat)

    except Exception as e:
        print(f"Admin Load Error: {e}")
        return render_template('admin.html', orders=[], inventory_by_cat={})


@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    """Updates delivery status — wrapped in try/except so it NEVER crashes."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        new_status = request.form.get('status', 'ORDER RECEIVED')
        supabase.table("orders") \
                .update({"status": new_status}) \
                .eq("id", order_id) \
                .execute()
    except Exception as e:
        print(f"Update Status Error (order {order_id}): {e}")
    return redirect(url_for('admin', tab='orders'))


@app.route('/edit_product/<int:p_id>', methods=['POST'])
def edit_product(p_id):
    """Updates product name, price, category, description, and optional image."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        update_data = {
            "name":        request.form.get('name',        '').strip(),
            "price":       int(request.form.get('price') or 0),
            "category":    request.form.get('category',    '').strip(),
            "description": request.form.get('description', '').strip(),
        }

        file = request.files.get('product_image')
        if file and file.filename != '':
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path     = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            update_data["image_url"] = supabase.storage \
                                               .from_("product-images") \
                                               .get_public_url(path)

        supabase.table("products").update(update_data).eq("id", p_id).execute()

    except Exception as e:
        print(f"Edit Product Error (id {p_id}): {e}")

    return redirect(url_for('admin', tab='inventory'))


@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    """Permanently removes a product."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        supabase.table("products").delete().eq("id", p_id).execute()
    except Exception as e:
        print(f"Delete Product Error (id {p_id}): {e}")
    return redirect(url_for('admin', tab='inventory'))


@app.route('/add_product', methods=['POST'])
def add_product():
    """Adds a brand-new product including description."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    try:
        file = request.files.get('product_image')
        if file and file.filename != '':
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path     = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            img_url  = supabase.storage.from_("product-images").get_public_url(path)

            supabase.table("products").insert({
                "name":        request.form.get('name',        '').strip(),
                "category":    request.form.get('category',    '').strip(),
                "price":       int(request.form.get('price') or 0),
                "description": request.form.get('description', '').strip(),
                "image_url":   img_url,
            }).execute()
    except Exception as e:
        print(f"Add Product Error: {e}")

    return redirect(url_for('admin', tab='inventory'))


# ─────────────────────────────────────────────
#  AUTHENTICATION
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


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
