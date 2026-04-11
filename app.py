import sqlite3
import os
import uuid
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DB_FILE = 'shop.db'
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Создаем новые таблицы
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, description TEXT, price REAL, old_price REAL, img TEXT, is_available INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promotions (id INTEGER PRIMARY KEY, title TEXT, img TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT, discount INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, name TEXT, phone TEXT, address TEXT, total REAL, promo_code TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_name TEXT, price REAL, quantity INTEGER)''')
    
    # Добавляем демо-данные, если база пустая
    if c.execute('SELECT COUNT(*) FROM categories').fetchone()[0] == 0:
        c.execute('INSERT INTO categories (name) VALUES ("Свежее мясо"), ("Молоко и сыры"), ("Выпечка")')
        c.execute('INSERT INTO promotions (title, img) VALUES ("Скидка 20% на мясо по выходным!", "")')
        c.execute('INSERT INTO promocodes (code, discount) VALUES ("СВОИ", 10)')
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
    prods = conn.execute('SELECT * FROM products WHERE is_available = 1').fetchall()
    promos = conn.execute('SELECT * FROM promotions').fetchall()
    conn.close()
    return jsonify({
        "categories": [dict(c) for c in cats],
        "products": [dict(p) for p in prods],
        "promotions": [dict(pr) for pr in promos]
    })

@app.route('/api/check-promo', methods=['POST'])
def check_promo():
    code = request.json.get('code', '').upper()
    conn = get_db_connection()
    promo = conn.execute('SELECT * FROM promocodes WHERE code = ?', (code,)).fetchone()
    conn.close()
    if promo:
        return jsonify({"success": True, "discount": promo['discount']})
    return jsonify({"success": False})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('INSERT INTO orders (name, phone, address, total, promo_code, status) VALUES (?, ?, ?, ?, ?, ?)',
              (data['name'], data['phone'], data['address'], data['total'], data.get('promo', ''), 'Новый'))
    order_id = c.lastrowid
    for item in data['cart']:
        c.execute('INSERT INTO order_items (order_id, product_name, price, quantity) VALUES (?, ?, ?, ?)',
                  (order_id, item['name'], item['price'], item['quantity']))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "order_id": order_id})

# --- CRM И АДМИНКА ---
@app.route('/admin')
def serve_admin():
    return send_from_directory('static', 'admin.html')

# Загрузка фото
@app.route('/api/admin/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "Нет файла"}), 400
    file = request.files['file']
    ext = file.filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({"url": f"/uploads/{filename}"})

# Универсальный роут для получения данных в админке
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
        "promocodes": [dict(pc) for pc in conn.execute('SELECT * FROM promocodes').fetchall()]
    }
    conn.close()
    return jsonify(res)

# Управление товарами
@app.route('/api/admin/products', methods=['POST'])
def add_product():
    d = request.json
    conn = get_db_connection()
    conn.execute('INSERT INTO products (category_id, name, description, price, old_price, img) VALUES (?, ?, ?, ?, ?, ?)',
                 (d['category_id'], d['name'], d['description'], d['price'], d.get('old_price', 0), d['img']))
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

# Управление статусом заказа
@app.route('/api/admin/orders/<int:oid>/status', methods=['POST'])
def update_order(oid):
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = ? WHERE id = ?', (request.json['status'], oid))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# Добавление категории
@app.route('/api/admin/categories', methods=['POST'])
def add_category():
    conn = get_db_connection()
    conn.execute('INSERT INTO categories (name) VALUES (?)', (request.json['name'],))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# Добавление акции
@app.route('/api/admin/promotions', methods=['POST'])
def add_promo():
    conn = get_db_connection()
    conn.execute('INSERT INTO promotions (title, img) VALUES (?, ?)', (request.json['title'], request.json['img']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# Добавление промокода
@app.route('/api/admin/promocodes', methods=['POST'])
def add_promocode():
    conn = get_db_connection()
    conn.execute('INSERT INTO promocodes (code, discount) VALUES (?, ?)', (request.json['code'].upper(), request.json['discount']))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
