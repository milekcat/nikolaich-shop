# -*- coding: utf-8 -*-
import sqlite3
import json
import urllib.parse
import requests
import uuid
import datetime
import random
import os
import re
import hashlib
from flask import Flask, render_template, request, jsonify, session, redirect
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'nikolaich_erp_v48_full_scale'
app.permanent_session_lifetime = datetime.timedelta(days=30)

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

VK_TOKEN = "f9LHodD0cOKnmfrtQwhB_QBqCoPV4XveP_YlEok9IKDCiL-2SbV9mU5vKBqFB9sYwRMurF9pmuj6DQnTerFM"
VK_API_VERSION = "5.131"

def send_vk_message(db_user_id, user_vk_link, text):
    if not user_vk_link or "vk.com" not in user_vk_link: return "Нет ссылки на VK."
    try:
        domain = user_vk_link.split('/')[-1].split('?')[0]
        vk_id = None
        if domain.startswith('id') and domain[2:].isdigit(): vk_id = domain[2:]
        else:
            req_url = f"https://api.vk.com/method/utils.resolveScreenName?screen_name={domain}&access_token={VK_TOKEN}&v={VK_API_VERSION}"
            r_id = requests.get(req_url).json()
            if r_id.get('response') and r_id['response']['type'] == 'user': vk_id = r_id['response']['object_id']
        if not vk_id: return "Не удалось распознать ID."
        with sqlite3.connect('shop.db') as conn:
            conn.execute("UPDATE users SET vk_id=? WHERE id=?", (str(vk_id), db_user_id))
            conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (db_user_id, text))
        payload = {"user_id": vk_id, "random_id": random.randint(1, 2147483647), "message": text, "access_token": VK_TOKEN, "v": VK_API_VERSION}
        res = requests.post("https://api.vk.com/method/messages.send", data=payload).json()
        if 'error' in res:
            err_code = res['error'].get('error_code')
            if err_code == 901: return "Клиент запретил сообщения."
            return f"Ошибка ВК: {res['error'].get('error_msg')}"
        return "ok"
    except Exception as e: return f"Сбой отправки: {str(e)}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (key_name TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL DEFAULT 0, old_price REAL DEFAULT 0, stock INTEGER DEFAULT 0, category_id INTEGER, images TEXT DEFAULT "[]", unit TEXT DEFAULT "шт", step REAL DEFAULT 1, active INTEGER DEFAULT 1, stickers TEXT DEFAULT "[]", rating REAL DEFAULT 5.0)''')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('''CREATE TABLE IF NOT EXISTS homepage_blocks (id INTEGER PRIMARY KEY, title TEXT, block_type TEXT, category_id INTEGER, sort_order INTEGER, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, vk_id TEXT DEFAULT "", balance REAL DEFAULT 0, is_sysadmin INTEGER DEFAULT 0, password TEXT DEFAULT "")''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, delivery_type TEXT, payment_type TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, address TEXT DEFAULT "", delivery_time TEXT DEFAULT "Как можно скорее", comment TEXT DEFAULT "")''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY, user_id INTEGER, is_incoming INTEGER, text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT UNIQUE, discount_percent REAL DEFAULT 0, discount_rub REAL DEFAULT 0, min_sum REAL DEFAULT 0, is_active INTEGER DEFAULT 1, is_sysadmin_only INTEGER DEFAULT 0)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, product_id INTEGER, user_id INTEGER, rating INTEGER, text TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_approved INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER)''')

        for col in ['stickers TEXT DEFAULT "[]"', 'rating REAL DEFAULT 5.0']:
            try: c.execute(f'ALTER TABLE products ADD COLUMN {col}')
            except: pass
        for col in ['delivery_time TEXT DEFAULT "Как можно скорее"', 'comment TEXT DEFAULT ""']:
            try: c.execute(f'ALTER TABLE orders ADD COLUMN {col}')
            except: pass

        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (key_name, value) VALUES (?,?)', [
                ('shop_name', 'У Николаича'), ('footer_text', 'Фермерские продукты от Николаича.'),
                ('package_cost', '29'), ('courier_cost', '150'), ('free_delivery_threshold', '3000'),
                ('min_order_sum', '500'), ('min_pickup_sum', '0'), ('high_demand', '0'), ('payment_details', '+7 (999) 000-00-00'), 
                ('vk_confirm_code', '00000000'), ('admin_pin', '0000'),
                ('pk_server', ''), ('pk_secret', ''),
                ('bg_main', '#fdfbf7'), ('bg_header', 'https://images.pexels.com/photos/1414651/pexels-photo-1414651.jpeg?auto=compress'),
                ('bg_cat', 'https://images.pexels.com/photos/413195/pexels-photo-413195.jpeg?auto=compress'), ('bg_card', 'https://images.pexels.com/photos/1297339/pexels-photo-1297339.jpeg?auto=compress')
            ])
            c.execute("INSERT OR IGNORE INTO promocodes (code, is_sysadmin_only) VALUES ('СисадминВоздвижение', 1)")
        else:
            try: c.execute("INSERT OR IGNORE INTO settings (key_name, value) VALUES ('min_pickup_sum', '0')")
            except: pass
    conn.commit()

init_db()

def get_db_query(query, args=(), fetch_one=False):
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        if fetch_one: res = cur.fetchone(); return dict(res) if res else None
        return [dict(row) for row in cur.fetchall()]

def get_user_by_identifier(identifier, is_vk=False):
    if not identifier: return None
    field = "vk_id" if is_vk else "phone"
    return get_db_query(f"SELECT * FROM users WHERE {field}=?", (identifier,), fetch_one=True)

# ================= ПЛАТЕЖНЫЕ ВЕБХУКИ =================
@app.route('/api/paykeeper_webhook', methods=['POST'])
def paykeeper_webhook():
    data = request.form
    pk_id = data.get('id', '')
    orderid = data.get('orderid', '')
    key = data.get('key', '')
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    secret = settings.get('pk_secret', '')
    valid_hash = hashlib.md5(f"{pk_id}{secret}".encode('utf-8')).hexdigest()
    
    if valid_hash == key:
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE orders SET status='Оплачен', payment_type='online' WHERE id=?", (orderid,))
        order = get_db_query("SELECT * FROM orders WHERE id=?", (orderid,), fetch_one=True)
        if order:
            user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
            if user and user['social_link']:
                send_vk_message(user['id'], user['social_link'], f"✅ Онлайн-оплата заказа #{orderid} получена! Начинаем комплектацию.")
        return f"OK {valid_hash}"
    return "Error: Hash mismatch"

@app.route('/api/vk_webhook', methods=['POST'])
def vk_webhook():
    data = request.json
    if not data: return 'ok'
    if data.get('type') == 'confirmation':
        settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
        return settings.get('vk_confirm_code', '00000000')
    elif data.get('type') == 'message_new':
        obj = data['object']['message']
        vk_id = str(obj['from_id'])
        user = get_db_query("SELECT id FROM users WHERE vk_id=?", (vk_id,), fetch_one=True)
        if user:
            with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 1, ?)", (user['id'], obj['text']))
    return 'ok'

@app.route('/api/auth/vk', methods=['POST'])
def auth_vk():
    data = request.json
    access_token = data.get('access_token')
    if not access_token: return jsonify({"error": "No token"}), 400
    req_url = f"https://api.vk.com/method/users.get?access_token={access_token}&v={VK_API_VERSION}"
    vk_res = requests.get(req_url).json()
    if 'error' in vk_res: return jsonify({"error": "VK API error"}), 400
    vk_data = vk_res['response'][0]
    vk_id = str(vk_data['id'])
    full_name = f"{vk_data.get('first_name', '')} {vk_data.get('last_name', '')}".strip()
    social_link = f"https://vk.com/id{vk_id}"
    user = get_user_by_identifier(vk_id, is_vk=True)
    with sqlite3.connect('shop.db') as conn:
        if not user:
            conn.execute("INSERT INTO users (phone, full_name, social_link, vk_id, ref_code) VALUES (?, ?, ?, ?, ?)", 
                         (f"vk_{vk_id}", full_name, social_link, vk_id, f"REF-{uuid.uuid4().hex[:6].upper()}"))
        elif not user['full_name']:
            conn.execute("UPDATE users SET full_name=?, social_link=? WHERE id=?", (full_name, social_link, user['id']))
    session.permanent = True
    session['user_identifier'] = vk_id
    session['auth_type'] = 'vk'
    return jsonify({"status": "ok"})

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    phone = request.json.get('phone')
    password = request.json.get('password', '')
    user = get_user_by_identifier(phone)
    if user:
        if user['password'] and user['password'] != password: return jsonify({"error": "Неверный пароль."}), 403
    else:
        with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO users (phone, password, ref_code) VALUES (?, ?, ?)", (phone, password, f"REF-{uuid.uuid4().hex[:6].upper()}"))
    session.permanent = True
    session['user_identifier'] = phone
    session['auth_type'] = 'phone'
    return jsonify({"status": "ok"})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout(): session.clear(); return jsonify({"status": "ok"})

# ================= ВИТРИНА И API КЛИЕНТА =================
@app.route('/')
def index():
    auth_val = session.get('user_identifier')
    auth_type = session.get('auth_type', 'phone')
    user = get_user_by_identifier(auth_val, is_vk=(auth_type=='vk')) if auth_val else None
    is_18_approved = (user and user['age_verified'] == 2)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    cats = get_db_query("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=? ORDER BY sort_order", (1 if is_18_approved else 0,))
    prods = get_db_query("SELECT p.* FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)", (1 if is_18_approved else 0,))
    
    favs = []
    if user:
        favs_raw = get_db_query("SELECT product_id FROM favorites WHERE user_id=?", (user['id'],))
        favs = [f['product_id'] for f in favs_raw]

    # Вычисляем средние оценки
    revs = get_db_query("SELECT product_id, AVG(rating) as avg_rating, COUNT(id) as c FROM reviews WHERE is_approved=1 GROUP BY product_id")
    rev_dict = {r['product_id']: {'avg': round(r['avg_rating'], 1), 'count': r['c']} for r in revs}

    for p in prods: 
        p['images'] = json.loads(p['images']) if p['images'] else []
        p['stickers'] = json.loads(p['stickers']) if p.get('stickers') else []
        p['is_fav'] = p['id'] in favs
        p['dyn_rating'] = rev_dict.get(p['id'], {}).get('avg', 5.0)
        p['rev_count'] = rev_dict.get(p['id'], {}).get('count', 0)
        
    banners = get_db_query("SELECT * FROM banners WHERE active=1")
    blocks = get_db_query("SELECT * FROM homepage_blocks WHERE active=1 ORDER BY sort_order")
    return render_template('index.html', settings=settings, categories=cats, products=prods, banners=banners, blocks=blocks, user=user)

@app.route('/api/user/cabinet', methods=['GET'])
def user_cabinet():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "user not found"})
    orders = get_db_query("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user['id'],))
    for o in orders: o['items'] = json.loads(o['items'])
    return jsonify({"user": user, "orders": orders})

@app.route('/api/user/update', methods=['POST'])
def user_update():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    data = request.json
    addresses = json.loads(user['addresses']) if user['addresses'] else []
    if data.get('new_address') and data['new_address'] not in addresses: addresses.append(data['new_address'])
    if data.get('remove_address') and data['remove_address'] in addresses: addresses.remove(data['remove_address'])
    with sqlite3.connect('shop.db') as conn:
        query = "UPDATE users SET full_name=?, social_link=?, addresses=?, phone=? "
        params = [data.get('full_name', ''), data.get('social_link', ''), json.dumps(addresses), data.get('phone', user['phone'])]
        if data.get('password'): query += ", password=? "; params.append(data['password'])
        query += "WHERE id=?"; params.append(user['id'])
        conn.execute(query, tuple(params))
    return jsonify({"status": "ok"})

@app.route('/api/user/fav', methods=['POST'])
def toggle_fav():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    prod_id = request.json.get('product_id')
    with sqlite3.connect('shop.db') as conn:
        exists = conn.execute("SELECT id FROM favorites WHERE user_id=? AND product_id=?", (user['id'], prod_id)).fetchone()
        if exists:
            conn.execute("DELETE FROM favorites WHERE id=?", (exists[0],))
            return jsonify({"status": "removed"})
        else:
            conn.execute("INSERT INTO favorites (user_id, product_id) VALUES (?,?)", (user['id'], prod_id))
            return jsonify({"status": "added"})

@app.route('/api/product/<int:prod_id>/reviews', methods=['GET'])
def get_product_reviews(prod_id):
    revs = get_db_query("SELECT r.rating, r.text, r.date, u.full_name as author FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.product_id=? AND r.is_approved=1 ORDER BY r.id DESC", (prod_id,))
    return jsonify(revs)

@app.route('/api/user/add_review', methods=['POST'])
def add_review():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    data = request.json
    with sqlite3.connect('shop.db') as conn:
        conn.execute("INSERT INTO reviews (product_id, user_id, rating, text) VALUES (?,?,?,?)", (data['product_id'], user['id'], data['rating'], data['text']))
    return jsonify({"status": "ok"})

@app.route('/api/order/cancel', methods=['POST'])
def cancel_order():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    order_id = request.json.get('order_id')
    with sqlite3.connect('shop.db') as conn:
        order = conn.execute("SELECT status FROM orders WHERE id=? AND user_id=?", (order_id, user['id'])).fetchone()
        if order and order[0] in ['Новый', 'Ожидает оплаты', 'Оплачен']:
            conn.execute("UPDATE orders SET status='Отменен' WHERE id=?", (order_id,))
            return jsonify({"status": "ok"})
    return jsonify({"error": "Заказ не найден или его уже нельзя отменить."}), 400

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    data = request.json
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    base_total = float(data.get('items_total', 0))
    delivery_type = data.get('delivery_type', 'pickup')
    promo_code = data.get('promo_code', '').strip()
    phone = data.get('phone', '').strip()
    
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user and phone: user = get_user_by_identifier(phone)
    
    package_cost = float(settings.get('package_cost', 29)) if base_total > 0 else 0
    courier_cost = float(settings.get('courier_cost', 150))
    free_threshold = float(settings.get('free_delivery_threshold', 3000))
    min_order_delivery = float(settings.get('min_order_sum', 500))
    min_order_pickup = float(settings.get('min_pickup_sum', 0))
    
    delivery_cost = 0
    if delivery_type == 'courier': delivery_cost = 0 if base_total >= free_threshold else courier_cost
        
    discount_rub, sysadmin_pay, promo_status = 0, 0, ""
    if promo_code:
        promo = get_db_query("SELECT * FROM promocodes WHERE code=? AND is_active=1", (promo_code,), fetch_one=True)
        if not promo: promo_status = "Неверный код"
        elif base_total < promo['min_sum']: promo_status = f"Минимальная сумма {promo['min_sum']} ₽"
        elif promo['is_sysadmin_only'] == 1:
            if user and user.get('is_sysadmin') == 1:
                sysadmin_pay = min(float(user.get('balance', 0)), base_total + package_cost + delivery_cost)
                promo_status = f"Списано с баланса: {sysadmin_pay:.0f} ₽"
            else: promo_status = "Код только для Сисадмина"
        else:
            discount_rub = float(promo['discount_rub']) + (base_total * float(promo['discount_percent']) / 100)
            promo_status = f"Скидка применена!"

    final_total = max(0, base_total + package_cost + delivery_cost - discount_rub - sysadmin_pay)
    active_min_order = min_order_pickup if delivery_type == 'pickup' else min_order_delivery
    
    return jsonify({
        "items_total": base_total, "package_cost": package_cost, "delivery_cost": delivery_cost, "discount": discount_rub, "sysadmin_pay": sysadmin_pay,
        "final_total": final_total, "free_threshold": free_threshold, "min_order": active_min_order, "promo_status": promo_status
    })

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone = data.get('phone', '').strip()
    if not phone: return jsonify({"error": "Введите номер телефона!"}), 400

    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user:
        user = get_user_by_identifier(phone)
        if not user:
            with sqlite3.connect('shop.db') as conn:
                conn.execute("INSERT INTO users (phone, social_link, addresses, ref_code) VALUES (?, ?, ?, ?)", 
                             (phone, data.get('social_link', ''), json.dumps([data.get('address', '')]), f"REF-{uuid.uuid4().hex[:6].upper()}"))
            user = get_user_by_identifier(phone)
        session.permanent = True
        session['user_identifier'] = phone
        session['auth_type'] = 'phone'

    calc = data.get('calc')
    d_type = data.get('delivery_type', 'pickup')
    p_type = data.get('payment_type', 'cash')
    address = data.get('address', '')
    d_time = data.get('delivery_time', 'Как можно скорее')
    comment = data.get('comment', '')
    sysadmin_pay = calc.get('sysadmin_pay', 0)
    
    order_status = "Ожидает оплаты" if p_type == 'online' else "Новый"

    with sqlite3.connect('shop.db') as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items, delivery_type, payment_type, status, address, delivery_time, comment) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                    (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], sysadmin_pay, json.dumps(data.get('cart')), d_type, p_type, order_status, address, d_time, comment))
        order_id = cur.lastrowid
        if sysadmin_pay > 0: conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (sysadmin_pay, user['id']))
            
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    if user['social_link'] and p_type != 'online':
        d_str = {"pickup": "Самовывоз", "courier": "Логистика магазина", "taxi": "Яндекс.Доставка"}.get(d_type, d_type)
        p_str = {"cash": "Наличными", "transfer": "Перевод"}.get(p_type, p_type)
        msg = f"🚜 Заказ #{order_id} принят!\nСумма: {calc['final_total']:.0f} ₽.\nОплата: {p_str}."
        if address: msg += f"\nАдрес: {address}\nВремя: {d_time}"
        if p_type == 'transfer': msg += f"\n\n💳 Ожидайте, скоро пришлем реквизиты."
        send_vk_message(user['id'], user['social_link'], msg)
        
    if p_type == 'online':
        pk_server = settings.get('pk_server', '').strip().rstrip('/')
        if pk_server:
            pay_data = {"url": f"{pk_server}/create/", "sum": f"{int(calc['final_total'])}", "orderid": str(order_id), "clientid": phone}
            return jsonify({"status": "ok", "order_id": order_id, "pay_data": pay_data})
        else: return jsonify({"status": "error", "error": "PayKeeper не настроен."}), 400
        
    return jsonify({"status": "ok", "order_id": order_id})

@app.route('/api/chat/send_from_site', methods=['POST'])
def chat_send_site():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    text = request.json.get('text', '').strip()
    if text:
        with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 1, ?)", (user['id'], text))
    return jsonify({"status": "ok"})

@app.route('/api/chat/get_from_site', methods=['GET'])
def chat_get_site():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify([])
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    msgs = get_db_query("SELECT * FROM chat_messages WHERE user_id=? ORDER BY id ASC", (user['id'],))
    return jsonify(msgs)

@app.route('/api/ai/upsell', methods=['POST'])
def ai_upsell():
    cart_items = request.json.get('cart_items', [])
    if not cart_items: return jsonify([])
    prods = get_db_query("SELECT id, name, images, price, unit, step FROM products WHERE active=1 AND category_id != 99")
    for p in prods: p['images'] = json.loads(p['images'])
    recommendations = [p for p in prods if p['name'] not in cart_items]
    random.shuffle(recommendations)
    return jsonify(recommendations[:3])

# ================= АДМИНКА =================
@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: return jsonify({'error': 'No file part'})
    file = request.files['file']
    filename = secure_filename(str(uuid.uuid4())[:8] + "_" + file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({'url': f'/{UPLOAD_FOLDER}/{filename}'})

@app.route('/api/admin/<entity>', methods=['GET', 'POST', 'DELETE'])
def admin_crud(entity):
    if request.method == 'GET':
        if entity == 'warehouse': 
            prods = get_db_query("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC")
            for p in prods: 
                p['images'] = json.loads(p['images'])
                p['stickers'] = json.loads(p['stickers']) if p.get('stickers') else []
            return jsonify({"products": prods, "categories": get_db_query("SELECT * FROM categories ORDER BY sort_order")})
        elif entity == 'orders': return jsonify(get_db_query("SELECT o.*, u.phone, u.full_name, u.social_link FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC"))
        elif entity == 'users': return jsonify(get_db_query("SELECT * FROM users ORDER BY created_at DESC"))
        elif entity == 'banners': return jsonify(get_db_query("SELECT * FROM banners ORDER BY id DESC"))
        elif entity == 'settings': return jsonify({s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")})
        elif entity == 'homepage_blocks': return jsonify(get_db_query("SELECT * FROM homepage_blocks ORDER BY sort_order"))
        elif entity == 'promocodes': return jsonify(get_db_query("SELECT * FROM promocodes ORDER BY id DESC"))
        elif entity == 'reviews': return jsonify(get_db_query("SELECT r.*, u.full_name, u.phone, p.name as prod_name FROM reviews r JOIN users u ON r.user_id = u.id JOIN products p ON r.product_id = p.id ORDER BY r.id DESC"))
        elif entity == 'analytics':
            sales = get_db_query("SELECT DATE(date) as d, SUM(final_total) as t FROM orders WHERE status != 'Отменен' AND status != 'Новый' GROUP BY DATE(date) ORDER BY d DESC LIMIT 7")
            orders = get_db_query("SELECT items FROM orders WHERE status != 'Отменен'")
            item_counts = {}
            for o in orders:
                items = json.loads(o['items'])
                for i_id, item in items.items():
                    item_counts[item['name']] = item_counts.get(item['name'], 0) + item['qty']
            top_items = sorted(item_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            return jsonify({"sales": sales, "top": top_items})
        
    data = request.json
    if request.method == 'DELETE':
        if entity == 'orders':
            settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
            if data.get('pin') != settings.get('admin_pin', '0000'): return jsonify({"error": "Неверный PIN-код для удаления!"}), 403
        with sqlite3.connect('shop.db') as conn: conn.execute(f"DELETE FROM {entity} WHERE id=?", (data['id'],))
        return jsonify({"status": "ok"})
    
    if request.method == 'POST':
        with sqlite3.connect('shop.db') as conn:
            if entity == 'product':
                img_json = json.dumps(data['images'])
                stickers_json = json.dumps(data.get('stickers', []))
                if data.get('id'): conn.execute("UPDATE products SET name=?, desc=?, price=?, stock=?, category_id=?, images=?, unit=?, step=?, old_price=?, stickers=? WHERE id=?", (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], img_json, data['unit'], data['step'], data.get('old_price', 0), stickers_json, data['id']))
                else: conn.execute("INSERT INTO products (name, desc, price, stock, category_id, images, unit, step, old_price, stickers) VALUES (?,?,?,?,?,?,?,?,?,?)", (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], img_json, data['unit'], data['step'], data.get('old_price', 0), stickers_json))
            elif entity == 'category':
                if data.get('id'): conn.execute("UPDATE categories SET name=?, icon=?, sort_order=?, is_hidden=? WHERE id=?", (data['name'], data['icon'], data['sort_order'], data['is_hidden'], data['id']))
                else: conn.execute("INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)", (data['name'], data['icon'], data['sort_order'], data['is_hidden']))
            elif entity == 'banners':
                if data.get('id'): conn.execute("UPDATE banners SET title=?, subtitle=?, img_url=?, bg_color=?, link_cat=? WHERE id=?", (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat'], data['id']))
                else: conn.execute("INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat) VALUES (?,?,?,?,?)", (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat']))
            elif entity == 'homepage_blocks':
                if data.get('id'): conn.execute("UPDATE homepage_blocks SET title=?, block_type=?, category_id=?, sort_order=?, active=? WHERE id=?", (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active'], data['id']))
                else: conn.execute("INSERT INTO homepage_blocks (title, block_type, category_id, sort_order, active) VALUES (?,?,?,?,?)", (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active']))
            elif entity == 'promocodes':
                if data.get('id'): conn.execute("UPDATE promocodes SET code=?, discount_percent=?, discount_rub=?, min_sum=?, is_active=?, is_sysadmin_only=? WHERE id=?", (data['code'], data['discount_percent'], data['discount_rub'], data['min_sum'], data['is_active'], data['is_sysadmin_only'], data['id']))
                else: conn.execute("INSERT INTO promocodes (code, discount_percent, discount_rub, min_sum, is_active, is_sysadmin_only) VALUES (?,?,?,?,?,?)", (data['code'], data['discount_percent'], data['discount_rub'], data['min_sum'], data['is_active'], data['is_sysadmin_only']))
            elif entity == 'settings':
                for key, val in data.items(): conn.execute("INSERT INTO settings (key_name, value) VALUES (?,?) ON CONFLICT(key_name) DO UPDATE SET value=?", (key, val, val))
            elif entity == 'orders':
                conn.execute("UPDATE orders SET status=? WHERE id=?", (data['status'], data['id']))
            elif entity == 'reviews':
                conn.execute("UPDATE reviews SET rating=?, text=?, is_approved=? WHERE id=?", (data['rating'], data['text'], data['is_approved'], data['id']))
            elif entity == 'users':
                conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, addresses=?, age_verified=?, balance=?, is_sysadmin=?, password=? WHERE id=?", (data['full_name'], data['phone'], data['social_link'], data.get('addresses','[]'), data['age_verified'], data.get('balance', 0), data.get('is_sysadmin', 0), data.get('password', ''), data['id']))
        return jsonify({"status": "ok"})

@app.route('/api/admin/order_chat/<int:order_id>', methods=['GET'])
def get_order_chat(order_id):
    order = get_db_query("SELECT * FROM orders WHERE id=?", (order_id,), fetch_one=True)
    if not order: return jsonify({"error": "Order not found"})
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    order['items'] = json.loads(order['items'])
    messages = get_db_query("SELECT * FROM chat_messages WHERE user_id=? ORDER BY id ASC", (user['id'],)) if user else []
    return jsonify({"order": order, "user": user, "messages": messages})

@app.route('/api/admin/chat_send', methods=['POST'])
def admin_chat_send():
    data = request.json
    order = get_db_query("SELECT * FROM orders WHERE id=?", (data.get('order_id'),), fetch_one=True)
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    if data.get('msg_type') == 'status':
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE orders SET status=? WHERE id=?", (data.get('status'), data.get('order_id')))
        msg_text = f"🚜 Статус заказа #{data.get('order_id')} изменен на: {data.get('status')}!"
        send_vk_message(user['id'], user['social_link'], msg_text)
        with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (user['id'], msg_text))
        return jsonify({"status": "ok"})
        
    text = ""
    if data.get('msg_type') == 'req': text = f"💳 Оплата комплектации:\nПереведите по реквизитам:\n{settings.get('payment_details', 'Не указано')}\nПосле перевода отправьте скриншот сюда."
    elif data.get('msg_type') == 'taxi': text = f"🚕 Николаич проверил тариф Яндекс.Логистики: {data.get('custom_val', '')} ₽."
    elif data.get('msg_type') == 'paid': text = "✅ Денежку увидел! Ваш заказ передан в комплектацию."
    elif data.get('msg_type') == 'custom': text = data.get('text')
    
    full_text = f"👨‍🌾 Николаич:\n{text}"
    send_vk_message(user['id'], user['social_link'], full_text)
    with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (user['id'], full_text))
    return jsonify({"status": "ok"})

@app.route('/api/admin/all_chats', methods=['GET'])
def admin_all_chats():
    users_with_msgs = get_db_query("SELECT DISTINCT user_id FROM chat_messages ORDER BY id DESC")
    res = []
    for u in users_with_msgs:
        user = get_db_query("SELECT id, phone, full_name, social_link FROM users WHERE id=?", (u['user_id'],), fetch_one=True)
        if user: res.append(user)
    return jsonify(res)

@app.route('/api/admin/vk_action', methods=['POST'])
def admin_vk_action():
    data = request.json
    if data.get('msg_type') == 'broadcast':
        users = get_db_query("SELECT id, social_link FROM users WHERE social_link != '' AND social_link IS NOT NULL")
        success_count = sum(1 for u in users if send_vk_message(u['id'], u['social_link'], f"📣 Новости от Николаича:\n\n{data.get('custom_val', '')}") == "ok")
        return jsonify({"status": "ok", "sent": success_count, "total": len(users)})
    return jsonify({"status": "error", "msg": "Unknown action"})

if __name__ == '__main__': app.run(host='0.0.0.0', port=8085)
