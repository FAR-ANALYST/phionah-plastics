import os
from datetime import datetime  # Added for unique filename generation
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "phionah-plastics-secure-key-2026"

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

import io
import csv
from flask import Response

@app.route('/export_orders')
def export_orders():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    # 1. Fetch orders from Supabase
    res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    orders = res.data

    # 2. Setup CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # 3. Header Row (Matches your new 'Notes' column)
    writer.writerow(['ID', 'Customer', 'Phone', 'Location', 'Items', 'Special Instructions', 'Total', 'Status'])

    # 4. Fill rows
    for o in orders:
        writer.writerow([
            o.get('order_id'),
            o.get('username'),
            o.get('phone'),
            o.get('location'),
            o.get('item_name'),
            o.get('notes'), # The new instructions field
            o.get('total_price'),
            o.get('status')
        ])

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=orders_export.csv"}
    )

# --- CUSTOMER ROUTES ---

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").order("id").execute()
        categories = {}
        for p in response.data:
            cat = p.get('category') or 'Other'
            if cat not in categories: categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        
        try:
            amount_paid = int(request.form.get('amount_paid', 0))
        except (ValueError, TypeError):
            amount_paid = 0

        response = supabase.table("products").select("*").execute()
        selected_items = []
        total_price = 0

        for p in response.data:
            qty_val = request.form.get(f"qty_{p['id']}")
            try:
                item_qty = int(qty_val) if qty_val else 0
            except ValueError:
                item_qty = 0
            
            if item_qty > 0:
                total_price += (p['price'] * item_qty)
                selected_items.append(f"{p['name']} x{item_qty}")
        
        if not selected_items:
            return "Error: No items selected. Please go back.", 400

        order_data = {
            "username": username, 
            "location": location, 
            "phone": phone,
            "item_name": ", ".join(selected_items), 
            "total_price": total_price,
            "amount_paid": amount_paid, 
            "balance": total_price - amount_paid, 
            "status": "Pending"
        }
        
        res = supabase.table("orders").insert(order_data).execute()
        return render_template('receipt.html', order=res.data[0])
    except Exception as e:
        return f"Order Submission Error: {e}", 500

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    orders_res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    prod_res = supabase.table("products").select("*").order("category").execute()
    
    inventory_by_cat = {}
    for p in prod_res.data:
        cat = p.get('category') or 'Other'
        if cat not in inventory_by_cat: inventory_by_cat[cat] = []
        inventory_by_cat[cat].append(p)
        
    return render_template('admin.html', orders=orders_res.data, inventory_by_cat=inventory_by_cat)

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        name = request.form.get('name')
        category = request.form.get('category')
        description = request.form.get('description')
        price = int(request.form.get('price'))

        file = request.files.get('product_image')
        if not file: return "Error: Image required", 400

        # UNIQUE FILENAME FIX: Prevents "Duplicate Resource" error
        filename = secure_filename(file.filename)
        unique_filename = f"{datetime.now().timestamp()}_{filename}"
        file_path = f"products/{unique_filename}"
        
        supabase.storage.from_("product-images").upload(file_path, file.read())
        image_url = supabase.storage.from_("product-images").get_public_url(file_path)

        product_data = {"name": name, "category": category, "description": description, "price": price, "image_url": image_url}
        supabase.table("products").insert(product_data).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Failed to add product: {e}", 500

@app.route('/edit_product/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        update_data = {
            "name": request.form.get('name'),
            "category": request.form.get('category'),
            "description": request.form.get('description'),
            "price": int(request.form.get('price'))
        }

        file = request.files.get('product_image')
        if file and file.filename != '':
            # UNIQUE FILENAME FIX: Prevents "Duplicate Resource" error
            filename = secure_filename(file.filename)
            unique_filename = f"{datetime.now().timestamp()}_{filename}"
            file_path = f"products/{unique_filename}"
            
            supabase.storage.from_("product-images").upload(file_path, file.read())
            update_data["image_url"] = supabase.storage.from_("product-images").get_public_url(file_path)

        supabase.table("products").update(update_data).eq("id", product_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Failed to edit: {e}", 500

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        supabase.table("orders").update({"status": "Shipped"}).eq("order_id", order_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Update Error: {e}", 500

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", product_id).execute()
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == "phiona" and request.form.get('password') == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid Credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
