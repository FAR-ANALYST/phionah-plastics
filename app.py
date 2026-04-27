import os
import csv
import io
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, make_response
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
        # Fetch all products and group them by category
        response = supabase.table("products").select("*").order("id").execute()
        categories = {}
        for p in response.data:
            cat = p.get('category') or 'Other'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/track_order', methods=['POST'])
def track_order():
    """Handles order status lookups."""
    try:
        order_id = request.form.get('order_id')
        res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
        if res.data:
            return render_template('receipt.html', order=res.data[0])
        return "Order not found. <a href='/'>Go back</a>"
    except Exception as e:
        return f"Tracking Error: {e}"

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    products = supabase.table("products").select("*").order("id").execute()
    return render_template('admin.html', orders=orders.data, products=products.data)

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
            "name": request.form.get('name'), 
            "category": request.form.get('category'),
            "description": request.form.get('description'), 
            "price": int(request.form.get('price')),
            "image_url": image_url
        }
        supabase.table("products").insert(product_data).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Upload Error: {e}"

@app.route('/edit_product/<int:product_id>', methods=['POST'])
def edit_product(product_id):
    """Updates existing product details and optionally the image."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        # Get existing product to retain image if no new one is uploaded
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

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        supabase.table("products").delete().eq("id", product_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Delete Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username, location, phone = request.form.get('username'), request.form.get('location'), request.form.get('phone')
        raw_amount = request.form.get('amount_paid', '0')
        amount_paid = int(raw_amount) if raw_amount.isdigit() else 0
        
        products_req = supabase.table("products").select("*").execute()
        selected_items, total_price = [], 0
        
        for p in products_req.data:
            qtys = request.form.getlist(f"qty_{p['id']}")
            total_qty = sum(int(q) if q.isdigit() else 0 for q in qtys)
            if total_qty > 0:
                total_price += (p['price'] * total_qty)
                selected_items.append(f"{p['name']} x{total_qty}")
        
        order_data = {
            "username": username, "location": location, "phone": phone,
            "item_name": ", ".join(selected_items), "total_price": total_price,
            "amount_paid": amount_paid, "balance": total_price - amount_paid, "status": "Pending"
        }
        res = supabase.table("orders").insert(order_data).execute()
        return render_template('receipt.html', order=res.data[0])
    except Exception as e:
        return f"Order Error: {e}", 500

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == "phiona" and request.form.get('password') == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
