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

# === НАСТРОЙКИ ВКОНТАКТЕ ===
VK_GROUP_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"

def send_vk_message(vk_identifier, message):
    if not VK_GROUP_TOKEN or not vk_identifier:
        return
    try:
        # Очищаем ссылку, оставляем только ID или короткое имя
        vk_id = str(vk_identifier).replace('https://vk.com/', '').split('/')[-1]
        
        # Если это уже цифровой ID (например, от VK Mini App)
        if vk_id.isdigit():
            user_id = vk_id
        else:
            # Если это короткая ссылка (домен), узнаем цифровой ID
            res = requests.get('https://api.vk.com/method/utils.resolveScreenName', params={'screen_name': vk_id, 'access_token': VK_GROUP_TOKEN, 'v': '5.131'}).json()
            if 'response' in res and res['response']:
                user_id = res['response']['object_id']
            else:
                return # Не смогли распознать пользователя
        
        # Отправляем сообщение
        requests.post('https://api.vk.com/method/messages.send', data={
            'user_id': user_id, 
            'random_id': 0, 
            'message': message, 
            'access_token': VK_GROUP_TOKEN, 
            'v': '5.131'
        })
    except Exception as e:
        print(f"Ошибка ВК: {e}")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    
    # Создание базовых таблиц
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, description TEXT, price REAL, old_price REAL, img TEXT, stock REAL DEFAULT 999, unit TEXT DEFAULT 'шт', is_popular INTEGER DEFAULT 0, is_promo INTEGER DEFAULT 0, is_secret INTEGER DEFAULT 0, is_available INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promotions (id INTEGER PRIMARY KEY, title TEXT, img TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT, discount INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, vk_link TEXT, total REAL, promo_code TEXT, payment_method TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, product_name TEXT, price REAL, quantity REAL, unit TEXT)''')
    
    # --- УМНАЯ МИГРАЦИЯ БАЗЫ ДАННЫХ ---
    columns_to_check = {
        'stock': "REAL DEFAULT 999", 
        'unit': "TEXT DEFAULT 'шт'",
        'is_popular': "INTEGER DEFAULT 0",
        'is_promo': "INTEGER DEFAULT 0",
        'is_secret': "INTEGER DEFAULT 0",
        'is_available': "INTEGER DEFAULT 1"
    }
    
    for col, col_type in columns_to_check.items():
        try:
            c.execute(f"SELECT {col} FROM products LIMIT 1")
        except sqlite3.OperationalError:
            c.execute(f"ALTER TABLE products ADD COLUMN {col} {col_type}")
    # -----------------------------------

    if c.execute('SELECT COUNT(*) FROM settings').fetchone()[0] == 0:
        c.executemany('INSERT INTO settings (key, value) VALUES (?, ?)', [
            ("secret_code", "7777"),
            ("pay_cash", "1"), ("pay_card_courier", "1"), ("pay_transfer", "1"), ("pay_online", "0")
        ])
        
    if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
        c.execute('INSERT INTO categories (name) VALUES ("Свежее мясо"), ("Молоко и сыры"), ("Выпечка")')
        c.execute('INSERT INTO promotions (title, img) VALUES ("Скидка 20% на мясо по выходным!", "")')
    conn.commit()
    conn.close()

init_db()

# --- КЛИЕНТСКАЯ ЧАСТЬ ---
@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/api/store-data', methods=['GET'])
def get_store_data():
    conn = get_db_connection()
    cats = conn.execute('SELECT * FROM categories').fetchall()
    # Ошибка со stock > 0 исправлена: теперь показываем всё, что is_available = 1
    prods = conn.execute('SELECT * FROM products WHERE is_available = 1 AND is_secret = 0').fetchall()
    promos = conn.execute('SELECT * FROM promotions').fetchall()
    settings = dict(conn.execute('SELECT key, value FROM settings').fetchall())
    conn.close()
    return jsonify({
        "categories": [dict(c) for c in cats],
        "products": [dict(p) for p in prods],
        "promotions": [dict(pr) for pr in promos],
        "settings": settings
    })

@app.route('/api/secret-auth', methods=['POST'])
def secret_auth():
    code = request.json.get('code')
    conn = get_db_connection()
    true_code = conn.execute('SELECT value FROM settings WHERE key="secret_code"').fetchone()['value']
    if code == true_code:
        # Ошибка со stock > 0 исправлена
        prods = conn.execute('SELECT * FROM products WHERE is_available = 1 AND is_secret = 1').fetchall()
        conn.close()
        return jsonify({"success": True, "products": [dict(p) for p in prods]})
    conn.close()
    return jsonify({"success": False})

@app.route('/api/search', methods=['GET'])
def search_products():
    query = request.args.get('q', '').lower()
    conn = get_db_connection()
    prods = conn.execute('SELECT * FROM products WHERE is_available = 1 AND is_secret = 0 AND LOWER(name) LIKE ?', ('%'+query+'%',)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in prods])

@app.route('/api/check-promo', methods=['POST'])
def check_promo():
    code = request.json.get('code', '').upper()
    conn = get_db_connection()
    promo = conn.execute('SELECT * FROM promocodes WHERE code = ?', (code,)).fetchone()
    conn.close()
    if promo: return jsonify({"success": True, "discount": promo['discount']})
    return jsonify({"success": False})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    conn = get_db_connection()
    c = conn.cursor()
    
    for item in data['cart']:
        prod = c.execute('SELECT stock, unit FROM products WHERE id = ?', (item['id'],)).fetchone()
        if not prod or round(prod['stock'], 3) < round(item['quantity'], 3):
            return jsonify({"success": False, "error": f"Товара '{item['name']}' не хватает на складе!"}), 400

    c.execute('INSERT INTO orders (name, phone, address, vk_link, payment_method, total, promo_code, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (data['name'], data['phone'], data['address'], data.get('vk_link', ''), data.get('payment_method', 'Наличными'), data['total'], data.get('promo', ''), 'Новый'))
    order_id = c.lastrowid
    
    for item in data['cart']:
        c.execute('INSERT INTO order_items (order_id, product_id, product_name, price, quantity, unit) VALUES (?, ?, ?, ?, ?, ?)',
                  (order_id, item['id'], item['name'], item['price'], item['quantity'], item.get('unit', 'шт')))
        c.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (item['quantity'], item['id']))
        
    conn.commit()
    conn.close()

    send_vk_message(data.get('vk_link', ''), f"🚜 Привет, {data['name']}! Ваш заказ #{order_id} на сумму {data['total']}₽ успешно оформлен. Оплата: {data.get('payment_method')}. Мы сообщим, когда курьер выедет!")

    return jsonify({"success": True, "order_id": order_id})

@app.route('/api/cabinet/<phone>', methods=['GET'])
def user_cabinet(phone):
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders WHERE phone = ? ORDER BY created_at DESC', (phone,)).fetchall()
    res = []
    for o in orders:
        od = dict(o)
        od['items'] = [dict(i) for i in conn.execute('SELECT * FROM order_items WHERE order_id = ?', (o['id'],)).fetchall()]
        res.append(od)
    conn.close()
    return jsonify(res)


# --- CRM И АДМИНКА ---
@app.route('/admin')
def serve_admin():
    return send_from_directory('static', 'admin.html')

@app.route('/api/admin/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({"error": "Нет файла"}), 400
    file = request.files['file']
    filename = f"{uuid.uuid4().hex}.{file.filename.split('.')[-1]}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({"url": f"/uploads/{filename}"})

@app.route('/api/admin/data', methods=['GET'])
def get_admin_data():
    conn = get_db_connection()
    orders = conn.execute('SELECT * FROM orders ORDER BY created_at DESC').fetchall()
    orders_list = []
    for o in orders:
        od = dict(o)
        od['items'] = [dict(i) for i in conn.execute('SELECT * FROM order_items WHERE order_id = ?', (o['id'],)).fetchall()]
        orders_list.append(od)
    
    res = {
        "orders": orders_list,
        "categories": [dict(c) for c in conn.execute('SELECT * FROM categories').fetchall()],
        "products": [dict(p) for p in conn.execute('SELECT * FROM products').fetchall()],
        "promotions": [dict(pr) for pr in conn.execute('SELECT * FROM promotions').fetchall()],
        "promocodes": [dict(pc) for pc in conn.execute('SELECT * FROM promocodes').fetchall()],
        "settings": dict(conn.execute('SELECT key, value FROM settings').fetchall())
    }
    conn.close()
    return jsonify(res)

@app.route('/api/admin/stats', methods=['GET'])
def get_stats():
    conn = get_db_connection()
    total_rev = conn.execute("SELECT SUM(total) FROM orders WHERE status IN ('Готов', 'В работе', 'Новый')").fetchone()[0] or 0
    total_orders = conn.execute("SELECT COUNT(id) FROM orders").fetchone()[0] or 0
    active_orders = conn.execute("SELECT COUNT(id) FROM orders WHERE status IN ('Новый', 'В работе')").fetchone()[0] or 0
    conn.close()
    return jsonify({"revenue": round(total_rev, 2), "orders": total_orders, "active": active_orders})

@app.route('/api/admin/products', methods=['POST'])
def add_product():
    d = request.json
    conn = get_db_connection()
    conn.execute('''INSERT INTO products (category_id, name, description, price, old_price, img, stock, unit, is_popular, is_promo, is_secret) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                 (d['category_id'], d['name'], d['description'], d['price'], d.get('old_price', 0), d['img'], d['stock'], d['unit'], d['is_popular'], d['is_promo'], d['is_secret']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/products/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    conn = get_db_connection()
    conn.execute('DELETE FROM products WHERE id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/orders/<int:oid>/status', methods=['POST'])
def update_order(oid):
    status = request.json['status']
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (status, oid))
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (oid,)).fetchone()
    conn.commit()
    conn.close()
    
    if order and order['vk_link']:
        send_vk_message(order['vk_link'], f"🚜 Обновление по заказу #{oid}! Новый статус: {status}. Спасибо, что выбираете нас!")

    return jsonify({"success": True})

@app.route('/api/admin/categories', methods=['POST'])
def add_category():
    conn = get_db_connection()
    conn.execute('INSERT INTO categories (name) VALUES (?)', (request.json['name'],))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/promotions', methods=['POST'])
def add_promo():
    conn = get_db_connection()
    conn.execute('INSERT INTO promotions (title, img) VALUES (?, ?)', (request.json['title'], request.json['img']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/promocodes', methods=['POST'])
def add_promocode():
    conn = get_db_connection()
    conn.execute('INSERT INTO promocodes (code, discount) VALUES (?, ?)', (request.json['code'].upper(), request.json['discount']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/settings', methods=['POST'])
def update_settings():
    data = request.json
    conn = get_db_connection()
    for key, value in data.items():
        conn.execute('UPDATE settings SET value = ? WHERE key = ?', (value, key))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# === МАССОВАЯ РАССЫЛКА ВК ===
@app.route('/api/admin/vk/broadcast', methods=['POST'])
def vk_broadcast():
    text = request.json.get('text', '')
    if not text: return jsonify({"success": False, "error": "Пустое сообщение"})
    
    conn = get_db_connection()
    # Выбираем всех уникальных клиентов, у которых указан ВК
    users = conn.execute('SELECT DISTINCT vk_link FROM orders WHERE vk_link != "" AND vk_link IS NOT NULL').fetchall()
    conn.close()
    
    count = 0
    for u in users:
        send_vk_message(u['vk_link'], text)
        count += 1
        
    return jsonify({"success": True, "count": count})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
