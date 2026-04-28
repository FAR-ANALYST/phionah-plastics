import io
import csv
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Secure key for session management
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

# --- SUPABASE CONFIGURATION ---
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CUSTOMER ROUTES ---

@app.route('/')
def index():
    """Main store page: fetches and groups products by category."""
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
    """Handles order submission, including payment method and image arrays."""
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        method = request.form.get('payment_method')
        
        try:
            paid = int(request.form.get('amount_paid', 0))
        except (ValueError, TypeError):
            paid = 0
        
        # Verify cart items and calculate total
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
            "username": username,
            "phone": phone,
            "location": location,
            "item_name": ", ".join(selected_items),
            "item_images": item_imgs, # Saved as text array
            "total_price": calc_total,
            "amount_paid": paid,
            "balance": max(0, calc_total - paid),
            "status": "ORDER RECEIVED",
            "payment_method": method
        }
        
        supabase.table("orders").insert(order_data).execute()
        return redirect(url_for('index', 
                                success='true', 
                                method=method, 
                                user=username, 
                                items=order_data['item_name'], 
                                total=calc_total))
    except Exception as e:
        print(f"Order Placement Error: {e}")
        return f"Order failed: {str(e)}", 500

@app.route('/get_status')
def get_status():
    """Allows customers to track their live order status."""
    phone = request.args.get('phone')
    if not phone: return jsonify({"status": "Enter phone number"})
    try:
        res = supabase.table("orders").select("status").eq("phone", phone).order("created_at", desc=True).limit(1).execute()
        return jsonify({"status": res.data[0]['status'] if res.data else "No order found"})
    except:
        return jsonify({"status": "Status check failed"})

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    """Comprehensive dashboard for Orders and Inventory Management."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        orders = supabase.table("orders").select("*").order("created_at", desc=True).execute().data
        prods = supabase.table("products").select("*").execute().data
        
        # Group products for the inventory tab
        inv_by_cat = {}
        for p in prods:
            cat = p.get('category', 'Other')
            if cat not in inv_by_cat: inv_by_cat[cat] = []
            inv_by_cat[cat].append(p)
            
        return render_template('admin.html', orders=orders, inventory_by_cat=inv_by_cat)
    except Exception as e:
        print(f"Admin Access Error: {e}")
        return "Dashboard Error", 500

@app.route('/edit_product/<int:p_id>', methods=['POST'])
def edit_product(p_id):
    """Updates product name, price, or category in real-time."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        update_data = {
            "name": request.form.get('name'),
            "price": int(request.form.get('price')),
            "category": request.form.get('category')
        }
        
        # Check if a new image was uploaded
        file = request.files.get('product_image')
        if file and file.filename != '':
            filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
            path = f"products/{filename}"
            supabase.storage.from_("product-images").upload(path, file.read())
            update_data["image_url"] = supabase.storage.from_("product-images").get_public_url(path)

        supabase.table("products").update(update_data).eq("id", p_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Edit Error: {e}")
        return redirect(url_for('admin'))

@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    """Removes a product from the shop (Trash Can functionality)."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        supabase.table("products").delete().eq("id", p_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        print(f"Delete Error: {e}")
        return redirect(url_for('admin'))

@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    """Changes order status for customer tracking."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_status = request.form.get('status')
    supabase.table("orders").update({"status": new_status}).eq("id", order_id).execute()
    return redirect(url_for('admin'))

@app.route('/add_product', methods=['POST'])
def add_product():
    """Adds a completely new product to the shop."""
    if not session.get('logged_in'): return redirect(url_for('login'))
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
    return redirect(url_for('admin'))

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
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
