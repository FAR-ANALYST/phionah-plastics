import os
from flask import Flask, render_template, request, redirect, url_for, session
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
# Secret key is required for sessions (login memory) to work
app.secret_key = "phionah-plastics-secure-key-2026"

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CUSTOMER STOREFRONT ---

@app.route('/')
def index():
    try:
        # Fetch all products
        response = supabase.table("products").select("*").order("id").execute()
        
        # Group products by category for the dropdown/expandable UI
        categories = {}
        for p in response.data:
            cat_name = p.get('category') or 'Uncategorized'
            if cat_name not in categories:
                categories[cat_name] = []
            categories[cat_name].append(p)
            
        return render_template('index.html', categories=categories)
    except Exception as e:
        return f"Storefront Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username')
        location = request.form.get('location')
        phone = request.form.get('phone')
        amount_paid = int(request.form.get('amount_paid', 0))
        
        # Fetch products to calculate total and item names
        products_req = supabase.table("products").select("*").execute()
        selected_items = []
        total_price = 0
        
        for p in products_req.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                total_price += (p['price'] * qty)
                # Include the description (Size) in the order summary
                item_detail = f"{p['name']} ({p.get('description', 'N/A')}) x{qty}"
                selected_items.append(item_detail)
        
        if not selected_items:
            return "Your cart is empty. <a href='/'>Go back</a>"

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
        return f"Order Processing Error: {e}"

# --- ADMIN AUTHENTICATION ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = request.form.get('username')
        pwd = request.form.get('password')
        
        # As requested: username=phiona, password=phiona-plastics
        if user == "phiona" and pwd == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
        else:
            return "Invalid credentials. <a href='/login'>Try again</a>"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# --- PROTECTED ADMIN ACTIONS ---

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    try:
        orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
        products = supabase.table("products").select("*").order("id").execute()
        return render_template('admin.html', orders=orders.data, products=products.data)
    except Exception as e:
        return f"Admin Panel Error: {e}"

@app.route('/add_product', methods=['POST'])
def add_product():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
        
    try:
        cat = request.form.get('category')
        name = request.form.get('name')
        desc = request.form.get('description') # This holds the Size/Detail
        price = int(request.form.get('price'))
        file = request.files.get('image')

        if file:
            filename = secure_filename(file.filename)
            file_content = file.read()
            storage_path = f"items/{filename}"
            
            # Upload to Supabase Storage
            supabase.storage.from_("product-images").upload(storage_path, file_content)
            img_url = supabase.storage.from_("product-images").get_public_url(storage_path)
            
            # Insert into Database with Categories and Descriptions
            supabase.table("products").insert({
                "category": cat,
                "name": name, 
                "description": desc,
                "price": price, 
                "image_url": img_url
            }).execute()
            
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Upload Failed: {e}"

@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", p_id).execute()
    return redirect(url_for('admin'))

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    # Using environment PORT for Render compatibility
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
