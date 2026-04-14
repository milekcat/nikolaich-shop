import sqlite3
import os
import uuid
import requests
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DB_FILE = 'shop.db'
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Ключ доступа для уведомлений и рассылок
VK_GROUP_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"

def send_vk_message(vk_identifier, message):
    if not VK_GROUP_TOKEN or not vk_identifier: return
    try:
        vk_id = str(vk_identifier).replace('https://vk.com/', '').split('/')[-1]
        if vk_id.isdigit(): user_id = vk_id
        else:
            res = requests.get('https://api.vk.com/method/utils.resolveScreenName', params={'screen_name': vk_id, 'access_token': VK_GROUP_TOKEN, 'v': '5.131'}).json()
            user_id = res['response']['object_id'] if 'response' in res and res['response'] else None
        if user_id:
            requests.post('https://api.vk.com/method/messages.send', data={'user_id': user_id, 'random_id': 0, 'message': message, 'access_token': VK_GROUP_TOKEN, 'v': '5.131'})
    except Exception as e: print(f"VK Error: {e}")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, description TEXT, price REAL, old_price REAL, img TEXT, stock REAL DEFAULT 999, unit TEXT DEFAULT "шт", is_popular INTEGER DEFAULT 0, is_promo INTEGER DEFAULT 0, is_secret INTEGER DEFAULT 0, is_available INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS promotions (id INTEGER PRIMARY KEY, title TEXT, img TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT, discount INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, vk_link TEXT, total REAL, promo_code TEXT, payment_method TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    c.execute('CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, price REAL, quantity REAL, unit TEXT)')
    
    # Миграция: Проверка и добавление необходимых колонок
    cols = { 'stock': "REAL DEFAULT 999", 'unit': "TEXT DEFAULT 'шт'", 'is_secret': "INTEGER DEFAULT 0" }
    for col, col_def in cols.items():
        try: c.execute(f"SELECT {col} FROM products LIMIT 1")
        except sqlite3.OperationalError: c.execute(f"ALTER TABLE products ADD COLUMN {col} {col_def}")
    
    if c.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0:
        c.executemany('INSERT INTO settings (key, value) VALUES (?, ?)', [("secret_code", "7777"), ("pay_cash", "1"), ("pay_transfer", "1")])
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def serve_index(): return send_from_directory('static', 'index.html')

@app.route('/api/store-data')
def get_store_data():
    conn = get_db_connection()
    data = {
        "categories": [dict(c) for c in conn.execute('SELECT * FROM categories').fetchall()],
        "products": [dict(p) for p in conn.execute('SELECT * FROM products WHERE is_available = 1 AND is_secret = 0').fetchall()],
        "promotions": [dict(pr) for pr in conn.execute('SELECT * FROM promotions').fetchall()],
        "settings": dict(conn.execute('SELECT key, value FROM settings').fetchall())
    }
    conn.close()
    return jsonify(data)

@app.route('/api/secret-auth', methods=['POST'])
def secret_auth():
    code = request.json.get('code')
    conn = get_db_connection()
    true_code = conn.execute('SELECT value FROM settings WHERE key="secret_code"').fetchone()['value']
    if str(code) == str(true_code):
        prods = [dict(p) for p in conn.execute('SELECT * FROM products WHERE is_available = 1 AND is_secret = 1').fetchall()]
        conn.close()
        return jsonify({"success": True, "products": prods})
    conn.close()
    return jsonify({"success": False})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    d = request.json
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO orders (name, phone, address, vk_link, payment_method, total, promo_code, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (d['name'], d['phone'], d['address'], d.get('vk_link', ''), d.get('payment_method', 'Наличными'), d['total'], d.get('promo', ''), 'Новый'))
    order_id = c.lastrowid
    for item in d['cart']:
        c.execute('INSERT INTO order_items (order_id, product_id, product_name, price, quantity, unit) VALUES (?, ?, ?, ?, ?, ?)',
                  (order_id, item['id'], item['name'], item['price'], item['quantity'], item.get('unit', 'шт')))
        c.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (item['quantity'], item['id']))
    conn.commit()
    conn.close()
    send_vk_message(d.get('vk_link'), f"🚜 Заказ #{order_id} принят! Сумма: {d['total']}₽. Мы скоро свяжемся с вами.")
    return jsonify({"success": True, "order_id": order_id})

@app.route('/admin')
def serve_admin(): return send_from_directory('static', 'admin.html')

@app.route('/api/admin/data')
def get_admin_data():
    conn = get_db_connection()
    orders = []
    for o in conn.execute('SELECT * FROM orders ORDER BY created_at DESC').fetchall():
        od = dict(o)
        od['items'] = [dict(i) for i in conn.execute('SELECT * FROM order_items WHERE order_id = ?', (o['id'],)).fetchall()]
        orders.append(od)
    res = {
        "orders": orders, 
        "products": [dict(p) for p in conn.execute('SELECT * FROM products').fetchall()],
        "categories": [dict(c) for c in conn.execute('SELECT * FROM categories').fetchall()],
        "promocodes": [dict(pc) for pc in conn.execute('SELECT * FROM promocodes').fetchall()]
    }
    conn.close()
    return jsonify(res)

@app.route('/api/admin/products', methods=['POST'])
def admin_add_product():
    d = request.json
    conn = get_db_connection()
    conn.execute('INSERT INTO products (category_id, name, description, price, img, unit, is_secret, stock) VALUES (?,?,?,?,?,?,?,?)',
                 (d['category_id'], d['name'], d['description'], d['price'], d['img'], d['unit'], d['is_secret'], d['stock']))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/orders/<int:oid>/status', methods=['POST'])
def update_order_status(oid):
    status = request.json['status']
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, oid))
    order = conn.execute('SELECT vk_link FROM orders WHERE id = ?', (oid,)).fetchone()
    conn.commit(); conn.close()
    if order and order['vk_link']: send_vk_message(order['vk_link'], f"🚜 Статус вашего заказа #{oid} изменен на: {status}")
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
