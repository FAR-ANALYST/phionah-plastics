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
        return "Store temporarily unavailable.", 500

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        method = request.form.get('payment_method')
        
        # Robust conversion to prevent NULL values in database
        try:
            paid = int(request.form.get('amount_paid', 0))
        except:
            paid = 0
        
        res_prod = supabase.table("products").select("*").execute()
        selected_items = []
        calc_total = 0
        
        for p in res_prod.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                calc_total += (p['price'] * qty)
                selected_items.append(f"{p['name']} (x{qty})")
        
        if not selected_items:
            return redirect(url_for('index'))

        # Ensure all numeric fields are present to fix the 'null value' error
        order_data = {
            "username": username,
            "phone": phone,
            "location": location,
            "item_name": ", ".join(selected_items),
            "total_price": calc_total,
            "amount_paid": paid,
            "balance": max(0, calc_total - paid), # Fix for balance null error
            "status": "Pending"
        }
        
        supabase.table("orders").insert(order_data).execute()
        
        # Pass parameters to frontend for conditional receipt display
        return redirect(url_for('index', 
                                success='true', 
                                method=method,
                                user=username, 
                                items=order_data['item_name'], 
                                total=calc_total))
    except Exception as e:
        return f"Order failed: {str(e)}", 500

@app.route('/download_receipt')
def download_receipt():
    """Generates the text receipt for Mobile Money users only."""
    user = request.args.get('user', 'Customer')
    items = request.args.get('items', 'Home Essentials')
    total = int(request.args.get('total', 0))
    date_str = datetime.now().strftime("%d-%b-%Y %H:%M")

    # Delivery Rule: Free for 500k+ in Kampala
    delivery_info = "FREE (Kampala Region)" if total >= 500000 else "Standard Rate"

    receipt_content = (
        "==========================================\n"
        "        GALPHY HOME ESSENTIALS\n"
        "==========================================\n"
        f"Date:      {date_str}\n"
        f"Customer:  {user}\n"
        "------------------------------------------\n"
        f"Items:     {items}\n"
        "------------------------------------------\n"
        f"TOTAL:     UGX {total:,}\n"
        "------------------------------------------\n"
        f"Delivery:  {delivery_info}\n"
        "Payment:   Mobile Money (Verified)\n"
        "Contact:   NAISANGA PHIONA (0703070193)\n"
        "==========================================\n"
    )
    
    return Response(
        receipt_content,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename=Galphy_Receipt_{user}.txt"}
    )

@app.route('/get_status')
def get_status():
    phone = request.args.get('phone')
    if not phone: return jsonify({"status": "Missing phone"}), 400
    res = supabase.table("orders").select("status").eq("phone", phone).order("created_at", desc=True).limit(1).execute()
    return jsonify({"status": res.data[0]['status'] if res.data else "Not found"})

# --- ADMIN ROUTES (Maintained) ---

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    orders = supabase.table("orders").select("*").order("created_at", desc=True).execute().data
    prods = supabase.table("products").select("*").execute().data
    inv = {}
    for p in prods:
        cat = p.get('category', 'Other')
        if cat not in inv: inv[cat] = []
        inv[cat].append(p)
    return render_template('admin.html', orders=orders, inventory_by_cat=inv)

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'): return redirect(url_for('login'))
    file = request.files.get('product_image')
    if file:
        filename = secure_filename(f"{datetime.now().timestamp()}_{file.filename}")
        path = f"products/{filename}"
        supabase.storage.from_("product-images").upload(path, file.read())
        img_url = supabase.storage.from_("product-images").get_public_url(path)
        
        product_data = {
            "name": request.form.get('name'),
            "category": request.form.get('category'),
            "price": int(request.form.get('price')),
            "description": request.form.get('description', ''),
            "image_url": img_url
        }
        supabase.table("products").insert(product_data).execute()
    return redirect(url_for('admin'))

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
