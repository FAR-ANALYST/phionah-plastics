import os
from flask import Flask, render_template, request, redirect, url_for
from supabase import create_client, Client

# 1. INITIALIZE FLASK FIRST
app = Flask(__name__)

# 2. DATABASE CREDENTIALS (Corrected URL and Key)
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"

# Initialize the Supabase connection
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Connection Error: {e}")

# 3. ROUTES
@app.route('/')
def index():
    try:
        # Fetch products for the shop
        response = supabase.table("products").select("*").execute()
        return render_template('index.html', products=response.data)
    except Exception as e:
        return f"Database Connection Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    # Collect customer details
    username = request.form.get('username')
    location = request.form.get('location')
    phone = request.form.get('phone')
    amount_paid_input = request.form.get('amount_paid', '0')
    amount_paid = int(amount_paid_input) if amount_paid_input.strip() else 0
    
    # Process multi-item selection
    products_req = supabase.table("products").select("*").execute()
    all_products = products_req.data
    
    selected_items = []
    total_price = 0
    
    for p in all_products:
        # Match each product to its quantity input in the HTML
        qty_input = request.form.get(f"qty_{p['id']}", "0")
        qty = int(qty_input) if qty_input.strip() else 0
        
        if qty > 0:
            total_price += (p['price'] * qty)
            selected_items.append(f"{p['name']} (x{qty})")
    
    # Validation: Ensure they actually picked something
    if not selected_items:
        return "Please go back and select at least one item."

    # Final calculations and preparation
    item_summary = ", ".join(selected_items)
    balance = total_price - amount_paid
    
    order_data = {
        "username": username,
        "location": location,
        "phone": phone,
        "item_name": item_summary,
        "total_price": total_price,
        "amount_paid": amount_paid,
        "balance": balance,
        "status": "Pending"
    }
    
    # Save to Supabase
    response = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=response.data[0])

@app.route('/track', methods=['POST'])
def track():
    # Handle the tracking form
