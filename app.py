import sqlite3
import os
import json
import qrcode
import base64
import requests
from io import BytesIO
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DB_FILE = 'shop.db'
os.makedirs('static/uploads', exist_ok=True)

# Интеграция API Artemox (Gemini)
AI_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"
AI_URL = "https://api.artemox.com/v1/chat/completions"
VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"

def send_vk(vk_link, message):
    if not VK_TOKEN or not vk_link: return
    try:
        vk_id = str(vk_link).replace('https://vk.com/', '').split('/')[-1]
        if vk_id.isdigit(): uid = vk_id
        else:
            res = requests.get('https://api.vk.com/method/utils.resolveScreenName', params={'screen_name': vk_id, 'access_token': VK_TOKEN, 'v': '5.131'}).json()
            uid = res.get('response', {}).get('object_id')
        if uid: requests.post('https://api.vk.com/method/messages.send', data={'user_id': uid, 'random_id': 0, 'message': message, 'access_token': VK_TOKEN, 'v': '5.131'})
    except: pass

def call_ai(prompt, system_instruction, model_name="gemini-2.5-pro"):
    headers = {"Authorization": f"Bearer {AI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model_name,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        r = requests.post(AI_URL, headers=headers, json=payload, timeout=20)
        return r.json()['choices'][0]['message']['content']
    except Exception as e: return f"Ошибка AI: {e}"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, desc TEXT, price REAL, img TEXT, unit TEXT DEFAULT "шт", is_vip INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, address TEXT, password TEXT, is_approved INTEGER DEFAULT 0, vip_code TEXT, role TEXT DEFAULT "client")')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, vk_link TEXT, total REAL, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_name TEXT, price REAL, quantity INTEGER, unit TEXT)')
    
    # Базовые настройки и тема
    if c.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0:
        theme = json.dumps({"name": "default", "bg": "bg-stone-50", "header": "bg-green-800", "btn": "bg-green-600", "icon": "🚜", "greeting": "Свежие продукты с доставкой на дом"})
        c.execute("INSERT INTO settings (key, value) VALUES ('site_theme', ?)", (theme,))
    
    # Базовые категории
    if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
        cats = [("Мясо и птица", "🥩"), ("Молочные продукты", "🥛"), ("Овощи и зелень", "🥦"), ("Домашние заготовки", "🍯")]
        c.executemany("INSERT INTO categories (name, icon) VALUES (?, ?)", cats)
        
    try: c.execute("INSERT INTO users (phone, name, password, is_approved, role) VALUES ('admin', 'Админ', 'admin777', 1, 'admin')")
    except: pass
    conn.commit(); conn.close()

init_db()

@app.route('/')
def index(): return send_from_directory('static', 'index.html')

# --- КЛИЕНТСКИЙ ПУТЬ (ВИТРИНА И ДОСТАВКА) ---
@app.route('/api/store')
def store_data():
    conn = get_db()
    theme = json.loads(conn.execute("SELECT value FROM settings WHERE key='site_theme'").fetchone()['value'])
    cats = [dict(r) for r in conn.execute('SELECT * FROM categories').fetchall()]
    prods = [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_vip=0').fetchall()]
    conn.close(); return jsonify({"theme": theme, "categories": cats, "products": prods})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    d = request.json
    conn = get_db(); c = conn.cursor()
    c.execute('INSERT INTO orders (name, phone, address, vk_link, total, status) VALUES (?,?,?,?,?,?)', 
              (d['name'], d['phone'], d['address'], d.get('vk_link',''), d['total'], 'Новый'))
    oid = c.lastrowid
    for item in d['cart']:
        c.execute('INSERT INTO order_items (order_id, product_name, price, quantity, unit) VALUES (?,?,?,?,?)',
                  (oid, item['name'], item['price'], item['quantity'], item['unit']))
    conn.commit(); conn.close()
    
    # Уведомление в ВК админу и клиенту
    msg = f"🚜 Новый заказ #{oid} на доставку!\nИмя: {d['name']}\nАдрес: {d['address']}\nСумма: {d['total']}₽"
    send_vk(d.get('vk_link'), f"Ваш заказ #{oid} принят! Скоро мы его доставим.")
    # Тут можно добавить send_vk('твой_вк', msg)
    
    return jsonify({"success": True, "order_id": oid})

# --- VIP СИСТЕМА ---
@app.route('/api/vip/auth', methods=['POST'])
def vip_auth():
    d = request.json
    conn = get_db()
    u = conn.execute('SELECT * FROM users WHERE phone=? AND password=? AND is_approved=1', (d['phone'], d['pass'])).fetchone()
    if not u or u['vip_code'] != d['code']: return jsonify({"success": False})
    prods = [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_vip=1').fetchall()]
    conn.close(); return jsonify({"success": True, "vip_products": prods})

# --- АДМИНКА И ИИ ---
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
    conn.close(); return jsonify({"orders": orders, "users": users})

@app.route('/api/ai/theme', methods=['POST'])
def ai_theme():
    event = request.json.get('event')
    instr = "Ты — веб-дизайнер TailwindCSS. Пользователь дает праздник. Выдай JSON с классами Tailwind для темы сайта. Ключи: bg (фон страницы, например bg-rose-50), header (фон шапки, например bg-pink-600), btn (кнопки, bg-pink-500), icon (эмодзи), greeting (короткое приветствие). Верни ТОЛЬКО JSON."
    ai_res = call_ai(f"Праздник: {event}", instr, "gemini-2.5-flash")
    try:
        import re; theme_data = json.loads(re.search(r'\{.*\}', ai_res, re.DOTALL).group())
        conn = get_db()
        conn.execute("UPDATE settings SET value=? WHERE key='site_theme'", (json.dumps(theme_data),))
        conn.commit(); conn.close()
        return jsonify({"success": True, "theme": theme_data})
    except Exception as e: return jsonify({"success": False, "error": str(e)})

@app.route('/api/ai/generate', methods=['POST'])
def ai_generate():
    topic = request.json.get('topic')
    instr = "Ты маркетолог. Создай текст для промо-баннера доставки продуктов. Верни JSON: {\"title\": \"Заголовок\", \"text\": \"Описание\"}"
    ai_res = call_ai(topic, instr, "gemini-3.1-pro")
    try:
        import re; data = json.loads(re.search(r'\{.*\}', ai_res, re.DOTALL).group())
        qr = qrcode.QRCode(version=1, box_size=8, border=1)
        qr.add_data("https://nikolaich.shop"); qr.make(fit=True)
        buf = BytesIO(); qr.make_image(fill_color="black", back_color="white").save(buf, format="PNG")
        data['qr'] = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        return jsonify(data)
    except: return jsonify({"error": "Ошибка генерации"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
