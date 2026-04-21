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
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'nikolaich_erp_v33_legal_geo'

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- НАСТРОЙКИ ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"
VK_API_VERSION = "5.131"

def send_vk_message(db_user_id, user_vk_link, text):
    if not user_vk_link or "vk.com" not in user_vk_link: return False
    try:
        domain = user_vk_link.split('/')[-1]
        req_url = f"https://api.vk.com/method/utils.resolveScreenName?screen_name={domain}&access_token={VK_TOKEN}&v={VK_API_VERSION}"
        r_id = requests.get(req_url).json()
        if r_id.get('response') and r_id['response']['type'] == 'user':
            vk_id = r_id['response']['object_id']
            with sqlite3.connect('shop.db') as conn:
                conn.execute("UPDATE users SET vk_id=? WHERE id=?", (str(vk_id), db_user_id))
                conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (db_user_id, text))
            
            payload = {"user_id": vk_id, "random_id": 0, "message": text, "access_token": VK_TOKEN, "v": VK_API_VERSION}
            res = requests.post("https://api.vk.com/method/messages.send", data=payload).json()
            if 'error' in res: return False
            return True
    except Exception as e: print(f"VK Error: {e}")
    return False

# ИСПРАВЛЕННЫЙ ВЫЗОВ ИИ (Без response_format, который крашит прокси)
def call_ai(prompt, sys_prompt, model="gemini-2.5-flash", is_json=True, messages_history=None):
    payload = {"model": model, "temperature": 0.3}
    
    # Добавляем жесткую инструкцию вернуть ТОЛЬКО JSON без форматирования
    if is_json:
        sys_prompt += " ВЫДАЙ СТРОГО ТОЛЬКО JSON. НАЧНИ С { И ЗАКОНЧИ }. НИКАКИХ ДРУГИХ СЛОВ, НИКАКОГО МАРКДАУНА."

    if messages_history:
        payload["messages"] = [{"role": "system", "content": sys_prompt}] + messages_history
    else:
        payload["messages"] = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]

    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=30)
        
        if r.status_code != 200:
            print(f"API Error ({r.status_code}) with {model}. Switch to gemini-2.5-pro...")
            payload["model"] = "gemini-2.5-pro"
            r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=30)
            if r.status_code != 200:
                return {"error": f"Сервер ИИ недоступен. Код: {r.status_code}. Ответ: {r.text[:100]}"} if is_json else f"Ошибка ИИ: {r.status_code}"

        response_text = r.json()['choices'][0]['message']['content']
        
        if is_json:
            match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if match:
                try: return json.loads(match.group(0))
                except: return {"error": "Сбой формата: ИИ вернул поврежденный JSON."}
            return {"error": "Сбой формата: ИИ не вернул JSON."}
            
        return response_text

    except Exception as e: 
        return {"error": f"Сбой сети: {str(e)}"} if is_json else f"Сбой сети: {e}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (key_name TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL DEFAULT 0, old_price REAL DEFAULT 0, stock INTEGER DEFAULT 0, category_id INTEGER, images TEXT DEFAULT "[]", unit TEXT DEFAULT "шт", step REAL DEFAULT 1, active INTEGER DEFAULT 1)''')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('''CREATE TABLE IF NOT EXISTS homepage_blocks (id INTEGER PRIMARY KEY, title TEXT, block_type TEXT, category_id INTEGER, sort_order INTEGER, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, vk_id TEXT DEFAULT "", balance REAL DEFAULT 0, is_sysadmin INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, delivery_type TEXT, payment_type TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, address TEXT DEFAULT "")''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY, user_id INTEGER, is_incoming INTEGER, text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT UNIQUE, discount_percent REAL DEFAULT 0, discount_rub REAL DEFAULT 0, min_sum REAL DEFAULT 0, is_active INTEGER DEFAULT 1, is_sysadmin_only INTEGER DEFAULT 0)''')

        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (key_name, value) VALUES (?,?)', [
                ('shop_name', 'У Николаича'), ('footer_text', 'Фермерские продукты от Николаича.'),
                ('package_cost', '29'), ('courier_cost', '150'), ('free_delivery_threshold', '3000'),
                ('min_order_sum', '500'), ('high_demand', '0'), 
                ('payment_details', '+7 (999) 000-00-00 (Сбербанк, Николаич)'), ('vk_confirm_code', '00000000')
            ])
            c.execute("INSERT OR IGNORE INTO promocodes (code, is_sysadmin_only) VALUES ('СисадминВоздвижение', 1)")
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
        text = obj['text']
        user = get_db_query("SELECT id FROM users WHERE vk_id=?", (vk_id,), fetch_one=True)
        if user:
            with sqlite3.connect('shop.db') as conn:
                conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 1, ?)", (user['id'], text))
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
            dummy_phone = f"vk_{vk_id}"
            conn.execute("INSERT INTO users (phone, full_name, social_link, vk_id, ref_code) VALUES (?, ?, ?, ?, ?)", 
                         (dummy_phone, full_name, social_link, vk_id, f"REF-{uuid.uuid4().hex[:6].upper()}"))
        else:
            if not user['full_name']:
                conn.execute("UPDATE users SET full_name=?, social_link=? WHERE id=?", (full_name, social_link, user['id']))
    
    session['user_identifier'] = vk_id
    session['auth_type'] = 'vk'
    return jsonify({"status": "ok"})

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    phone = request.json.get('phone')
    if not get_user_by_identifier(phone):
        with sqlite3.connect('shop.db') as conn: 
            conn.execute("INSERT INTO users (phone, ref_code) VALUES (?, ?)", (phone, f"REF-{uuid.uuid4().hex[:6].upper()}"))
    session['user_identifier'] = phone
    session['auth_type'] = 'phone'
    return jsonify({"status": "ok"})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route('/')
def index():
    auth_val = session.get('user_identifier')
    auth_type = session.get('auth_type', 'phone')
    user = get_user_by_identifier(auth_val, is_vk=(auth_type=='vk')) if auth_val else None
    is_18_approved = (user and user['age_verified'] == 2)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    cats = get_db_query("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=? ORDER BY sort_order", (1 if is_18_approved else 0,))
    prods = get_db_query("SELECT p.* FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)", (1 if is_18_approved else 0,))
    for p in prods: p['images'] = json.loads(p['images']) if p['images'] else []
    banners = get_db_query("SELECT * FROM banners WHERE active=1")
    blocks = get_db_query("SELECT * FROM homepage_blocks WHERE active=1 ORDER BY sort_order")
    return render_template('index.html', settings=settings, categories=cats, products=prods, banners=banners, blocks=blocks, user=user)

@app.route('/api/user/cabinet', methods=['GET'])
def user_cabinet():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    orders = get_db_query("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user['id'],))
    for o in orders: o['items'] = json.loads(o['items'])
    return jsonify({"user": user, "orders": orders})

@app.route('/api/user/update', methods=['POST'])
def user_update():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    data = request.json
    addr_json = json.dumps([data.get('address', '')]) if data.get('address') else "[]"
    new_phone = data.get('phone', user['phone'])
    with sqlite3.connect('shop.db') as conn:
        conn.execute("UPDATE users SET full_name=?, social_link=?, addresses=?, phone=? WHERE id=?", 
                     (data.get('full_name', ''), data.get('social_link', ''), addr_json, new_phone, user['id']))
    return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    data = request.json
    auth_val = session.get('user_identifier')
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    if user:
        with sqlite3.connect('shop.db') as conn: 
            conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE id=?", (data.get('full_name',''), data.get('social_link',''), user['id']))
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    data = request.json
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    base_total = float(data.get('items_total', 0))
    delivery_type = data.get('delivery_type', 'pickup')
    promo_code = data.get('promo_code', '').strip()
    
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    
    package_cost = float(settings.get('package_cost', 29)) if base_total > 0 else 0
    courier_cost = float(settings.get('courier_cost', 150))
    free_threshold = float(settings.get('free_delivery_threshold', 3000))
    min_order = float(settings.get('min_order_sum', 500))
    
    delivery_cost = 0
    if delivery_type == 'courier':
        delivery_cost = 0 if base_total >= free_threshold else courier_cost
        
    discount_rub = 0
    sysadmin_pay = 0
    promo_status = ""

    if promo_code:
        promo = get_db_query("SELECT * FROM promocodes WHERE code=? AND is_active=1", (promo_code,), fetch_one=True)
        if not promo:
            promo_status = "Неверный код"
        elif base_total < promo['min_sum']:
            promo_status = f"Минимальная сумма {promo['min_sum']} ₽"
        elif promo['is_sysadmin_only'] == 1:
            if user and user.get('is_sysadmin') == 1:
                balance = float(user.get('balance', 0))
                total_need = base_total + package_cost + delivery_cost
                sysadmin_pay = min(balance, total_need)
                promo_status = f"Списано с баланса: {sysadmin_pay:.0f} ₽"
            else:
                promo_status = "Код только для Сисадмина"
        else:
            discount_rub = float(promo['discount_rub']) + (base_total * float(promo['discount_percent']) / 100)
            promo_status = f"Скидка применена!"

    final_total = max(0, base_total + package_cost + delivery_cost - discount_rub - sysadmin_pay)
        
    return jsonify({
        "items_total": base_total, "package_cost": package_cost, 
        "delivery_cost": delivery_cost, "discount": discount_rub, "sysadmin_pay": sysadmin_pay,
        "final_total": final_total, "free_threshold": free_threshold, 
        "min_order": min_order, "promo_status": promo_status
    })

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "Unauthorized"}), 401
    
    calc = data.get('calc')
    d_type = data.get('delivery_type', 'pickup')
    p_type = data.get('payment_type', 'cash')
    address = data.get('address', '')
    sysadmin_pay = calc.get('sysadmin_pay', 0)
    
    with sqlite3.connect('shop.db') as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items, delivery_type, payment_type, address) VALUES (?,?,?,?,?,?,?,?,?,?)", (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], sysadmin_pay, json.dumps(data.get('cart')), d_type, p_type, address))
        order_id = cur.lastrowid
        
        if sysadmin_pay > 0:
            conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (sysadmin_pay, user['id']))
            
        sysadmin_reward = calc['final_total'] * 0.01
        if sysadmin_reward > 0:
            conn.execute("UPDATE users SET balance = balance + ? WHERE is_sysadmin=1", (sysadmin_reward,))
            
    if user['social_link']:
        settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
        # ЮРИДИЧЕСКАЯ ЧИСТОТА: МЕНЯЕМ СЛОВО В СООБЩЕНИЯХ
        d_str = {"pickup": "Самовывоз", "courier": "Логистический пакет (внутри магазина)", "taxi": "Логистический пакет (через Яндекс)"}.get(d_type, d_type)
        p_str = {"cash": "Наличными", "transfer": "Перевод"}.get(p_type, p_type)
        msg = f"🚜 Заказ #{order_id} принят!\nСумма: {calc['final_total']:.0f} ₽.\nКомплектация: {d_str}.\nОплата: {p_str}."
        if address: msg += f"\nАдрес: {address}"
        if p_type == 'transfer': msg += f"\n\n💳 Ожидайте, сейчас Николаич пришлет реквизиты."
        if d_type == 'taxi': msg += "\n\n🚕 Николаич уточняет тариф логистики до вас. Скоро пришлет стоимость!"
        send_vk_message(user['id'], user['social_link'], msg)
        
    return jsonify({"status": "ok", "order_id": order_id})

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
            for p in prods: p['images'] = json.loads(p['images'])
            return jsonify({"products": prods, "categories": get_db_query("SELECT * FROM categories ORDER BY sort_order")})
        elif entity == 'orders': return jsonify(get_db_query("SELECT o.*, u.phone, u.full_name, u.social_link FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC"))
        elif entity == 'users': return jsonify(get_db_query("SELECT * FROM users ORDER BY created_at DESC"))
        elif entity == 'banners': return jsonify(get_db_query("SELECT * FROM banners ORDER BY id DESC"))
        elif entity == 'settings': return jsonify({s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")})
        elif entity == 'homepage_blocks': return jsonify(get_db_query("SELECT * FROM homepage_blocks ORDER BY sort_order"))
        elif entity == 'promocodes': return jsonify(get_db_query("SELECT * FROM promocodes ORDER BY id DESC"))

    data = request.json
    if request.method == 'DELETE':
        with sqlite3.connect('shop.db') as conn: conn.execute(f"DELETE FROM {entity} WHERE id=?", (data['id'],))
        return jsonify({"status": "ok"})
        
    if request.method == 'POST':
        with sqlite3.connect('shop.db') as conn:
            if entity == 'product':
                img_json = json.dumps(data['images'])
                if data.get('id'): conn.execute("UPDATE products SET name=?, desc=?, price=?, stock=?, category_id=?, images=?, unit=?, step=?, old_price=? WHERE id=?", (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], img_json, data['unit'], data['step'], data.get('old_price', 0), data['id']))
                else: conn.execute("INSERT INTO products (name, desc, price, stock, category_id, images, unit, step, old_price) VALUES (?,?,?,?,?,?,?,?,?)", (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], img_json, data['unit'], data['step'], data.get('old_price', 0)))
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
            elif entity == 'users':
                conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, addresses=?, age_verified=?, balance=?, is_sysadmin=? WHERE id=?", (data['full_name'], data['phone'], data['social_link'], data.get('addresses','[]'), data['age_verified'], data.get('balance', 0), data.get('is_sysadmin', 0), data['id']))
        return jsonify({"status": "ok"})

@app.route('/api/admin/order_chat/<int:order_id>', methods=['GET'])
def get_order_chat(order_id):
    order = get_db_query("SELECT * FROM orders WHERE id=?", (order_id,), fetch_one=True)
    if not order: return jsonify({"error": "Order not found"})
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    if not user: return jsonify({"error": "User not found"})
    order['items'] = json.loads(order['items'])
    messages = get_db_query("SELECT * FROM chat_messages WHERE user_id=? ORDER BY id ASC", (user['id'],))
    return jsonify({"order": order, "user": user, "messages": messages})

@app.route('/api/admin/chat_send', methods=['POST'])
def admin_chat_send():
    data = request.json
    order_id = data.get('order_id')
    text = data.get('text')
    msg_type = data.get('msg_type')
    
    order = get_db_query("SELECT * FROM orders WHERE id=?", (order_id,), fetch_one=True)
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    if msg_type == 'status':
        new_status = data.get('status')
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
        msg_text = f"🚜 Статус заказа #{order_id} изменен на: {new_status}!"
        send_vk_message(user['id'], user['social_link'], msg_text)
        return jsonify({"status": "ok"})

    if msg_type == 'req': text = f"💳 Оплата комплектации:\nПереведите по реквизитам:\n{settings.get('payment_details', 'Не указано')}\nПосле перевода отправьте скриншот сюда."
    elif msg_type == 'taxi': text = f"🚕 Николаич проверил тариф Яндекс.Логистики до вас: {data.get('custom_val', '')} ₽. Оплачиваем или сами заберете?"
    elif msg_type == 'paid': text = "✅ Денежку увидел! Ваш заказ передан в комплектацию."
    
    success = send_vk_message(user['id'], user['social_link'], f"👨‍🌾 Николаич:\n{text}")
    return jsonify({"status": "ok" if success else "error"})

@app.route('/api/admin/vk_action', methods=['POST'])
def admin_vk_action():
    data = request.json
    msg_type = data.get('msg_type')
    custom_val = data.get('custom_val', '')
    
    if msg_type == 'broadcast':
        users = get_db_query("SELECT id, social_link FROM users WHERE social_link != '' AND social_link IS NOT NULL")
        success_count = sum(1 for u in users if send_vk_message(u['id'], u['social_link'], f"📣 Новости от Николаича:\n\n{custom_val}"))
        return jsonify({"status": "ok", "sent": success_count, "total": len(users)})
    
    return jsonify({"status": "error", "msg": "Unknown action"})

# --- ИИ МАРШРУТЫ (ИСПОЛЬЗУЮТ gemini-2.5-flash) ---
@app.route('/api/ai/upsell', methods=['POST'])
def ai_upsell():
    cart_items = request.json.get('cart_items', [])
    if not cart_items: return jsonify([])
    prods = get_db_query("SELECT id, name, images, price, unit, step FROM products WHERE active=1 AND category_id != 99")
    for p in prods: p['images'] = json.loads(p['images'])
    recommendations = [p for p in prods if p['name'] not in cart_items]
    random.shuffle(recommendations)
    return jsonify(recommendations[:3])

@app.route('/api/ai/chef', methods=['POST'])
def ai_chef():
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    prods = get_db_query("SELECT p.id, p.name FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND c.is_hidden=0")
    catalog = ", ".join([f"ID {p['id']}: {p['name']}" for p in prods])
    sys_prompt = f"{settings.get('shop_name', 'Магазин')}. Собери продукты из: {catalog}. Без 18+. Выдай JSON: ключи 'message' и 'cart_ids' (список)."
    return jsonify(call_ai(request.json.get('query'), sys_prompt, "gemini-2.5-flash", True))

@app.route('/api/ai/gen_banner', methods=['POST'])
def ai_gen_banner():
    topic = request.json.get('topic', '')
    cat_name = request.json.get('category_name', '')
    sys_prompt = "Ты маркетолог. Выдай JSON: ключи title, subtitle, bg_color (hex), img_prompt (на англ)."
    prompt = f"Идея: {topic}. Категория: {cat_name}."
    res = call_ai(prompt, sys_prompt, "gemini-2.5-flash", True)
    if "error" not in res:
        res["img_url"] = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(res.get('img_prompt', 'food'))}?width=800&height=400&nologo=true"
    return jsonify(res)

@app.route('/api/ai/agent_chat', methods=['POST'])
def ai_agent_chat():
    role = "опытный маркетолог" if request.json.get('role') == 'marketer' else "строгий юрист"
    reply = call_ai(None, f"Ты {role}.", "gemini-2.5-pro", False, messages_history=request.json.get('messages', []))
    return jsonify({"reply": reply})

if __name__ == '__main__': app.run(host='0.0.0.0', port=8085)
