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

def cleanup_old_orders():
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        supabase.table("orders").delete().lt("created_at", cutoff_date).execute()
    except Exception as e:
        print(f"Cleanup Error: {e}")

@app.route('/')
def index():
    cleanup_old_orders()
    try:
        # Fetch all products to display on the homepage
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

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        file = request.files.get('product_image')
        image_url = ""
        if file:
            filename = secure_filename(file.filename)
            file_path = f"inventory/{datetime.now().timestamp()}_{filename}"
            file_content = file.read()
            # Upload to your existing 'product-images' bucket
            supabase.storage.from_("product-images").upload(file_path, file_content)
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

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    products = supabase.table("products").select("*").order("id").execute()
    return render_template('admin.html', orders=orders.data, products=products.data)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == "phiona" and request.form.get('password') == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
