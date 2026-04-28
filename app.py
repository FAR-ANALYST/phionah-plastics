import os
import csv
import io
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, session, make_response
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "phionah-plastics-secure-key-2026"

# Supabase Credentials
SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    try:
        response = supabase.table("products").select("*").order("id").execute()
        categories = {}
        for p in response.data:
            cat = p.get('category') or 'Other'
            if cat not in categories: categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        return f"Database Error: {e}"

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username')
        phone = request.form.get('phone')
        location = request.form.get('location')
        
        # Ensure amount_paid is handled safely
        try:
            amount_paid = int(request.form.get('amount_paid', 0))
        except (ValueError, TypeError):
            amount_paid = 0

        response = supabase.table("products").select("*").execute()
        selected_items = []
        total_price = 0

        # FIX: Robust quantity parsing to prevent crashes on empty/invalid input
        for p in response.data:
            item_qty = 0
            qty_val = request.form.get(f"qty_{p['id']}")
            if qty_val:
                try:
                    item_qty = int(qty_val)
                except ValueError:
                    item_qty = 0
            
            if item_qty > 0:
                total_price += (p['price'] * item_qty)
                selected_items.append(f"{p['name']} x{item_qty}")
        
        if not selected_items:
            return "Error: No items selected. Please go back and add products.", 400

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
        
        # Ensure receipt.html exists in your templates folder
        return render_template('receipt.html', order=res.data[0])
    except Exception as e:
        return f"Order Submission Error: {e}", 500

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    try:
        # FIX: Using "Shipped" to ensure database constraint compliance
        supabase.table("orders").update({"status": "Shipped"}).eq("order_id", order_id).execute()
        return redirect(url_for('admin'))
    except Exception as e:
        return f"Status Update Error: {e}", 500

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    # Fetch orders
    orders_res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    
    # Fetch products and group by category for the management tab
    prod_res = supabase.table("products").select("*").order("category").execute()
    inventory_by_cat = {}
    for p in prod_res.data:
        cat = p.get('category') or 'Other'
        if cat not in inventory_by_cat: inventory_by_cat[cat] = []
        inventory_by_cat[cat].append(p)
        
    return render_template('admin.html', 
                           orders=orders_res.data, 
                           inventory_by_cat=inventory_by_cat)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == "phiona" and request.form.get('password') == "phiona-plastics":
            session['logged_in'] = True
            return redirect(url_for('admin'))
        return "Invalid Credentials"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("products").delete().eq("id", product_id).execute()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
