import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "phionah-plastics-secure-key-2026"

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    """FIX: Added explicit return for GET requests to prevent TypeError in logs."""
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        if user == "phiona" and pwd == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid Credentials. <a href='/login'>Try again</a>"
    # This ensures the login page actually loads when you visit the URL
    return render_template('login.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    # Fetch data and group inventory by category for a cleaner Admin UI
    orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    products_res = supabase.table("products").select("*").order("id").execute()
    
    inventory_by_cat = {}
    for p in products_res.data:
        cat = p.get('category') or 'Other'
        if cat not in inventory_by_cat: inventory_by_cat[cat] = []
        inventory_by_cat[cat].append(p)

    return render_template('admin.html', orders=orders.data, inventory_by_cat=inventory_by_cat)

@app.route('/track_order', methods=['GET', 'POST'])
def track_order():
    """FIX: Supports both POST (form submission) and GET (page refresh)."""
    if request.method == 'POST':
        order_id = request.form.get('order_id')
        res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
        if res.data:
            return render_template('receipt.html', order=res.data[0])
        return "Order not found. <a href='/'>Go back</a>"
    return redirect(url_for('index'))

@app.route('/edit_product/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        existing = supabase.table("products").select("*").eq("id", product_id).single().execute()
        image_url = existing.data.get('image_url')

        file = request.files.get('product_image')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file_path = f"inventory/{datetime.now().timestamp()}_{filename}"
            supabase.storage.from_("product-images").upload(file_path, file.read())
            image_url = supabase.storage.from_("product-images").get_public_url(file_path)

        update_data = {
            "name": request.form.get('name'),
            "category": request.form.get('category'),
            "description": request.form.get('description'),
            "price": int(request.form.get('price')),
            "image_url": image_url
        }
        supabase.table("products").update(update_data).eq("id", product_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Update Error: {e}"

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        file = request.files.get('product_image')
        image_url = ""
        if file:
            filename = secure_filename(file.filename)
            file_path = f"inventory/{datetime.now().timestamp()}_{filename}"
            supabase.storage.from_("product-images").upload(file_path, file.read())
            image_url = supabase.storage.from_("product-images").get_public_url(file_path)

        product_data = {
            "name": request.form.get('name'), "category": request.form.get('category'),
            "description": request.form.get('description'), "price": int(request.form.get('price')),
            "image_url": image_url
        }
        supabase.table("products").insert(product_data).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Upload Error: {e}"

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", product_id).execute()
    return redirect(url_for('admin'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
