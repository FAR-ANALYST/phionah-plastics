import io
import csv
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "phionah-secure-key-2026"

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
    """Handles order placement and calculates totals on the server for security."""
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        
        # Fetch current products to verify prices and build order string
        res_prod = supabase.table("products").select("*").execute()
        selected_items = []
        total_price = 0
        
        for p in res_prod.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                item_total = p['price'] * qty
                total_price += item_total
                selected_items.append(f"{p['name']} (x{qty})")
        
        if not selected_items:
            return redirect(url_for('index'))

        order_data = {
            "username": username,
            "phone": phone,
            "location": location,
            "item_name": ", ".join(selected_items),
            "total_price": total_price,
            "status": "Pending"
        }
        
        # INSERT order - Note: Ensure RLS is disabled or policy is set in Supabase
        supabase.table("orders").insert(order_data).execute()
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Order Placement Error: {e}")
        return "Error placing order. Please contact Phionah directly.", 500

@app.route('/get_status')
def get_status():
    """JSON route for the tracking feature on index.html."""
    phone = request.args.get('phone')
    if not phone:
        return jsonify({"status": "Enter phone number"}), 400
    
    try:
        res = supabase.table("orders").select("status")\
            .eq("phone", phone)\
            .order("order_id", desc=True)\
            .limit(1).execute()
            
        if res.data:
            return jsonify({"status": res.data[0]['status']})
        return jsonify({"status": "No order found for this number"})
    except Exception as e:
        return jsonify({"status": "Error checking status"}), 500

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    """Dashboard viewing area for orders and inventory management."""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    try:
        orders = supabase.table("orders").select("*").order("order_id", desc=True).execute().data
        prods = supabase.table("products").select("*").execute().data
        
        inventory_by_cat = {}
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inventory_by_cat:
                inventory_by_cat[cat] = []
            inventory_by_cat[cat].append(p)
            
        return render_template('admin.html', orders=orders, inventory_by_cat=inventory_by_cat)
    except Exception as e:
        print(f"Admin Access Error: {e}")
        return "Internal Error. Verify Supabase table columns.", 500

@app.route('/add_product', methods=['POST'])
def add_product():
    """Adds a new product including image upload to Supabase Storage."""
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
            "description": request.form.get('description'),
            "image_url": img_url
        }
        supabase.table("products").insert(data).execute()
    return redirect(url_for('admin'))

@app.route('/edit_product/<int:id>', methods=['POST'])
def edit_product(id):
    """Updates existing product details. Handles optional image updates."""
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
    """Permanently removes a product from inventory."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", id).execute()
    return redirect(url_for('admin'))

@app.route('/export_orders')
def export_orders():
    """Generates a downloadable CSV of all orders for business records."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Order ID', 'Customer', 'Phone', 'Location', 'Items', 'Total Price', 'Status'])
    
    for o in res.data:
        writer.writerow([
            o.get('order_id'), o.get('username'), o.get('phone'),
            o.get('location'), o.get('item_name'), o.get('total_price'),
            o.get('status')
        ])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=phionah_orders.csv"}
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login handler using established credentials."""
    if request.method == 'POST':
        if request.form.get('username') == 'phiona' and request.form.get('password') == 'phiona-plastics':
            session['logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Clears admin session."""
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # On Render, the port is typically assigned automatically.
    # debug=True is for development; set to False for production.
    app.run(debug=True)
