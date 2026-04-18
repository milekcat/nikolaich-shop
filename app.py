import sqlite3, json, urllib.parse, csv, io, requests, os
from flask import Flask, render_template, request, jsonify, make_response, session, redirect

app = Flask(__name__)
app.secret_key = 'nikolaich_super_secret_key_2026'

try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass

# --- НАСТРОЙКИ ИИ ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"
FAST_MODEL = "gemini-2.5-pro"
HEAVY_MODEL = "gemini-3.1-pro" # Для юриста и бухгалтера

def call_ai(prompt, system_prompt, model=FAST_MODEL, temp=0.25, is_json=True):
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model, 
        "temperature": temp, 
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
    }
    if is_json:
        payload["response_format"] = {"type": "json_object"}
        
    try:
        r = requests.post(AI_URL, json=payload, headers=headers, timeout=50)
        content = r.json()['choices'][0]['message']['content']
        return json.loads(content) if is_json else content
    except Exception as e:
        return {"error": str(e)} if is_json else f"Ошибка ИИ: {str(e)}"

# --- БАЗА ДАННЫХ 4.1 (С отдельными категориями) ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, image_url TEXT, active INTEGER DEFAULT 1, is_18_plus INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, full_name TEXT, vk_id TEXT UNIQUE, vip_status INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL, details TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Фейковые данные для старта
    c.execute("SELECT COUNT(*) FROM categories")
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO categories (name) VALUES (?)', [('Молоко и сыр',), ('Хлеб и выпечка',), ('Напитки',), ('Мясо',)])
        
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ('Молоко Свежее 3.2%, 1л', '', 120, 0, 50, 1, '🥛', 0),
            ('Хлеб Бородинский', '', 65, 0, 20, 2, '🍞', 0),
            ('Колбаса Докторская', '', 340, 0, 15, 4, '🥓', 0),
            ('Квас Никола, 1.5л', '', 95, 0, 30, 3, '🥤', 0),
            ('Фермерская Настойка', 'Крепкая', 850, 950, 10, 3, '🍷', 1)
        ]
        c.executemany('INSERT INTO products (name, desc, price, old_price, stock, category_id, image_url, is_18_plus) VALUES (?,?,?,?,?,?,?,?)', products)
    conn.commit()
    conn.close()

init_db()

# --- ВИТРИНА ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    categories = conn.execute("SELECT * FROM categories").fetchall()
    products = conn.execute("""
        SELECT p.*, c.name as cat_name 
        FROM products p 
        LEFT JOIN categories c ON p.category_id = c.id 
        WHERE p.active=1
    """).fetchall()
    conn.close()
    return render_template('index.html', categories=categories, products=products, user_phone=session.get('user_phone'))

# --- АВТОРЕГИСТРАЦИЯ И ЗАКАЗ ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone, name, cart_total = data.get('phone'), data.get('name'), data.get('cart_total', 0)
    
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

@app.route('/auth/vk')
def auth_vk():
    vk_app_id = "ТВОЙ_APP_ID" 
    redirect_uri = "https://nikolaich.shop/auth/vk/callback"
    return redirect(f"https://oauth.vk.com/authorize?client_id={vk_app_id}&display=page&redirect_uri={redirect_uri}&response_type=code&v=5.131")

# --- АДМИНКА (РЕНДЕР) ---
@app.route('/admin')
def admin():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    cats = conn.execute("SELECT * FROM categories").fetchall()
    conn.close()
    return render_template('admin.html', categories=cats)

# --- СКЛАД И КАТЕГОРИИ API ---
@app.route('/api/categories', methods=['POST'])
def add_category():
    conn = sqlite3.connect('shop.db')
    try:
        conn.execute("INSERT INTO categories (name) VALUES (?)", (request.json.get('name'),))
        conn.commit()
    except: pass
    conn.close()
    return jsonify({"status": "ok"})

@app.route('/api/products', methods=['GET', 'POST'])
def api_products():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    if request.method == 'GET':
        p = conn.execute("SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id").fetchall()
        conn.close()
        return jsonify([dict(x) for x in p])
    
    data = request.json
    conn.execute("INSERT INTO products (name, desc, price, old_price, category_id, image_url, is_18_plus) VALUES (?,?,?,?,?,?,?)", 
                 (data['name'], data.get('desc',''), data['price'], data.get('old_price',0), data['cat_id'], data.get('img','📦'), data.get('is_18', 0)))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- AI АССИСТЕНТЫ (НОВОЕ) ---
@app.route('/admin/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    role = data.get('role', 'маркетолог')
    msg = data.get('message', '')
    
    prompts = {
        "юрист": "Ты старший юрист. Помогаешь малому бизнесу (продуктовый магазин). Отвечай строго, сухо и по делу, опираясь на законы РФ.",
        "бухгалтер": "Ты главный бухгалтер. Помогаешь с налогами, ИП, кассой и отчетностью для продуктового магазина.",
        "маркетолог": "Ты креативный маркетолог. Придумываешь акции, тексты и стратегии продаж."
    }
    
    # Для Юриста и Бухгалтера используем тяжелую модель (3.1-pro)
    model = HEAVY_MODEL if role in ['юрист', 'бухгалтер'] else FAST_MODEL
    
    reply = call_ai(msg, prompts.get(role, prompts["маркетолог"]), model=model, is_json=False)
    return jsonify({"reply": reply})

@app.route('/admin/ai/print', methods=['POST'])
def ai_print():
    prompt = request.json.get('prompt')
    format_type = request.json.get('format', 'portrait') # portrait (A4) или landscape
    
    size = "width=2480&height=3508" if format_type == "portrait" else "width=3508&height=2480"
    safe_prompt = urllib.parse.quote(prompt + ", clean background, high resolution print ready, professional photography")
    img_url = f"https://image.pollinations.ai/prompt/{safe_prompt}?{size}&nologo=true"
    
    return jsonify({"image_url": img_url})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
