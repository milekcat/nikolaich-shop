# -*- coding: utf-8 -*-
import sqlite3, json, urllib.parse, requests, uuid, datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_premium_key_2026'

# --- ИНТЕГРАЦИЯ AI ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True):
    payload = {
        "model": model, 
        "temperature": 0.25, 
        "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]
    }
    if is_json: payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=50)
        return json.loads(r.json()['choices'][0]['message']['content']) if is_json else r.json()['choices'][0]['message']['content']
    except Exception as e: return {"error": str(e)} if is_json else f"Ошибка ИИ: {str(e)}"

# --- БАЗА ДАННЫХ 7.0 ---
def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE, sort_order INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, img TEXT, active INTEGER DEFAULT 1, is_18 INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, vk_id TEXT, vip INTEGER DEFAULT 0, bonuses INTEGER DEFAULT 0, ref_code TEXT UNIQUE, referred_by INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, subtotal REAL, discount REAL, delivery_cost REAL, final_total REAL, used_bonuses INTEGER, earned_bonuses INTEGER, items TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        c.execute('CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT UNIQUE, type TEXT, val REAL, min_cart REAL, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS promotions (id INTEGER PRIMARY KEY, name TEXT, condition_type TEXT, condition_val REAL, reward_type TEXT, reward_val REAL, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
        
        c.execute("SELECT COUNT(*) FROM settings")
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO settings VALUES (?,?)', [('base_delivery', '150'), ('km_price', '30'), ('cashback_percent', '5')])
            c.executemany('INSERT INTO categories (name) VALUES (?)', [('🔥 Акции',), ('🥛 Молочное',), ('🥩 Мясо',)])
            c.executemany('INSERT INTO promocodes (code, type, val, min_cart) VALUES (?,?,?,?)', [('START', 'percent', 10, 1000)])
            c.executemany('INSERT INTO products (name, desc, price, old_price, stock, category_id, img, is_18) VALUES (?,?,?,?,?,?,?,?)', [
                ('Молоко Фермерское', '1 литр', 120, 140, 50, 2, '🥛', 0),
                ('Стейк Рибай', 'Мраморная говядина', 850, 950, 15, 3, '🥩', 0),
                ('Настойка Николаича', '40 градусов', 900, 0, 10, 1, '🍷', 1)
            ])
    conn.commit()

init_db()

# --- МАРШРУТЫ ---
@app.route('/')
def index():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cats = conn.execute("SELECT * FROM categories ORDER BY id").fetchall()
        prods = conn.execute("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1").fetchall()
        user = None
        if 'phone' in session:
            user = conn.execute("SELECT * FROM users WHERE phone=?", (session['phone'],)).fetchone()
        return render_template('index.html', categories=cats, products=prods, user=user)

@app.route('/api/cart/calculate', methods=['POST'])
def calc_cart():
    data = request.json
    cart_total = float(data.get('cart_total', 0))
    promo_code = data.get('promo_code', '').upper().strip()
    use_bonuses = bool(data.get('use_bonuses', False))
    phone = session.get('phone') or data.get('phone')
    
    discount = 0
    delivery = 150
    
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if cart_total >= 2000: delivery = 0
        
        msg = ""
        if promo_code:
            pc = conn.execute("SELECT * FROM promocodes WHERE code=? AND active=1", (promo_code,)).fetchone()
            if pc and cart_total >= pc['min_cart']:
                discount = cart_total * (pc['val'] / 100) if pc['type'] == 'percent' else pc['val']
                msg = "Промокод применен!"

        bonuses_spent = 0
        earned = int(cart_total * 0.05)
        if phone:
            user = conn.execute("SELECT bonuses FROM users WHERE phone=?", (phone,)).fetchone()
            if user and use_bonuses:
                bonuses_spent = min(user[0], cart_total * 0.5)
                discount += bonuses_spent
                earned = 0

    return jsonify({"subtotal": cart_total, "discount": round(discount, 2), "delivery": delivery, "final": max(0, cart_total - discount) + delivery, "earned": earned, "msg": msg})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone, name = data.get('phone'), data.get('name')
    calc = data.get('calc_data')
    
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE phone=?", (phone,))
        u = c.fetchone()
        if not u:
            ref = f"REF-{uuid.uuid4().hex[:6].upper()}"
            c.execute("INSERT INTO users (phone, name, ref_code) VALUES (?, ?, ?)", (phone, name, ref))
            uid = c.lastrowid
        else: uid = u[0]
        
        if calc and calc.get('bonuses_spent', 0) > 0:
            c.execute("UPDATE users SET bonuses = bonuses - ? WHERE id=?", (calc['bonuses_spent'], uid))
        if calc:
            c.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (calc.get('earned', 0), uid))
        
        c.execute("INSERT INTO orders (user_id, final_total, items) VALUES (?, ?, ?)", (uid, calc['final'] if calc else 0, json.dumps(data.get('cart'))))
        conn.commit()
    session['phone'] = phone
    return jsonify({"status": "ok"})

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/products', methods=['GET', 'POST', 'PUT', 'DELETE'])
def admin_prods():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if request.method == 'GET':
            p = conn.execute("SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id=c.id").fetchall()
            return jsonify([dict(x) for x in p])
        d = request.json
        if request.method == 'POST':
            conn.execute("INSERT INTO products (name, desc, price, old_price, stock, category_id, img, is_18) VALUES (?,?,?,?,?,?,?,?)", (d['name'], d['desc'], d['price'], d.get('old_price',0), d['stock'], d['cat_id'], d['img'], d['is_18']))
        elif request.method == 'PUT':
            conn.execute("UPDATE products SET name=?, desc=?, price=?, old_price=?, stock=?, category_id=?, img=?, is_18=? WHERE id=?", (d['name'], d['desc'], d['price'], d['old_price'], d['stock'], d['cat_id'], d['img'], d['is_18'], d['id']))
        elif request.method == 'DELETE':
            conn.execute("DELETE FROM products WHERE id=?", (d['id'],))
        conn.commit()
    return jsonify({"status": "ok"})

@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    role, msg = request.json.get('role'), request.json.get('msg')
    sys = {"marketer": "Marketer", "lawyer": "Lawyer", "accountant": "Accountant"}
    m = "gemini-3.1-pro" if role in ['lawyer', 'accountant'] else "gemini-2.5-pro"
    return jsonify({"reply": call_ai(msg, sys.get(role, "Assistant"), m, False)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
