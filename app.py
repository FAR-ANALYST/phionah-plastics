import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").order("id").execute()
        return render_template('index.html', products=response.data)
    except Exception as e:
        return f"Database Connection Error: {e}"

@app.route('/admin')
def admin():
    try:
        orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
        products = supabase.table("products").select("*").order("id").execute()
        return render_template('admin.html', orders=orders.data, products=products.data)
    except Exception as e:
        return f"Admin Error: {e}"

@app.route('/add_product', methods=['POST'])
def add_product():
    try:
        name = request.form.get('name')
        price = int(request.form.get('price'))
        file = request.files.get('image')

        if file:
            filename = secure_filename(file.filename)
            file_content = file.read()
            # Ensure the 'product-images' bucket exists in Supabase Storage!
            storage_path = f"items/{filename}"
            
            # Uploading to Supabase Storage
            supabase.storage.from_("product-images").upload(storage_path, file_content)
            
            # Get Public URL for the database
            img_url = supabase.storage.from_("product-images").get_public_url(storage_path)
            
            # Insert into Products table
            supabase.table("products").insert({
                "name": name, 
                "price": price, 
                "image_url": img_url
            }).execute()
            
        return redirect(url_for('admin'))
    except Exception as e:
        # This will show you the exact error (e.g., Bucket Not Found) instead of a generic 500
        return f"Upload Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username')
        location = request.form.get('location')
        phone = request.form.get('phone')
        amount_paid = int(request.form.get('amount_paid', 0))
        
        products_req = supabase.table("products").select("*").execute()
        selected_items = []
        total_price = 0
        
        for p in products_req.data:
            qty = int(request.form.get(f"qty_{p['id']}", 0))
            if qty > 0:
                total_price += (p['price'] * qty)
                selected_items.append(f"{p['name']} (x{qty})")
        
        if not selected_items: return "Please select an item."

        order_data = {
            "username": username, "location": location, "phone": phone,
            "item_name": ", ".join(selected_items), "total_price": total_price,
            "amount_paid": amount_paid, "balance": total_price - amount_paid, "status": "Pending"
        }
        res = supabase.table("orders").insert(order_data).execute()
        return render_template('receipt.html', order=res.data[0])
    except Exception as e:
        return f"Order Error: {e}"

@app.route('/track', methods=['POST'])
def track():
    order_id = request.form.get('order_id')
    try:
        res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
        return render_template('track.html', order=res.data[0] if res.data else None)
    except Exception as e:
        return f"Tracking Error: {e}"

@app.route('/delete_product/<int:p_id>')
def delete_product(p_id):
    supabase.table("products").delete().eq("id", p_id).execute()
    return redirect(url_for('admin'))

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
