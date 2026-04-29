import os
import pdfkit # Optional: for true PDF generation, but we will use a high-quality Print-to-PDF approach
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, make_response
from supabase import create_client, Client
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "phionah-secure-key-2026")

SUPABASE_URL = "https://vzeznntgcqzdwnfqwtra.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ6ZXpubnRnY3F6ZHduZnF3dHJhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU5ODI5NTMsImV4cCI6MjA5MTU1ODk1M30.DgAjwuAOa46jXdVoq_BglmBiNNP2Rfa_N1Ja3wylhDk"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

@app.route('/')
def index():
    try:
        res = supabase.table("products").select("*").execute()
        products = res.data if res.data is not None else []
        categories = {}
        for p in products:
            cat = p.get('category', 'Other')
            if cat not in categories: categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories, success=request.args.get('success'), order_id=request.args.get('order_id'))
    except Exception as e:
        return "Store offline.", 500

@app.route('/place_order', methods=['POST'])
def place_order():
    try:
        username = request.form.get('username', '').strip()
        phone = request.form.get('phone', '').strip()
        location = request.form.get('location', '').strip()
        method = request.form.get('payment_method', '')
        notes = request.form.get('notes', '').strip()
        paid = int(request.form.get('amount_paid', 0) or 0)

        res_prod = supabase.table("products").select("*").execute()
        products = res_prod.data or []
        selected_items, item_imgs, calc_total = [], [], 0

        for p in products:
            qty = int(request.form.get(f"qty_{p['id']}", 0) or 0)
            if qty > 0:
                calc_total += p['price'] * qty
                selected_items.append(f"{p['name']} (x{qty})")
                item_imgs.append(p.get('image_url', ''))

        if not selected_items: return redirect(url_for('index'))

        order_data = {
            "username": username, "phone": phone, "location": location,
            "item_name": ", ".join(selected_items), "item_images": item_imgs,
            "total_price": calc_total, "amount_paid": paid,
            "balance": max(0, calc_total - paid), "status": "ORDER RECEIVED",
            "payment_method": method, "notes": notes
        }

        # Save order and get the ID for the receipt
        order_res = supabase.table("orders").insert(order_data).execute()
        new_order_id = order_res.data[0]['id']

        return redirect(url_for('index', success='true', order_id=new_order_id))
    except Exception as e:
        return f"Order failed: {str(e)}", 500

@app.route('/receipt/<int:order_id>')
def view_receipt(order_id):
    """Generates a viewable/downloadable receipt for the customer."""
    try:
        res = supabase.table("orders").select("*").eq("id", order_id).execute()
        if not res.data: return "Order not found", 404
        order = res.data[0]
        return render_template('receipt.html', order=order)
    except Exception as e:
        return str(e), 500

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    order_res = supabase.table("orders").select("*").order("created_at", desc=True).execute()
    prod_res = supabase.table("products").select("*").execute()
    
    inv_by_cat = {}
    for p in (prod_res.data or []):
        cat = p.get('category', 'Other')
        if cat not in inv_by_cat: inv_by_cat[cat] = []
        inv_by_cat[cat].append(p)

    return render_template('admin.html', orders=order_res.data or [], inventory_by_cat=inv_by_cat)

@app.route('/update_status/<int:order_id>', methods=['POST'])
def update_status(order_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    new_status = request.form.get('status')
    supabase.table("orders").update({"status": new_status}).eq("id", order_id).execute()
    return redirect(url_for('admin', tab='orders'))

# Other routes (edit_product, delete_product, add_product) remain as provided in your file
