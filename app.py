import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

app = Flask(__name__)

# Corrected URL and Key fallback
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://vzeznnntgcqzdwnfqwtra.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk")

# Securely initialize Supabase
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Connection Error: {e}")

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").execute()
        return render_template('index.html', products=response.data)
    except Exception as e:
        return f"Database Connection Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    # Collect form data
    username = request.form.get('username')
    location = request.form.get('location')
    product_id = int(request.form.get('product_id'))
    quantity = int(request.form.get('quantity'))
    amount_paid = int(request.form.get('amount_paid'))
    
    # Calculate math
    product = supabase.table("products").select("name, price").eq("id", product_id).single().execute()
    total = product.data['price'] * quantity
    balance = total - amount_paid
    
    order_data = {
        "username": username, "location": location, "item_name": product.data['name'],
        "total_price": total, "amount_paid": amount_paid, "balance": balance, "status": "Pending"
    }
    
    res = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=res.data[0])

@app.route('/track', methods=['POST'])
def track():
    order_id = request.form.get('order_id')
    res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
    return render_template('track.html', order=res.data[0] if res.data else None)

@app.route('/admin')
def admin():
    res = supabase.table("orders").select("*").order("order_id").execute()
    return render_template('admin.html', orders=res.data)

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
