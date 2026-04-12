import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

# Initialize Flask
app = Flask(__name__)

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").execute()
        return render_template('index.html', products=response.data)
    except Exception as e:
        return f"Database Connection Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    username = request.form.get('username')
    location = request.form.get('location')
    phone = request.form.get('phone')
    amount_paid_input = request.form.get('amount_paid', '0')
    amount_paid = int(amount_paid_input) if amount_paid_input.strip() else 0
    
    products_req = supabase.table("products").select("*").execute()
    selected_items = []
    total_price = 0
    
    for p in products_req.data:
        qty_input = request.form.get(f"qty_{p['id']}", "0")
        qty = int(qty_input) if qty_input.strip() else 0
        if qty > 0:
            total_price += (p['price'] * qty)
            selected_items.append(f"{p['name']} (x{qty})")
    
    if not selected_items:
        return "Please select at least one item."

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
    
    response = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=response.data[0])

@app.route('/track', methods=['POST'])
def track():
    # FIXED INDENTATION HERE
    order_id = request.form.get('order_id')
    try:
        res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
        order_found = res.data[0] if res.data else None
        return render_template('track.html', order=order_found)
    except Exception as e:
        return f"Tracking Error: {e}"

@app.route('/admin')
def admin():
    res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    return render_template('admin.html', orders=res.data)

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
