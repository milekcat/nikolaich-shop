import sqlite3, os, json, qrcode, base64, requests
from io import BytesIO
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
DB_FILE = 'shop.db'
os.makedirs('static/uploads', exist_ok=True)

# Интеграция API Artemox (Gemini)
AI_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"
AI_URL = "https://api.artemox.com/v1/chat/completions"

def call_ai(prompt, system_instr, model="gemini-2.5-pro"):
    try:
        r = requests.post(AI_URL, headers={"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"}, 
                          json={"model": model, "temperature": 0.3, "messages": [{"role": "system", "content": system_instr}, {"role": "user", "content": prompt}]}, timeout=20)
        return r.json()['choices'][0]['message']['content']
    except Exception as e: return f"Ошибка AI: {e}"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    # Строгая структура базы данных
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, address TEXT, password TEXT, is_approved INTEGER DEFAULT 0, vip_code TEXT, role TEXT DEFAULT "client", consent_pdn INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category TEXT, name TEXT, desc TEXT, price REAL, img TEXT, unit TEXT DEFAULT "шт", stock REAL DEFAULT 100, is_vip INTEGER DEFAULT 0, is_available INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, total REAL, status TEXT, legal_consent INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, price REAL, quantity REAL, unit TEXT)')
    
    try: c.execute("INSERT INTO users (phone, name, password, is_approved, role) VALUES ('admin', 'Администратор', 'admin777', 1, 'admin')")
    except: pass
    conn.commit(); conn.close()

init_db()

@app.route('/')
def index(): return send_from_directory('static', 'index.html')

@app.route('/api/store')
def store():
    conn = get_db()
    prods = [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_available=1 AND is_vip=0 AND stock > 0').fetchall()]
    conn.close(); return jsonify({"products": prods})

# --- ОФОРМЛЕНИЕ ЗАКАЗА (С УЧЕТОМ ОСТАТКОВ И ЮР. БАЗОЙ) ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    d = request.json
    if not d.get('legal_consent'): return jsonify({"success": False, "msg": "Необходимо согласие с условиями оферты."})
    
    conn = get_db(); c = conn.cursor()
    try:
        # Регистрация заказа
        c.execute('INSERT INTO orders (name, phone, address, total, status, legal_consent) VALUES (?,?,?,?,?,?)', 
                  (d['name'], d['phone'], d['address'], d['total'], 'Новый', 1))
        oid = c.lastrowid
        
        # Списание остатков
        for item in d['cart']:
            c.execute('INSERT INTO order_items (order_id, product_id, product_name, price, quantity, unit) VALUES (?,?,?,?,?,?)',
                      (oid, item['id'], item['name'], item['price'], item['quantity'], item['unit']))
            # Жесткий учет товара
            c.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (item['quantity'], item['id']))
        conn.commit()
        return jsonify({"success": True, "order_id": oid})
    except Exception as e:
        conn.rollback(); return jsonify({"success": False, "msg": "Ошибка оформления заказа."})
    finally: conn.close()

# --- VIP АВТОРИЗАЦИЯ И РЕГИСТРАЦИЯ ---
@app.route('/api/vip/register', methods=['POST'])
def vip_reg():
    d = request.json
    conn = get_db(); c = conn.cursor()
    try:
        c.execute('INSERT INTO users (phone, name, address, password) VALUES (?,?,?,?)', (d['phone'], d['name'], d['address'], d['password']))
        conn.commit(); return jsonify({"success": True, "msg": "Заявка отправлена. Ожидайте одобрения."})
    except sqlite3.IntegrityError: return jsonify({"success": False, "msg": "Телефон уже зарегистрирован."})
    finally: conn.close()

@app.route('/api/vip/login', methods=['POST'])
def vip_login():
    d = request.json
    conn = get_db()
    u = conn.execute('SELECT * FROM users WHERE phone=? AND password=? AND is_approved=1', (d['phone'], d['pass'])).fetchone()
    if not u or u['vip_code'] != d['code']: return jsonify({"success": False, "msg": "Отказано в доступе."})
    prods = [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_vip=1 AND stock > 0').fetchall()]
    conn.close(); return jsonify({"success": True, "vip_products": prods})

# --- АДМИНКА И AI ---
@app.route('/admin')
def admin(): return send_from_directory('static', 'admin.html')

@app.route('/api/admin/data')
def admin_data():
    conn = get_db()
    orders = []
    for o in conn.execute('SELECT * FROM orders ORDER BY id DESC').fetchall():
        od = dict(o)
        od['items'] = [dict(i) for i in conn.execute('SELECT * FROM order_items WHERE order_id=?', (o['id'],)).fetchall()]
        orders.append(od)
    users = [dict(r) for r in conn.execute('SELECT * FROM users WHERE role="client"').fetchall()]
    prods = [dict(r) for r in conn.execute('SELECT * FROM products').fetchall()]
    conn.close(); return jsonify({"orders": orders, "users": users, "products": prods})

@app.route('/api/admin/approve', methods=['POST'])
def admin_approve():
    d = request.json; conn = get_db()
    conn.execute('UPDATE users SET is_approved=1, vip_code=? WHERE id=?', (d['code'], d['id']))
    conn.commit(); conn.close(); return jsonify({"success": True})

@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    reply = call_ai(request.json.get('prompt'), "Ты бизнес-консультант магазина фермерских продуктов. Помогай с продажами.", "gemini-2.5-pro")
    return jsonify({"reply": reply})

@app.route('/api/ai/banner', methods=['POST'])
def ai_banner():
    res = call_ai(request.json.get('topic'), "Ты маркетолог. Верни строго JSON: {\"title\":\"...\", \"text\":\"...\"}", "gemini-3.1-pro")
    try:
        import re; data = json.loads(re.search(r'\{.*\}', res, re.DOTALL).group())
        qr = qrcode.QRCode(version=1, box_size=8, border=1); qr.add_data("https://nikolaich.shop"); qr.make(fit=True)
        buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        data['qr'] = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        return jsonify(data)
    except: return jsonify({"error": "Ошибка ИИ"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
