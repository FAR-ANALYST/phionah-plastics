import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

# CRITICAL: Define 'app' first so the routes below can use it
app = Flask(__name__)

# Corrected URL and Key
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"

# Initialize the client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").execute()
        product_list = response.data if response.data else []
        return render_template('index.html', products=product_list)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    username = request.form.get('username')
    location = request.form.get('location')
    amount_paid = int(request.form.get('amount_paid', 0))
    
    # Fetch all products to match against quantities
    products_req = supabase.table("products").select("*").execute()
    all_products = products_req.data
    
    selected_items = []
    total_price = 0
    
    for p in all_products:
        # Get quantity for each product (defaults to 0 if empty)
        qty_input = request.form.get(f"qty_{p['id']}", "0")
        qty = int(qty_input) if qty_input.strip() else 0
        
        if qty > 0:
            item_total = p['price'] * qty
            total_price += item_total
            selected_items.append(f"{p['name']} (x{qty})")
    
    if not selected_items:
        return "Please select at least one item with a quantity greater than 0."

    balance = total_price - amount_paid
    item_summary = ", ".join(selected_items)
    
    order_data = {
        "username": username,
        "location": location,
        "item_name": item_summary,
        "total_price": total_price,
        "amount_paid": amount_paid,
        "balance": balance,
        "status": "Pending"
    }
    
    response = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=response.data[0])

@app.route('/track', methods=['POST'])
def track():
    order_id = request.form.get('order_id')
    order = supabase.table("orders").select("*").eq("order_id", order_id).execute()
    result = order.data[0] if order.data else None
    return render_template('track.html', order=result)

@app.route('/admin')
def admin():
    orders = supabase.table("orders").select("*").order("order_id").execute()
    return render_template('admin.html', orders=orders.data)

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
