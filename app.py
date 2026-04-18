import sqlite3, json, urllib.parse, csv, io, requests, os
from flask import Flask, render_template, request, jsonify, make_response, session, redirect

app = Flask(__name__)
app.secret_key = 'nikolaich_super_secret_key_2026'

try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass

# --- НАСТРОЙКИ ИИ (Artemox + Gemini 2.5 Pro) ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"
MARKETING_MODEL = "gemini-2.5-pro"

def call_ai(prompt, system_prompt="Ты креативный маркетолог", model=MARKETING_MODEL, temp=0.5):
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model, 
        "temperature": temp, 
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}], 
        "response_format": {"type": "json_object"}
    }
    try:
        r = requests.post(AI_URL, json=payload, headers=headers, timeout=40)
        return json.loads(r.json()['choices'][0]['message']['content'])
    except Exception as e:
        return {"error": str(e)}

# --- БАЗА ДАННЫХ 4.0 ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, stock INTEGER, category TEXT, image_url TEXT, active INTEGER DEFAULT 1, is_18_plus INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, text TEXT, rules TEXT, bg_color TEXT, image_url TEXT, active INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, full_name TEXT, vk_id TEXT UNIQUE, vip_status INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL, details TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    settings = [('delivery_base', '150'), ('delivery_km', '30'), ('free_delivery_limit', '2000'), ('package_fee', '40'), ('free_package_limit', '500'), ('theme_color', '#1a3622')]
    c.executemany('INSERT OR IGNORE INTO settings VALUES (?, ?)', settings)
    
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ('Лимонад "Николаич"', 150, 50, 'Напитки', 'https://via.placeholder.com/400x300?text=Limonad', 0),
            ('Фермерское Сало', 450, 20, 'Мясо', 'https://via.placeholder.com/400x300?text=Salo', 0),
            ('Настойка на кедре', 850, 10, 'Скрытое 18+', 'https://via.placeholder.com/400x300?text=Nastoyka', 1)
        ]
        c.executemany('INSERT INTO products (name, price, stock, category, image_url, is_18_plus) VALUES (?,?,?,?,?,?)', products)
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = sqlite3.connect('shop.db')
    res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    try: return float(res[0])
    except: return res[0] if res else default

# --- ВИТРИНА ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    data = {
        "products": conn.execute("SELECT * FROM products WHERE active=1").fetchall(),
        "banners": conn.execute("SELECT * FROM banners WHERE active=1 ORDER BY id DESC LIMIT 1").fetchall(),
        "theme": get_setting('theme_color', '#1a3622'),
        "user_phone": session.get('user_phone', None)
    }
    conn.close()
    return render_template('index.html', **data)

# --- АВТОРЕГИСТРАЦИЯ И ЗАКАЗ ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone = data.get('phone')
    name = data.get('name')
    cart_total = data.get('cart_total', 0)
    
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE phone=?", (phone,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (phone, full_name) VALUES (?, ?)", (phone, name))
        user_id = c.lastrowid
    else:
        user_id = user[0]
        
    c.execute("INSERT INTO orders (user_id, total, details) VALUES (?, ?, ?)", (user_id, cart_total, json.dumps(data.get('items', []))))
    conn.commit()
    conn.close()
    
    session['user_phone'] = phone
    return jsonify({"status": "success"})

# --- ИНТЕГРАЦИЯ VK ---
@app.route('/auth/vk')
def auth_vk():
    vk_app_id = "ТВОЙ_APP_ID_ТУТ" 
    redirect_uri = "https://nikolaich.shop/auth/vk/callback"
    return redirect(f"https://oauth.vk.com/authorize?client_id={vk_app_id}&display=page&redirect_uri={redirect_uri}&response_type=code&v=5.131")

# --- УМНАЯ ЛОГИСТИКА ---
@app.route('/api/calculate_delivery', methods=['POST'])
def calculate_delivery():
    data = request.json
    cart_total = float(data.get('cart_total', 0))
    distance_km = float(data.get('distance_km', 0))
    delivery_type = data.get('type', 'taxi')
    
    base_price = get_setting('delivery_base', 150)
    price_per_km = get_setting('delivery_km', 30)
    free_delivery = get_setting('free_delivery_limit', 2000)
    package_fee = get_setting('package_fee', 40)
    free_package = get_setting('free_package_limit', 500)
    
    final_package = 0 if cart_total >= free_package else package_fee
    
    if cart_total >= free_delivery:
        final_delivery = 0
    else:
        if delivery_type == 'taxi':
            final_delivery = base_price + (distance_km * price_per_km)
        else:
            final_delivery = base_price
            
    return jsonify({"cart_total": cart_total, "delivery_price": round(final_delivery, 2), "package_price": final_package, "total_to_pay": round(cart_total + final_delivery + final_package, 2)})

# --- АДМИНКА ---
@app.route('/admin')
def admin():
    s = {"base": get_setting('delivery_base'), "km": get_setting('delivery_km'), "free_del": get_setting('free_delivery_limit'), "pack": get_setting('package_fee'), "free_pack": get_setting('free_package_limit')}
    return render_template('admin.html', **s)

@app.route('/admin/settings', methods=['POST'])
def save_settings():
    conn = sqlite3.connect('shop.db')
    for key, value in request.json.items():
        conn.execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- VIP КЛИЕНТЫ ---
@app.route('/api/users', methods=['GET', 'PUT'])
def api_users():
    conn = sqlite3.connect('shop.db')
    if request.method == 'GET':
        u = conn.execute("SELECT * FROM users").fetchall()
        conn.close()
        return jsonify([dict(zip(['id','phone','name','vk_id','vip'], x)) for x in u])
    
    data = request.json
    conn.execute("UPDATE users SET vip_status=? WHERE id=?", (data['vip_status'], data['id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- СКЛАД ---
@app.route('/api/products', methods=['GET', 'POST', 'PUT'])
def api_products():
    conn = sqlite3.connect('shop.db')
    if request.method == 'GET':
        p = conn.execute("SELECT * FROM products").fetchall()
        conn.close()
        return jsonify([dict(zip(['id','name','price','stock','cat','img','active','is_18'], x)) for x in p])
    
    data = request.json
    if request.method == 'POST':
        conn.execute("INSERT INTO products (name, price, stock, category, image_url, is_18_plus) VALUES (?,?,?,?,?,?)", 
                     (data['name'], data['price'], data['stock'], data.get('cat', 'Разное'), data.get('img', ''), data.get('is_18', 0)))
    elif request.method == 'PUT':
        conn.execute("UPDATE products SET name=?, price=?, stock=?, active=?, is_18_plus=? WHERE id=?", 
                     (data['name'], data['price'], data['stock'], data['active'], data['is_18'], data['id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- AI МАРКЕТИНГ ---
@app.route('/admin/ai/full_campaign', methods=['POST'])
def ai_campaign():
    topic = request.json.get('topic')
    sys_prompt = "Ты креативный директор. Выдай СТРОГИЙ JSON формат, без разметки markdown."
    prompt = f"""Тема: {topic}. Выдай JSON: {{"title": "Короткий заголовок", "text": "Слоган", "rules": "Условия", "color": "HEX цвет (#...)", "img_prompt": "English prompt: minimal, high quality food photography, cinematic lighting"}}"""
    
    ai_data = call_ai(prompt, sys_prompt, MARKETING_MODEL, 0.5)
    if "error" in ai_data: return jsonify(ai_data), 500
        
    safe_prompt = urllib.parse.quote(ai_data.get('img_prompt', 'delicious food'))
    img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?width=1200&height=600&nologo=true"
    
    conn = sqlite3.connect('shop.db')
    conn.execute("UPDATE settings SET value=? WHERE key='theme_color'", (ai_data.get('color', '#0b3d2c'),))
    conn.execute("UPDATE banners SET active=0") 
    conn.execute("INSERT INTO banners (title, text, rules, bg_color, image_url, active) VALUES (?, ?, ?, ?, ?, 1)", 
                 (ai_data['title'], ai_data['text'], ai_data['rules'], ai_data['color'], img_url))
    conn.commit()
    conn.close()
    
    return jsonify({"title": ai_data['title'], "text": ai_data['text'], "image_url": img_url, "color": ai_data['color']})

# --- АНАЛИТИКА ---
@app.route('/admin/export')
def export_stats():
    conn = sqlite3.connect('shop.db')
    orders = conn.execute("SELECT id, total, date FROM orders").fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID Заказа', 'Сумма (руб)', 'Дата'])
    cw.writerows(orders)
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = "attachment; filename=nikolaich_stats.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
