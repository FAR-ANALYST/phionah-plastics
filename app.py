import io
import csv
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CUSTOMER ROUTES ---

@app.route('/')
def index():
    """Renders the storefront with products grouped by category."""
    try:
        res = supabase.table("products").select("*").execute()
        products = res.data if res.data else []
        categories = {}
        for p in products:
            cat = p.get('category', 'Other')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        print(f"Index Load Error: {e}")
        return "Store temporarily unavailable.", 500

@app.route('/place_order', methods=['POST'])
def place_order():
    """Matches EXACT Supabase columns: username, phone, location, item_name, total_price, amount_paid, status"""
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        # Amount Paid is now collected from the user on index.html
        user_amount_paid = request.form.get('amount_paid')
        
        res_prod = supabase.table("products").select("*").execute()
        selected_items = []
        calculated_total = 0
        
        for p in res_prod.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                item_total = p['price'] * qty
                calculated_total += item_total
                selected_items.append(f"{p['name']} (x{qty})")
        
        if not selected_items:
            return redirect(url_for('index'))

        # Mapping data to match constraints seen in logs
        order_data = {
            "username": username,
            "phone": phone,
            "location": location,
            "item_name": ", ".join(selected_items),
            "total_price": calculated_total,  # Fixed 'total_price' constraint
            "amount_paid": user_amount_paid,   # Fixed 'amount_paid' constraint
            "status": "Pending"
        }
        
        supabase.table("orders").insert(order_data).execute()
        return redirect(url_for('index'))
    except Exception as e:
        print(f"CRITICAL ORDER ERROR: {e}")
        return f"Order failed: {str(e)}. Check Supabase columns.", 500

@app.route('/get_status')
def get_status():
    phone = request.args.get('phone')
    if not phone: return jsonify({"status": "Enter phone"}), 400
    try:
        res = supabase.table("orders").select("status").eq("phone", phone).order("order_id", desc=True).limit(1).execute()
        return jsonify({"status": res.data[0]['status'] if res.data else "No order found"})
    except Exception:
        return jsonify({"status": "System busy"}), 500

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        orders = supabase.table("orders").select("*").order("order_id", desc=True).execute().data
        prods = supabase.table("products").select("*").execute().data
        inv = {}
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inv: inv[cat] = []
            inv[cat].append(p)
        return render_template('admin.html', orders=orders, inventory_by_cat=inv)
    except Exception as e:
        return f"Admin Access Error: {e}", 500

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    file = request.files.get('product_image')
    if file:
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        path = f"products/{filename}"
        supabase.storage.from_("product-images").upload(path, file.read())
        img_url = supabase.storage.from_("product-images").get_public_url(path)
        
        data = {
            "name": request.form.get('name'),
            "category": request.form.get('category'),
            "price": int(request.form.get('price')),
            "description": request.form.get('description', ''),
            "image_url": img_url
        }
        supabase.table("products").insert(data).execute()
    return redirect(url_for('admin'))

@app.route('/edit_product/<int:id>', methods=['POST'])
def edit_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    update_data = {
        "name": request.form.get('name'),
        "price": int(request.form.get('price')),
        "category": request.form.get('category')
    }
    file = request.files.get('product_image')
    if file and file.filename != '':
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        path = f"products/{filename}"
        supabase.storage.from_("product-images").upload(path, file.read())
        update_data["image_url"] = supabase.storage.from_("product-images").get_public_url(path)
    supabase.table("products").update(update_data).eq("id", id).execute()
    return redirect(url_for('admin'))

@app.route('/delete_product/<int:id>')
def delete_product(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", id).execute()
    return redirect(url_for('admin'))

@app.route('/export_orders')
def export_orders():
    if not session.get('logged_in'): return redirect(url_for('login'))
    res = supabase.table("orders").select("*").order("order_id", desc=True).execute().data
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Customer', 'Phone', 'Location', 'Items', 'Required Total', 'Paid', 'Status'])
    for o in res:
        writer.writerow([o.get('order_id'), o.get('username'), o.get('phone'), o.get('location'), o.get('item_name'), o.get('total_price'), o.get('amount_paid'), o.get('status')])
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-disposition": "attachment; filename=orders.csv"})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == 'phiona-plastics':
            session['logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
