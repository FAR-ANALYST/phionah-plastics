import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

app = Flask(__name__)

# 1. Retrieve keys
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# 2. Initialize the client OUTSIDE the routes
# If keys are missing, we use None to avoid the NameError
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Failed to connect to Supabase: {e}")

@app.route('/')
def index():
    # 3. Check if supabase exists before using it
    if not supabase:
        return "Database keys are missing or incorrect. Please check Render Environment Variables."
    
    try:
        response = supabase.table("products").select("*").execute()
        product_list = response.data if response.data else []
        return render_template('index.html', products=product_list)
    except Exception as e:
        print(f"Error: {e}")
        return "Internal Error: Could not fetch products."

@app.route('/place_order', methods=['POST'])
def place_order():
    if not supabase: return "Database Error"
    
    username = request.form.get('username')
    location = request.form.get('location')
    product_id = int(request.form.get('product_id'))
    quantity = int(request.form.get('quantity'))
    amount_paid = int(request.form.get('amount_paid'))
    
    product_req = supabase.table("products").select("name, price").eq("id", product_id).single().execute()
    total_price = product_req.data['price'] * quantity
    balance = total_price - amount_paid
    
    order_data = {
        "username": username,
        "location": location,
        "item_name": product_req.data['name'],
        "total_price": total_price,
        "amount_paid": amount_paid,
        "balance": balance,
        "status": "Pending"
    }
    
    response = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=response.data[0])

@app.route('/track', methods=['POST'])
def track():
    if not supabase: return "Database Error"
    order_id = request.form.get('order_id')
    order = supabase.table("orders").select("*").eq("order_id", order_id).execute()
    result = order.data[0] if order.data else None
    return render_template('track.html', order=result)

@app.route('/admin')
def admin():
    if not supabase: return "Database Error"
    orders = supabase.table("orders").select("*").order("order_id").execute()
    return render_template('admin.html', orders=orders.data)

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not supabase: return "Database Error"
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
