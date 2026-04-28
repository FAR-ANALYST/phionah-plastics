import io
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Secure key for session management
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CUSTOMER STOREFRONT ROUTES ---

@app.route('/')
def index():
    """Fetches and groups products for the shop home page."""
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
        print(f"Index Error: {e}")
        return "Store temporarily offline.", 500

@app.route('/place_order', methods=['POST'])
def place_order():
    """Handles order submission and calculates totals/balances."""
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        method = request.form.get('payment_method')
        
        try:
            paid = int(request.form.get('amount_paid', 0))
        except:
            paid = 0
        
        res_prod = supabase.table("products").select("*").execute()
        selected_items, item_imgs, calc_total = [], [], 0
        
        for p in res_prod.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                calc_total += (p['price'] * qty)
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p['image_url'])
        
        if not selected_items:
            return redirect(url_for('index'))

        order_data = {
            "username": username, "phone": phone, "location": location,
            "item_name": ", ".join(selected_items), "item_images": item_imgs,
            "total_price": calc_total, "amount_paid": paid,
            "balance": max(0, calc_total - paid), "status": "ORDER RECEIVED",
            "payment_method": method
        }
        
        supabase.table("orders").insert(order_data).execute()
        return redirect(url_for('index', success='true', user=username, total=calc_total))
    except Exception as e:
        return f"Order failed: {str(e)}", 500

# --- ADMIN PANEL ROUTES ---

@app.route('/admin')
def admin():
    """Dashboard that handles Tab Switching between Orders and Inventory."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        orders = supabase.table("orders").select("*").order("created_at", desc=True).execute().data
        prods = supabase.table("products").select("*").execute().data
        
        inv_by_cat = {}
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inv_by_cat: inv_by_cat[cat] = []
            inv_by_cat[cat].append(p)
            
        return render_template('admin.html', orders=orders, inventory_by_cat=inv_by_cat)
    except Exception as e:
        return "Dashboard Error", 500

@app.route('/edit_product/<int:p_id>', methods=['POST'])
def edit_product(p_id):
    """Updates product and returns specifically to the Inventory tab."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
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

        supabase.table("products").update(update_data).eq("id", p_id).execute()
        return redirect(url_for('admin', tab='inventory'))
    except Exception as e:
        print(f"Edit Error: {e}")
        return redirect(url_for('admin', tab='inventory'))

@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    """Removes product and returns specifically to the Inventory tab."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        supabase.table("products").delete().eq("id", p_id).execute()
        return redirect(url_for('admin', tab='inventory'))
    except Exception as e:
        print(f"Delete Error: {e}")
        return redirect(url_for('admin', tab='inventory'))

@app.route('/add_product', methods=['POST'])
def add_product():
    """Adds a new product and returns specifically to the Inventory tab."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        file = request.files.get('product_image')
        if file:
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            img_url = supabase.storage.from_("product-images").get_public_url(path)
            
            supabase.table("products").insert({
                "name": request.form.get('name'), 
                "category": request.form.get('category'),
                "price": int(request.form.get('price')), 
                "image_url": img_url
            }).execute()
        return redirect(url_for('admin', tab='inventory'))
    except:
        return redirect(url_for('admin', tab='inventory'))

@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    """Updates order status and returns to the Orders tab."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_status = request.form.get('status')
    supabase.table("orders").update({"status": new_status}).eq("id", order_id).execute()
    return redirect(url_for('admin', tab='orders'))

# --- AUTH ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and request.form.get('password') == 'phiona-plastics':
        session['logged_in'] = True
        return redirect(url_for('admin'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    # Render uses environment variables for Port
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
