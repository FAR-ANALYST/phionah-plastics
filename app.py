@app.route('/place_order', methods=['POST'])
def place_order():
    username = request.form.get('username')
    location = request.form.get('location')
    amount_paid = int(request.form.get('amount_paid'))
    
    # Fetch all products to match against form data
    products_req = supabase.table("products").select("*").execute()
    all_products = products_req.data
    
    selected_items = []
    total_price = 0
    
    for p in all_products:
        # Check the quantity for this specific product ID
        qty = int(request.form.get(f"qty_{p['id']}", 0))
        if qty > 0:
            item_total = p['price'] * qty
            total_price += item_total
            selected_items.append(f"{p['name']} (x{qty})")
    
    if not selected_items:
        return "Please select at least one item."

    balance = total_price - amount_paid
    item_summary = ", ".join(selected_items)
    
    order_data = {
        "username": username,
        "location": location,
        "item_name": item_summary, # Stores both items like: "Pot Set (x1), Chair (x2)"
        "total_price": total_price,
        "amount_paid": amount_paid,
        "balance": balance,
        "status": "Pending"
    }
    
    response = supabase.table("orders").insert(order_data).execute()
    return render_template('receipt.html', order=response.data[0])
