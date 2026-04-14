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

# --- AUTO-DELETE LOGIC ---
def cleanup_old_orders():
    """Deletes orders older than 30 days automatically."""
    try:
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        supabase.table("orders").delete().lt("created_at", cutoff_date).execute()
    except Exception as e:
        print(f"Cleanup Error: {e}")

@app.route('/')
def index():
    cleanup_old_orders() # Runs cleanup every time the home page is loaded
    try:
        response = supabase.table("products").select("*").order("id").execute()
        categories = {}
        for p in response.data:
            cat = p.get('category') or 'Other'
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(p)
        return render_template('index.html', categories=categories)
    except Exception as e:
        return f"Database Error: {e}"

# --- ADMIN EXPORT ROUTE ---
@app.route('/export_orders')
def export_orders():
    if not session.get('logged_in'): return redirect(url_for('login'))
    try:
        res = supabase.table("orders").select("*").order("order_id", desc=True).execute()
        orders = res.data

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Date', 'Customer', 'Phone', 'Location', 'Items', 'Total', 'Paid', 'Balance', 'Status'])
        
        for o in orders:
            writer.writerow([
                o.get('order_id'), o.get('created_at'), o.get('username'),
                o.get('phone'), o.get('location'), o.get('item_name'),
                o.get('total_price'), o.get('amount_paid'), o.get('balance'), o.get('status')
            ])

        response = make_response(output.getvalue())
        filename = f"orders_{datetime.now().strftime('%Y-%m-%d')}.csv"
        response.headers["Content-Disposition"] = f"attachment; filename={filename}"
        response.headers["Content-type"] = "text/csv"
        return response
    except Exception as e:
        return f"Export Error: {e}"

# --- REMAINING ROUTES ---
@app.route('/place_order', methods=['POST'])
def place_order():
    # ... existing place_order logic ...
    pass

@app.route('/track_order', methods=['POST'])
def track_order():
    order_id = request.form.get('order_id')
    res = supabase.table("orders").select("*").eq("order_id", order_id).execute()
    if res.data: return render_template('receipt.html', order=res.data[0])
    return "Order ID not found. <a href='/'>Go back</a>"

@app.route('/admin')
def admin():
    if not session.get('logged_in'): return redirect(url_for('login'))
    orders = supabase.table("orders").select("*").order("order_id", desc=True).execute()
    products = supabase.table("products").select("*").order("id").execute()
    return render_template('admin.html', orders=orders.data, products=products.data)

@app.route('/update_status/<int:order_id>')
def update_status(order_id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    supabase.table("orders").update({"status": "On the Way"}).eq("order_id", order_id).execute()
    return redirect(url_for('admin'))

# Include Login/Logout/Add Product routes as previously provided...

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
