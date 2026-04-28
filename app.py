import io
import csv
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Secure key for session management (Login/Admin)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

# --- SUPABASE CONFIGURATION ---
# Connects to the Galphy Home Essentials project on Supabase
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CUSTOMER ROUTES ---

@app.route('/')
def index():
    """Fetches all products and organizes them by category for the store dropdowns."""
    try:
        res = supabase.table("products").select("*").execute()
        products = res.data if res.data else []
        categories = {}
        for p in products:
            cat = p.get('category', 'Essentials')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        print(f"Index Error: {e}")
        return "Store temporarily unavailable.", 500

@app.route('/place_order', methods=['POST'])
def place_order():
    """
    Processes orders, calculates totals, and captures specific product images 
    for the admin order view.
    """
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        method = request.form.get('payment_method')
        
        # Ensure 'amount_paid' is an integer to satisfy Supabase constraints
        try:
            paid = int(request.form.get('amount_paid', 0))
        except (ValueError, TypeError):
            paid = 0
        
        # Verify pricing and capture image URLs for the admin display
        res_prod = supabase.table("products").select("*").execute()
        selected_items = []
        item_imgs = []
        calc_total = 0
        
        for p in res_prod.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                calc_total += (p['price'] * qty)
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p['image_url']) # Captures item images for admin
        
        if not selected_items:
            return redirect(url_for('index'))

        # Construct data to fix "null value in column balance" and other constraints
        order_data = {
            "username": username,
            "phone": phone,
            "location": location,
            "item_name": ", ".join(selected_items),
            "item_images": item_imgs,      # New feature: display images for admin
            "total_price": calc_total,
            "amount_paid": paid,
            "balance": max(0, calc_total - paid),
            "status": "ORDER RECEIVED",     # Default initial status
            "payment_method": method
        }
        
        supabase.table("orders").insert(order_data).execute()
        
        # Triggers the success overlay and receipt logic on index.html
        return redirect(url_for('index', 
                                success='true', 
                                method=method,
                                user=username, 
                                items=order_data['item_name'], 
                                total=calc_total))
    except Exception as e:
        print(f"ORDER ERROR: {e}")
        return f"Order failed: {str(e)}", 500

@app.route('/download_receipt')
def download_receipt():
    """Generates the text-based receipt including GTBank and Mobile Money details."""
    user = request.args.get('user', 'Customer')
    items = request.args.get('items', '')
    total = int(request.args.get('total', 0))
    date_str = datetime.now().strftime("%d-%b-%Y %H:%M")

    # Kampala Delivery Logic
    delivery_note = "FREE DELIVERY (Kampala Region)" if total >= 500000 else "Standard Delivery Rate"

    receipt_text = (
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
        f"Delivery:  {delivery_note}\n"
        "------------------------------------------\n"
        "PAYMENT DETAILS:\n"
        "Account:   NAISANGA PHIONA\n"
        "MM/Number: 0703070193\n"
        "GTBank:    211/154424/1/5003/0\n"
        "==========================================\n"
        "   Thank you for your business!\n"
        "=========================================="
    )
    
    return Response(
        receipt_text,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename=GalphyReceipt_{user}.txt"}
    )

@app.route('/get_status')
def get_status():
    """Allows customers to check their order progress via their phone number."""
    phone = request.args.get('phone')
    if not phone: return jsonify({"status": "Enter phone number"})
    try:
        res = supabase.table("orders").select("status").eq("phone", phone).order("created_at", desc=True).limit(1).execute()
        return jsonify({"status": res.data[0]['status'] if res.data else "No order found"})
    except:
        return jsonify({"status": "Server busy"})

# --- ADMIN ROUTES ---

@app.route('/admin')
def admin():
    """Main dashboard for Phionah to manage orders and track statuses."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    orders = supabase.table("orders").select("*").order("created_at", desc=True).execute().data
    products = supabase.table("products").select("*").execute().data
    return render_template('admin.html', orders=orders, products=products)

@app.route('/add_product', methods=['POST'])
def add_product():
    """Adds products with image cropping support via frontend storage upload."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    file = request.files.get('product_image')
    if file:
        filename = secure_filename(f"{datetime.now().timestamp()}.png")
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

@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    """Admin-only status updates: ORDER RECEIVED, ON THE WAY, or DELIVERED."""
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_status = request.form.get('status')
    supabase.table("orders").update({"status": new_status}).eq("id", order_id).execute()
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
