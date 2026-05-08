# -*- coding: utf-8 -*-
import sqlite3
import json
import requests
import uuid
import datetime
import random
import os
import hashlib
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_erp_v55_final'
app.permanent_session_lifetime = datetime.timedelta(days=30)

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

VK_TOKEN = "f9LHodD0cOKnmfrtQwhB_QBqCoPV4XveP_YlEok9IKDCiL-2SbV9mU5vKBqFB9sYwRMurF9pmuj6DQnTerFM"
VK_API_VERSION = "5.131"

def send_vk_message(db_user_id, user_vk_link, text):
    if not user_vk_link or "vk.com" not in user_vk_link: 
        return "Нет ссылки на VK."
    try:
        domain = user_vk_link.split('/')[-1].split('?')[0]
        vk_id = None
        if domain.startswith('id') and domain[2:].isdigit(): 
            vk_id = domain[2:]
        else:
            req_url = f"https://api.vk.com/method/utils.resolveScreenName?screen_name={domain}&access_token={VK_TOKEN}&v={VK_API_VERSION}"
            r_id = requests.get(req_url).json()
            if r_id.get('response') and r_id['response']['type'] == 'user': 
                vk_id = r_id['response']['object_id']
        
        if not vk_id: return "Не удалось распознать ID."
        
        with sqlite3.connect('shop.db') as conn:
            conn.execute("UPDATE users SET vk_id=? WHERE id=?", (str(vk_id), db_user_id))
            conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (db_user_id, text))
            
        payload = {
            "user_id": vk_id, 
            "random_id": random.randint(1, 2147483647), 
            "message": text, 
            "access_token": VK_TOKEN, 
            "v": VK_API_VERSION
        }
        res = requests.post("https://api.vk.com/method/messages.send", data=payload).json()
        if 'error' in res:
            err_code = res['error'].get('error_code')
            if err_code == 901: return "Клиент запретил сообщения."
            return f"Ошибка ВК: {res['error'].get('error_msg')}"
        return "ok"
    except Exception as e: 
        return f"Сбой отправки: {str(e)}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (key_name TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0, is_on_main INTEGER DEFAULT 0)')
        c.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL DEFAULT 0, old_price REAL DEFAULT 0, 
            stock INTEGER DEFAULT 0, category_id INTEGER, images TEXT DEFAULT "[]", unit TEXT DEFAULT "шт", 
            step REAL DEFAULT 1, active INTEGER DEFAULT 1, stickers TEXT DEFAULT "[]", rating REAL DEFAULT 5.0, 
            variations TEXT DEFAULT "", ticket_bonus INTEGER DEFAULT 0)''')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, link_url TEXT DEFAULT "", active INTEGER DEFAULT 1)')
        c.execute('''CREATE TABLE IF NOT EXISTS homepage_blocks (id INTEGER PRIMARY KEY, title TEXT, block_type TEXT, category_id INTEGER, sort_order INTEGER, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", 
            addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, 
            vk_id TEXT DEFAULT "", balance REAL DEFAULT 0, is_sysadmin INTEGER DEFAULT 0, password TEXT DEFAULT "", 
            role TEXT DEFAULT "client", comm_type TEXT DEFAULT "fixed", comm_val REAL DEFAULT 0, 
            tips_link TEXT DEFAULT "", tips_qr TEXT DEFAULT "", created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tickets_balance INTEGER DEFAULT 0, last_daily_bonus TIMESTAMP DEFAULT NULL)''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, 
            final_total REAL, bonuses_spent INTEGER, items TEXT, delivery_type TEXT, payment_type TEXT, 
            status TEXT DEFAULT "Новый", address TEXT DEFAULT "", delivery_time TEXT DEFAULT "Как можно скорее", 
            comment TEXT DEFAULT "", courier_id INTEGER DEFAULT 0, is_paid_to_courier INTEGER DEFAULT 0, 
            is_paid_to_sysadmin INTEGER DEFAULT 0, courier_rating INTEGER DEFAULT 0, courier_comment TEXT DEFAULT "", 
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS chat_messages (id INTEGER PRIMARY KEY, user_id INTEGER, is_incoming INTEGER, text TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT UNIQUE, discount_percent REAL DEFAULT 0, discount_rub REAL DEFAULT 0, min_sum REAL DEFAULT 0, is_active INTEGER DEFAULT 1, is_sysadmin_only INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS reviews (id INTEGER PRIMARY KEY, product_id INTEGER, user_id INTEGER, rating INTEGER, text TEXT, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_approved INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS contests (id INTEGER PRIMARY KEY, title TEXT, description TEXT, img_url TEXT, min_sum REAL DEFAULT 1500, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY, contest_id INTEGER, user_id INTEGER, order_id INTEGER, ticket_number TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS sysadmin_logs (id INTEGER PRIMARY KEY, amount REAL, description TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS promotions (
            id INTEGER PRIMARY KEY, title TEXT, promo_type TEXT, target_id INTEGER DEFAULT 0, 
            discount_val REAL DEFAULT 0, min_sum REAL DEFAULT 0, time_start TEXT DEFAULT "", 
            time_end TEXT DEFAULT "", active INTEGER DEFAULT 1
        )''')

        # ТАБЛИЦЫ РУЛЕТКИ
        c.execute('''CREATE TABLE IF NOT EXISTS wheel_sectors (
            id INTEGER PRIMARY KEY, title TEXT, type TEXT, value TEXT, weight INTEGER DEFAULT 10, 
            stock INTEGER DEFAULT -1, color TEXT DEFAULT "#ffffff", icon TEXT DEFAULT "🎁",
            banner_url TEXT DEFAULT "", partner_link TEXT DEFAULT "", promo_code TEXT DEFAULT "", description TEXT DEFAULT "")''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_prizes (
            id INTEGER PRIMARY KEY, user_id INTEGER, title TEXT, type TEXT, value TEXT, 
            expires_at TIMESTAMP, is_used INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            banner_url TEXT DEFAULT "", partner_link TEXT DEFAULT "", promo_code TEXT DEFAULT "", description TEXT DEFAULT "")''')

        # Миграция
        for col in ['is_on_main INTEGER DEFAULT 0']:
            try: c.execute(f'ALTER TABLE categories ADD COLUMN {col}')
            except: pass
        for col in ['link_url TEXT DEFAULT ""']:
            try: c.execute(f'ALTER TABLE banners ADD COLUMN {col}')
            except: pass
        for col in ['tickets_balance INTEGER DEFAULT 0', 'last_daily_bonus TIMESTAMP DEFAULT NULL']:
            try: c.execute(f'ALTER TABLE users ADD COLUMN {col}')
            except: pass
        for col in ['ticket_bonus INTEGER DEFAULT 0']:
            try: c.execute(f'ALTER TABLE products ADD COLUMN {col}')
            except: pass
            
        for col in ['banner_url TEXT DEFAULT ""', 'partner_link TEXT DEFAULT ""', 'promo_code TEXT DEFAULT ""', 'description TEXT DEFAULT ""']:
            try: c.execute(f'ALTER TABLE wheel_sectors ADD COLUMN {col}')
            except: pass
            try: c.execute(f'ALTER TABLE user_prizes ADD COLUMN {col}')
            except: pass

        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (key_name, value) VALUES (?,?)', [
                ('shop_name', 'У Николаича'), ('footer_text', 'Фермерские продукты от Николаича.'),
                ('package_cost', '29'), ('courier_cost', '150'), ('free_delivery_threshold', '3000'),
                ('min_order_sum', '500'), ('min_pickup_sum', '0'), ('high_demand', '0'), ('payment_details', '+7 (999) 000-00-00'), 
                ('vk_confirm_code', '00000000'), ('admin_pin', '0000'), ('pk_server', ''), ('pk_secret', ''),
                ('bg_main', '#fdfbf7'), ('bg_header', 'https://images.pexels.com/photos/1414651/pexels-photo-1414651.jpeg?auto=compress'),
                ('bg_cat', 'https://images.pexels.com/photos/413195/pexels-photo-413195.jpeg?auto=compress'), ('bg_card', 'https://images.pexels.com/photos/1297339/pexels-photo-1297339.jpeg?auto=compress'),
                ('wheel_active', '1')
            ])
            
        if c.execute("SELECT COUNT(*) FROM settings WHERE key_name='wheel_active'").fetchone()[0] == 0:
            c.execute("INSERT INTO settings (key_name, value) VALUES ('wheel_active', '1')")

        if c.execute("SELECT COUNT(*) FROM wheel_sectors").fetchone()[0] == 0:
            defaults = [
                ('Скидка 5%', 'discount', '5', 30, -1, '#ffc107', '🏷️', '', '', '', 'Скидка на весь ассортимент'),
                ('СберПрайм 30 дней', 'partner', 'SBER30', 20, -1, '#00d65f', '🏦', 'https://example.com/sber.png', 'https://sber.ru', 'SBER30', 'Крутой подарок от партнера'),
                ('Пусто', 'empty', '', 40, -1, '#e0e0e0', '😢', '', '', '', ''),
                ('Супер приз', 'product', 'Корзина продуктов', 5, 2, '#ff9800', '🎁', '', '', '', 'Свяжитесь с админом для получения')
            ]
            c.executemany("INSERT INTO wheel_sectors (title, type, value, weight, stock, color, icon, banner_url, partner_link, promo_code, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)", defaults)
    conn.commit()

init_db()

def get_db_query(query, args=(), fetch_one=False):
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        if fetch_one: 
            res = cur.fetchone()
            return dict(res) if res else None
        return [dict(row) for row in cur.fetchall()]

def get_user_by_identifier(identifier, is_vk=False):
    if not identifier: return None
    field = "vk_id" if is_vk else "phone"
    return get_db_query(f"SELECT * FROM users WHERE {field}=?", (identifier,), fetch_one=True)

def award_tickets(conn, order_id, user_id, final_total, items_json="{}"):
    contest = conn.execute("SELECT id, min_sum FROM contests WHERE active=1 LIMIT 1").fetchone()
    if contest and float(final_total) >= float(contest[1]):
        exists = conn.execute("SELECT COUNT(*) FROM tickets WHERE order_id=?", (order_id,)).fetchone()[0]
        if exists == 0:
            t_count = int(float(final_total) // float(contest[1]))
            for _ in range(t_count):
                t_num = f"{random.randint(100000, 999999)}"
                conn.execute("INSERT INTO tickets (contest_id, user_id, order_id, ticket_number) VALUES (?,?,?,?)", (contest[0], user_id, order_id, t_num))
    
    wheel_tix = int(float(final_total) // 500)
    items = json.loads(items_json) if items_json else {}
    for k, v in items.items():
        if '_gift' in k: continue
        pid = k.split('_')[0]
        p = conn.execute("SELECT ticket_bonus FROM products WHERE id=?", (pid,)).fetchone()
        if p and p[0]: 
            wheel_tix += (int(p[0]) * int(v.get('qty', 1)))
            
    if wheel_tix > 0:
        conn.execute("UPDATE users SET tickets_balance = tickets_balance + ? WHERE id=?", (wheel_tix, user_id))


# ================= ВЕБХУК БАНКА И VK =================
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
        with sqlite3.connect('shop.db') as conn: 
            conn.execute("UPDATE orders SET status='Оплачен', payment_type='online' WHERE id=?", (orderid,))
        
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
            with sqlite3.connect('shop.db') as conn: 
                conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 1, ?)", (user['id'], obj['text']))
    return 'ok'

@app.route('/api/auth/vk', methods=['POST'])
def auth_vk():
    data = request.json
    access_token = data.get('access_token')
    if not access_token: return jsonify({"error": "No token"}), 400
    
    vk_res = requests.get(f"https://api.vk.com/method/users.get?access_token={access_token}&v={VK_API_VERSION}").json()
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
        if user['password'] and user['password'] != password: 
            return jsonify({"error": "Неверный пароль."}), 403
    else:
        with sqlite3.connect('shop.db') as conn: 
            conn.execute("INSERT INTO users (phone, password, ref_code) VALUES (?, ?, ?)", 
                         (phone, password, f"REF-{uuid.uuid4().hex[:6].upper()}"))
            
    session.permanent = True
    session['user_identifier'] = phone
    session['auth_type'] = 'phone'
    return jsonify({"status": "ok"})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout(): 
    session.clear()
    return jsonify({"status": "ok"})


# ================= РУЛЕТКА (АПИ КОЛЕСА) =================
@app.route('/api/wheel/data', methods=['GET'])
def wheel_data():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "unauthorized"})
    
    sectors = get_db_query("SELECT id, title, type, color, icon FROM wheel_sectors WHERE stock != 0 ORDER BY id ASC")
    prizes = get_db_query("SELECT * FROM user_prizes WHERE user_id=? AND is_used=0 AND expires_at > ? ORDER BY id DESC", 
                          (user['id'], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                          
    is_active = get_db_query("SELECT value FROM settings WHERE key_name='wheel_active'", fetch_one=True)
    wheel_active = int(is_active['value']) if is_active else 1
                          
    return jsonify({"sectors": sectors, "tickets": user['tickets_balance'], "prizes": prizes, "wheel_active": wheel_active})

@app.route('/api/wheel/spin', methods=['POST'])
def wheel_spin():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "unauthorized"})
    
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        
        try: conn.execute("ALTER TABLE users ADD COLUMN wheel_spins INTEGER DEFAULT 0")
        except: pass
        
        curr_user = conn.execute("SELECT tickets_balance, wheel_spins FROM users WHERE id=?", (user['id'],)).fetchone()
        if not curr_user or curr_user['tickets_balance'] < 1: return jsonify({"error": "Недостаточно билетов"})
        
        conn.execute("UPDATE users SET tickets_balance = tickets_balance - 1, wheel_spins = IFNULL(wheel_spins, 0) + 1 WHERE id=?", (user['id'],))
        current_spin = (curr_user['wheel_spins'] or 0) + 1
        
        loss_setting = conn.execute("SELECT value FROM settings WHERE key_name='wheel_loss_threshold'").fetchone()
        loss_threshold = int(loss_setting['value']) if loss_setting and str(loss_setting['value']).isdigit() else 0
        
        sectors = conn.execute("SELECT * FROM wheel_sectors WHERE stock != 0 ORDER BY id ASC").fetchall()
        if not sectors: return jsonify({"error": "Колесо не настроено"})
        
        force_cheap = False
        if loss_threshold > 0 and (current_spin % loss_threshold != 0):
            force_cheap = True 
            
        total_weight = sum(s['weight'] for s in sectors if not force_cheap or s['type'] in ['empty', 'discount'])
        
        if total_weight <= 0:
            total_weight = sum(s['weight'] for s in sectors)
            force_cheap = False
            
        rand_val = random.uniform(0, total_weight)
        curr_weight = 0
        winner_sector = sectors[0]
        winner_index = 0
        
        for idx, s in enumerate(sectors):
            if force_cheap and s['type'] not in ['empty', 'discount']:
                continue
                
            curr_weight += s['weight']
            if rand_val <= curr_weight:
                winner_sector = s
                winner_index = idx
                break
                
        if winner_sector['stock'] > 0:
            conn.execute("UPDATE wheel_sectors SET stock = stock - 1 WHERE id=?", (winner_sector['id'],))
            
        if winner_sector['type'] != 'empty':
            exp = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""INSERT INTO user_prizes 
                (user_id, title, type, value, expires_at, banner_url, partner_link, promo_code, description) 
                VALUES (?,?,?,?,?,?,?,?,?)""", 
                (user['id'], winner_sector['title'], winner_sector['type'], winner_sector['value'], exp,
                 winner_sector.get('banner_url', ''), winner_sector.get('partner_link', ''), 
                 winner_sector.get('promo_code', ''), winner_sector.get('description', '')))
                         
    sector_angle = 360 / len(sectors)
    target_angle = 360 * 5 + (360 - (winner_index * sector_angle + sector_angle/2))
    
    return jsonify({
        "status": "ok", 
        "target_angle": target_angle, 
        "prize": dict(winner_sector),
        "tickets_left": curr_user['tickets_balance'] - 1
    })

@app.route('/api/wheel/daily', methods=['POST'])
def wheel_daily():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "unauthorized"})
    
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    last_bonus = user.get('last_daily_bonus', '')
    
    if last_bonus and last_bonus.startswith(today):
        return jsonify({"error": "Бонус сегодня уже получен"})
    
    with sqlite3.connect('shop.db') as conn:
        conn.execute("UPDATE users SET tickets_balance = tickets_balance + 1, last_daily_bonus=? WHERE id=?", 
                     (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user['id']))
                     
    return jsonify({"status": "ok", "tickets": user['tickets_balance'] + 1})


# ================= ВИТРИНА И ЗАКАЗЫ =================
@app.route('/')
def index():
    auth_val = session.get('user_identifier')
    auth_type = session.get('auth_type', 'phone')
    user = get_user_by_identifier(auth_val, is_vk=(auth_type=='vk')) if auth_val else None
    
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    cats = get_db_query("SELECT * FROM categories ORDER BY sort_order")
    prods = get_db_query("SELECT p.*, c.is_hidden FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1")
    
    favs = [f['product_id'] for f in get_db_query("SELECT product_id FROM favorites WHERE user_id=?", (user['id'],))] if user else []
    rev_dict = {r['product_id']: {'avg': round(r['avg_rating'], 1), 'count': r['c']} for r in get_db_query("SELECT product_id, AVG(rating) as avg_rating, COUNT(id) as c FROM reviews WHERE is_approved=1 GROUP BY product_id")}

    current_time = datetime.datetime.now().strftime("%H:%M")
    promotions = get_db_query("SELECT * FROM promotions WHERE active=1 AND promo_type='happy_hours'")
    
    for p in prods: 
        p['images'] = json.loads(p['images']) if p['images'] else []
        p['stickers'] = json.loads(p['stickers']) if p.get('stickers') else []
        p['is_fav'] = p['id'] in favs
        p['dyn_rating'] = rev_dict.get(p['id'], {}).get('avg', 5.0)
        p['rev_count'] = rev_dict.get(p['id'], {}).get('count', 0)
        p['variations'] = p.get('variations', '')
        
        for promo in promotions:
            if promo['time_start'] <= current_time <= promo['time_end']:
                if promo['target_id'] == 0 or promo['target_id'] == p['category_id']:
                    p['old_price'] = p['price']
                    p['price'] = p['price'] - (p['price'] * (promo['discount_val'] / 100))
                    if '🔥 Скидка' not in p['stickers']: p['stickers'].append('🔥 Скидка')
        
    banners = get_db_query("SELECT * FROM banners WHERE active=1")
    blocks = get_db_query("SELECT * FROM homepage_blocks WHERE active=1 ORDER BY sort_order")
    active_contest = get_db_query("SELECT * FROM contests WHERE active=1 LIMIT 1", fetch_one=True)
    
    return render_template('index.html', settings=settings, categories=cats, products=prods, banners=banners, blocks=blocks, user=user, active_contest=active_contest)

@app.route('/api/user/vip_request', methods=['POST'])
def request_vip():
    data = request.json
    phone = data.get('phone', '').strip()
    fio = data.get('fio', '').strip()
    social = data.get('social', '').strip()
    if not phone: return jsonify({"error": "Укажите телефон"}), 400
    
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    with sqlite3.connect('shop.db') as conn:
        if user: 
            conn.execute("UPDATE users SET phone=?, full_name=?, social_link=?, age_verified=1 WHERE id=?", (phone, fio, social, user['id']))
        else:
            exist = get_user_by_identifier(phone)
            if exist: 
                conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE id=?", (fio, social, exist['id']))
            else: 
                conn.execute("INSERT INTO users (phone, full_name, social_link, age_verified, ref_code) VALUES (?,?,?,1,?)", 
                             (phone, fio, social, f"REF-{uuid.uuid4().hex[:6].upper()}"))
            session.permanent = True
            session['user_identifier'] = phone
            session['auth_type'] = 'phone'
    return jsonify({"status": "ok"})

@app.route('/api/user/cabinet', methods=['GET'])
def user_cabinet():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "user not found"})
    
    tickets = get_db_query("SELECT t.ticket_number, c.title FROM tickets t JOIN contests c ON t.contest_id = c.id WHERE t.user_id=? ORDER BY t.id DESC", (user['id'],))
    
    available_orders = []
    my_orders = []
    
    if user.get('role') == 'courier': 
        my_orders = get_db_query("SELECT o.*, u.full_name as client_name, u.phone as client_phone FROM orders o JOIN users u ON o.user_id = u.id WHERE o.courier_id=? AND o.status != 'Отменен' ORDER BY o.id DESC LIMIT 30", (user['id'],))
        available_orders = get_db_query("SELECT o.*, u.full_name as client_name, u.phone as client_phone FROM orders o JOIN users u ON o.user_id = u.id WHERE o.status='Собран' AND (o.courier_id=0 OR o.courier_id IS NULL) AND o.delivery_type='courier' ORDER BY o.id DESC")
        for o in my_orders: o['items'] = json.loads(o['items'])
        for o in available_orders: o['items'] = json.loads(o['items'])
        orders = my_orders
    else: 
        orders = get_db_query("SELECT o.*, c.tips_link as c_tips, c.tips_qr as c_tips_qr, c.full_name as c_name FROM orders o LEFT JOIN users c ON o.courier_id = c.id WHERE o.user_id=? ORDER BY o.id DESC", (user['id'],))
        for o in orders: o['items'] = json.loads(o['items'])
        
    return jsonify({"user": user, "orders": orders, "available_orders": available_orders, "my_orders": my_orders, "tickets": tickets})

@app.route('/api/user/update', methods=['POST'])
def user_update():
    auth_val = session.get('user_identifier')
    if not auth_val: return jsonify({"error": "unauthorized"})
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    data = request.json
    
    addresses = json.loads(user['addresses']) if user['addresses'] else []
    if data.get('new_address') and data.get('new_address') not in addresses: 
        addresses.append(data['new_address'])
    if data.get('remove_address') and data.get('remove_address') in addresses: 
        addresses.remove(data['remove_address'])
        
    with sqlite3.connect('shop.db') as conn:
        query = "UPDATE users SET full_name=?, social_link=?, addresses=?, phone=?, tips_link=?, tips_qr=? "
        params = [data.get('full_name', user['full_name']), data.get('social_link', user['social_link']), json.dumps(addresses), data.get('phone', user['phone']), data.get('tips_link', user.get('tips_link', '')), data.get('tips_qr', user.get('tips_qr', ''))]
        if data.get('password'): 
            query += ", password=? "
            params.append(data['password'])
        query += "WHERE id=?"
        params.append(user['id'])
        conn.execute(query, tuple(params))
        
    return jsonify({"status": "ok"})

@app.route('/api/order/rate_delivery', methods=['POST'])
def rate_delivery():
    auth_val = session.get('user_identifier')
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify({"error": "unauthorized"})
    data = request.json
    with sqlite3.connect('shop.db') as conn: 
        conn.execute("UPDATE orders SET courier_rating=?, courier_comment=? WHERE id=? AND user_id=?", 
                     (data['rating'], data['comment'], data['order_id'], user['id']))
    return jsonify({"status": "ok"})

@app.route('/api/courier/action', methods=['POST'])
def courier_action():
    auth_val = session.get('user_identifier')
    user = get_user_by_identifier(auth_val, is_vk=(session.get('auth_type')=='vk'))
    if not user or user.get('role') != 'courier': return jsonify({"error": "access denied"}), 403
    
    order_id = request.json.get('order_id')
    action = request.json.get('action')
    new_status = request.json.get('status')
    
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order: return jsonify({"error": "Order not found"}), 404
        
        client = conn.execute("SELECT * FROM users WHERE id=?", (order['user_id'],)).fetchone()

        if action == 'take':
            if order['status'] != 'Собран' or order['courier_id'] not in [0, None]:
                return jsonify({"error": "Извините, этот заказ уже забрал другой курьер или он не готов."}), 400
            
            conn.execute("UPDATE orders SET status='В пути', courier_id=? WHERE id=?", (user['id'], order_id))
            if client and client['social_link']:
                courier_info = f"Курьер: {user['full_name'] or 'Наш сотрудник'}\nТелефон: {user['phone']}"
                send_vk_message(client['id'], client['social_link'], f"🚚 Ваш заказ #{order_id} передан курьеру и уже в пути к вам!\n\n{courier_info}")
                
        elif action == 'status':
            if order['courier_id'] != user['id']: return jsonify({"error": "Не ваш заказ"}), 403
            conn.execute("UPDATE orders SET status=? WHERE id=?", (new_status, order_id))
            
            if new_status == 'Выполнен':
                if order['is_paid_to_courier'] == 0:
                    payout = float(user['comm_val']) if user['comm_type'] == 'fixed' else (float(order['final_total']) * float(user['comm_val']) / 100)
                    conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (payout, user['id']))
                    conn.execute("UPDATE orders SET is_paid_to_courier=1 WHERE id=?", (order_id,))
                    award_tickets(conn, order_id, order['user_id'], order['final_total'], order['items'])
                    
                if 'is_paid_to_sysadmin' in order.keys() and order['is_paid_to_sysadmin'] == 0:
                    sysadmin_bonus = float(order['final_total']) * 0.01
                    conn.execute("UPDATE users SET balance = balance + ? WHERE role='sysadmin'", (sysadmin_bonus,))
                    conn.execute("UPDATE orders SET is_paid_to_sysadmin=1 WHERE id=?", (order_id,))
                    conn.execute("INSERT INTO sysadmin_logs (amount, description) VALUES (?, ?)", (sysadmin_bonus, f"Начисление 1% за заказ #{order_id} (Выполнен)"))

    return jsonify({"status": "ok"})

@app.route('/api/user/fav', methods=['POST'])
def toggle_fav():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
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
    return jsonify(get_db_query("SELECT r.rating, r.text, r.date, u.full_name as author FROM reviews r JOIN users u ON r.user_id = u.id WHERE r.product_id=? AND r.is_approved=1 ORDER BY r.id DESC", (prod_id,)))

@app.route('/api/user/add_review', methods=['POST'])
def add_review():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    data = request.json
    with sqlite3.connect('shop.db') as conn: 
        conn.execute("INSERT INTO reviews (product_id, user_id, rating, text) VALUES (?,?,?,?)", 
                     (data['product_id'], user['id'], data['rating'], data['text']))
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    data = request.json
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    cart_items = data.get('cart', {})
    
    has_18 = False
    base_total = 0
    gift_added = False
    free_items_discount = 0
    
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user and data.get('phone', '').strip(): 
        user = get_user_by_identifier(data.get('phone', '').strip())
        
    is_new_user = True
    if user:
        orders_count = get_db_query("SELECT COUNT(*) as c FROM orders WHERE user_id=? AND status != 'Отменен'", (user['id'],), fetch_one=True)
        if orders_count and orders_count['c'] > 0: is_new_user = False

    promotions = get_db_query("SELECT * FROM promotions WHERE active=1")
    current_time = datetime.datetime.now().strftime("%H:%M")

    for p_id_key, item in cart_items.items():
        base_p_id = str(p_id_key).split('_')[0]
        prod = get_db_query("SELECT p.*, c.is_hidden FROM products p JOIN categories c ON p.category_id = c.id WHERE p.id=?", (base_p_id,), fetch_one=True)
        
        if prod:
            if prod['is_hidden'] == 1: has_18 = True
            item_price = float(prod['price'])
            
            for promo in promotions:
                if promo['promo_type'] == 'happy_hours' and promo['time_start'] <= current_time <= promo['time_end']:
                    if promo['target_id'] == 0 or promo['target_id'] == prod['category_id']:
                        item_price = item_price - (item_price * (promo['discount_val'] / 100))
                        
                elif promo['promo_type'] == '1plus1' and (promo['target_id'] == 0 or promo['target_id'] == prod['category_id']):
                    if item['qty'] >= 3:
                        free_qty = int(item['qty'] // 3)
                        free_items_discount += (item_price * free_qty)
                        
            base_total += (item_price * float(item['qty']))

    gift_prod = None
    for promo in promotions:
        if promo['promo_type'] == 'gift' and is_new_user and base_total >= promo['min_sum']:
            gift_prod = get_db_query("SELECT id, name, images, unit, step FROM products WHERE id=?", (promo['target_id'],), fetch_one=True)
            if gift_prod: gift_added = True

    base_total -= free_items_discount
    base_total = max(0, base_total)

    delivery_type = data.get('delivery_type', 'pickup')
    promo_code = data.get('promo_code', '').strip()
    
    is_vip = user and user.get('age_verified') == 2
    force_pickup_18 = has_18 and not is_vip
    if force_pickup_18: delivery_type = 'pickup'

    package_cost = float(settings.get('package_cost', 29)) if base_total > 0 else 0
    courier_cost = float(settings.get('courier_cost', 150))
    free_threshold = float(settings.get('free_delivery_threshold', 3000))
    min_order_delivery = float(settings.get('min_order_sum', 500))
    min_order_pickup = float(settings.get('min_pickup_sum', 0))
    
    delivery_cost = 0
    if delivery_type == 'courier': 
        delivery_cost = 0 if base_total >= free_threshold else courier_cost
        
    discount_rub, sysadmin_pay, promo_status = 0, 0, ""
    if promo_code:
        promo_db = get_db_query("SELECT * FROM promocodes WHERE code=? AND is_active=1", (promo_code,), fetch_one=True)
        if not promo_db: 
            promo_status = "Неверный код"
        elif base_total < promo_db['min_sum']: 
            promo_status = f"Минимальная сумма {promo_db['min_sum']} ₽"
        elif promo_db['is_sysadmin_only'] == 1:
            if user and user.get('role') == 'sysadmin':
                sysadmin_pay = min(float(user.get('balance', 0)), base_total + package_cost + delivery_cost)
                promo_status = f"Списано с баланса: {sysadmin_pay:.0f} ₽"
            else: 
                promo_status = "Код только для Сисадмина"
        else:
            discount_rub = float(promo_db['discount_rub']) + (base_total * float(promo_db['discount_percent']) / 100)
            promo_status = f"Скидка применена!"

    final_total = max(0, base_total + package_cost + delivery_cost - discount_rub - sysadmin_pay)
    active_min_order = min_order_pickup if delivery_type == 'pickup' else min_order_delivery
    
    return jsonify({
        "items_total": base_total + free_items_discount, 
        "package_cost": package_cost, 
        "delivery_cost": delivery_cost, 
        "discount": discount_rub + free_items_discount, 
        "sysadmin_pay": sysadmin_pay, 
        "final_total": final_total, 
        "free_threshold": free_threshold, 
        "min_order": active_min_order, 
        "promo_status": promo_status, 
        "force_pickup_18": force_pickup_18,
        "gift": gift_prod
    })

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone = data.get('phone', '').strip()
    email = data.get('email', '').strip() 
    
    if not phone: return jsonify({"error": "Введите номер телефона!"}), 400

    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    with sqlite3.connect('shop.db') as conn:
        if user and session.get('auth_type') == 'vk':
            existing_phone_user = get_user_by_identifier(phone)
            if existing_phone_user and existing_phone_user['id'] != user['id']:
                conn.execute("UPDATE users SET vk_id=?, social_link=? WHERE id=?", (user['vk_id'], user['social_link'], existing_phone_user['id']))
                conn.execute("DELETE FROM users WHERE id=?", (user['id'],))
                user = get_user_by_identifier(phone)
                session['user_identifier'] = phone
                session['auth_type'] = 'phone'
            else: 
                conn.execute("UPDATE users SET phone=? WHERE id=?", (phone, user['id']))
        elif not user:
            user = get_user_by_identifier(phone)
            if not user:
                conn.execute("INSERT INTO users (phone, social_link, addresses, ref_code) VALUES (?, ?, ?, ?)", 
                             (phone, data.get('social_link', ''), json.dumps([data.get('address', '')]), f"REF-{uuid.uuid4().hex[:6].upper()}"))
                user = get_user_by_identifier(phone)
            session.permanent = True
            session['user_identifier'] = phone
            session['auth_type'] = 'phone'

    cart = data.get('cart', {})
    calc = data.get('calc')
    
    if calc.get('gift'):
        g = calc['gift']
        cart[f"{g['id']}_gift"] = {"name": f"🎁 {g['name']}", "price": 0, "qty": g['step'], "unit": g['unit'], "img": json.loads(g['images'])[0] if g['images'] else ''}

    has_18 = False
    for p_id_key, item in cart.items():
        if "_gift" in str(p_id_key): continue
        base_p_id = str(p_id_key).split('_')[0]
        db_prod = get_db_query("SELECT p.stock, p.name, c.is_hidden FROM products p JOIN categories c ON p.category_id=c.id WHERE p.id=?", (base_p_id,), fetch_one=True)
        if not db_prod or db_prod['stock'] < item['qty']: 
            return jsonify({"error": f"Товара '{item['name']}' недостаточно (остаток: {db_prod['stock'] if db_prod else 0})."}), 400
        if db_prod['is_hidden'] == 1: has_18 = True

    is_vip = user and user.get('age_verified') == 2
    force_pickup_18 = has_18 and not is_vip

    d_type = 'pickup' if force_pickup_18 else data.get('delivery_type', 'pickup')
    p_type = 'cash' if force_pickup_18 else data.get('payment_type', 'cash')
    address = data.get('address', '') if not force_pickup_18 else ''
    d_time = data.get('delivery_time', 'Как можно скорее')
    comment = data.get('comment', '')
    sysadmin_pay = calc.get('sysadmin_pay', 0)
    order_status = "Ожидает оплаты" if p_type == 'online' else "Новый"

    # ФИСКАЛИЗАЦИЯ 54-ФЗ (СБИС/PayKeeper) МАКСИМАЛЬНО ПОДРОБНАЯ (FFD 1.2)
    receipt_items = []
    total_cart_sum = sum(float(i['price']) * i['qty'] for k, i in cart.items() if '_gift' not in str(k))
    total_logistics = calc['package_cost'] + calc['delivery_cost']
    discount_ratio = calc['final_total'] / (total_cart_sum + total_logistics) if (total_cart_sum + total_logistics) > 0 else 1
    
    for p_id_key, item in cart.items():
        if "_gift" in str(p_id_key): continue
        adjusted_price = round(float(item['price']) * discount_ratio, 2)
        adjusted_sum = round(adjusted_price * item['qty'], 2)
        receipt_items.append({
            "name": item['name'][:128], 
            "price": adjusted_price, 
            "quantity": item['qty'], 
            "sum": adjusted_sum, 
            "tax": "none",
            "item_type": "goods", # Тип: Товар
            "payment_method": "full_prepayment" # Способ: Полная предоплата
        })
        
    if calc['package_cost'] > 0:
        adj_pkg = round(calc['package_cost'] * discount_ratio, 2)
        receipt_items.append({
            "name": "Упаковка заказа", 
            "price": adj_pkg, 
            "quantity": 1, 
            "sum": adj_pkg, 
            "tax": "none",
            "item_type": "service", # Тип: Услуга
            "payment_method": "full_prepayment"
        })
        
    if calc['delivery_cost'] > 0:
        adj_del = round(calc['delivery_cost'] * discount_ratio, 2)
        receipt_items.append({
            "name": "Доставка курьером", 
            "price": adj_del, 
            "quantity": 1, 
            "sum": adj_del, 
            "tax": "none",
            "item_type": "service", # Тип: Услуга
            "payment_method": "full_prepayment"
        })
        
    current_sum = sum(i['sum'] for i in receipt_items)
    diff = round(calc['final_total'] - current_sum, 2)
    if diff != 0 and receipt_items:
        # Корректировка копеек для СБИСа (добавляем к первому товару)
        receipt_items[0]['sum'] = round(receipt_items[0]['sum'] + diff, 2)
        receipt_items[0]['price'] = round(receipt_items[0]['sum'] / receipt_items[0]['quantity'], 2)

    client_email = email if email else f"{phone.replace('+', '')}@nikolaich.shop"

    # Строгий формат для PayKeeper + СБИС
    receipt_json = json.dumps({
        "clientEmail": client_email,
        "clientPhone": phone,
        "taxSystem": "usn_income", # УСН Доходы. (Если Патент - "patent")
        "items": receipt_items
    })

    with sqlite3.connect('shop.db') as conn:
        cur = conn.cursor()
        for p_id_key, item in cart.items(): 
            if "_gift" in str(p_id_key): continue
            base_p_id = str(p_id_key).split('_')[0]
            cur.execute("UPDATE products SET stock = stock - ? WHERE id=?", (item['qty'], base_p_id))
            
        cur.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items, delivery_type, payment_type, status, address, delivery_time, comment) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", 
                    (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], sysadmin_pay, json.dumps(cart), d_type, p_type, order_status, address, d_time, comment))
        order_id = cur.lastrowid
        
        if sysadmin_pay > 0: 
            conn.execute("UPDATE users SET balance = balance - ? WHERE id=?", (sysadmin_pay, user['id']))
            conn.execute("INSERT INTO sysadmin_logs (amount, description) VALUES (?, ?)", (-sysadmin_pay, f"Оплата заказа #{order_id} промокодом Сисадмина"))
            
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    if user['social_link'] and p_type != 'online': 
        send_vk_message(user['id'], user['social_link'], f"🚜 Заказ #{order_id} принят!\nСумма: {calc['final_total']:.0f} ₽.")
        
    if p_type == 'online':
        pk_server = settings.get('pk_server', '').strip().rstrip('/')
        if pk_server: 
            return jsonify({
                "status": "ok", 
                "order_id": order_id, 
                "pay_data": {
                    "url": f"{pk_server}/create/", 
                    "sum": f"{calc['final_total']}", 
                    "orderid": str(order_id), 
                    "clientid": user.get('full_name', phone) if user.get('full_name') else phone,
                    "client_email": client_email,  # <--- Вытащили в корень!
                    "client_phone": phone,         # <--- Вытащили в корень!
                    "name": f"Заказ #{order_id} (У Николаича)", # <--- Обязательно для некоторых банков
                    "service_name": f"Продукты питания (Заказ #{order_id})", # <--- Запасной ключ для Альфы
                    "receipt": receipt_json
                }
            })
        else: 
            return jsonify({"status": "error", "error": "PayKeeper не настроен."}), 400
            
    return jsonify({"status": "ok", "order_id": order_id})

@app.route('/api/chat/send_from_site', methods=['POST'])
def chat_send_site():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    text = request.json.get('text', '').strip()
    if text and user:
        with sqlite3.connect('shop.db') as conn: 
            conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 1, ?)", (user['id'], text))
    return jsonify({"status": "ok"})

@app.route('/api/chat/get_from_site', methods=['GET'])
def chat_get_site():
    user = get_user_by_identifier(session.get('user_identifier'), is_vk=(session.get('auth_type')=='vk'))
    if not user: return jsonify([])
    return jsonify(get_db_query("SELECT * FROM chat_messages WHERE user_id=? ORDER BY id ASC", (user['id'],)))

# ================= ROBOTS.TXT И ВЕРИФИКАЦИЯ PERFLUENCE =================
@app.route('/robots.txt')
def robots():
    text = "User-agent: *\nAllow: /\n\nUser-agent: Perfluence\nVerification: 89813663bd51\n"
    return text, 200, {'Content-Type': 'text/plain; charset=utf-8'}
# ================= АДМИНКА =================
@app.route('/admin')
def admin(): 
    if not session.get('is_admin'): return render_template('admin_login.html')
    return render_template('admin.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    pin = request.json.get('pin')
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    if pin == settings.get('admin_pin', '0000'): 
        session['is_admin'] = True
        return jsonify({"status": "ok"})
    return jsonify({"error": "Неверный PIN-код"}), 403

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout(): 
    session.pop('is_admin', None)
    return jsonify({"status": "ok"})

@app.route('/api/admin/<entity>', methods=['GET', 'POST', 'DELETE'])
def admin_crud(entity):
    if not session.get('is_admin'): return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'GET':
        if entity == 'warehouse': 
            prods = get_db_query("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC")
            for p in prods: 
                p['images'] = json.loads(p['images'])
                p['stickers'] = json.loads(p['stickers']) if p.get('stickers') else []
            return jsonify({"products": prods, "categories": get_db_query("SELECT * FROM categories ORDER BY sort_order")})
        elif entity == 'orders': return jsonify(get_db_query("SELECT o.*, u.phone, u.full_name, u.social_link FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC"))
        elif entity == 'users': return jsonify(get_db_query("SELECT * FROM users ORDER BY created_at DESC"))
        elif entity == 'couriers': return jsonify(get_db_query("SELECT id, full_name, phone FROM users WHERE role='courier'"))
        elif entity == 'banners': return jsonify(get_db_query("SELECT * FROM banners ORDER BY id DESC"))
        elif entity == 'settings': return jsonify({s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")})
        elif entity == 'homepage_blocks': return jsonify(get_db_query("SELECT * FROM homepage_blocks ORDER BY sort_order"))
        elif entity == 'promocodes': return jsonify(get_db_query("SELECT * FROM promocodes ORDER BY id DESC"))
        elif entity == 'promotions': return jsonify(get_db_query("SELECT * FROM promotions ORDER BY id DESC"))
        elif entity == 'reviews': return jsonify(get_db_query("SELECT r.*, u.full_name, u.phone, p.name as prod_name FROM reviews r JOIN users u ON r.user_id = u.id JOIN products p ON r.product_id = p.id ORDER BY r.id DESC"))
        elif entity == 'contests': return jsonify(get_db_query("SELECT * FROM contests ORDER BY id DESC"))
        elif entity == 'tickets': return jsonify(get_db_query("SELECT t.*, u.full_name, u.phone FROM tickets t JOIN users u ON t.user_id = u.id WHERE t.contest_id=? ORDER BY t.id DESC", (request.args.get('contest_id'),)))
        elif entity == 'sysadmin_logs': return jsonify(get_db_query("SELECT * FROM sysadmin_logs ORDER BY id DESC"))
        elif entity == 'wheel_sectors': return jsonify(get_db_query("SELECT * FROM wheel_sectors ORDER BY id ASC"))
        
    data = request.json
    if request.method == 'DELETE':
        if entity == 'sysadmin_logs': return jsonify({"error": "Удаление логов финансовой истории запрещено на уровне БД."}), 403
        table_map = {'product': 'products', 'category': 'categories'}
        table_name = table_map.get(entity, entity)
        with sqlite3.connect('shop.db') as conn: 
            conn.execute(f"DELETE FROM {table_name} WHERE id=?", (data['id'],))
        return jsonify({"status": "ok"})
    
    if request.method == 'POST':
        with sqlite3.connect('shop.db') as conn:
            if entity == 'product':
                img_json = json.dumps(data.get('images', []))
                stickers_json = json.dumps(data.get('stickers', []))
                variations = data.get('variations', '').strip()
                
                try: p_price = float(data.get('price') or 0)
                except: p_price = 0.0
                try: p_old = float(data.get('old_price') or 0)
                except: p_old = 0.0
                try: p_stock = int(data.get('stock') or 0)
                except: p_stock = 0
                try: p_step = float(data.get('step') or 1)
                except: p_step = 1.0
                try: p_cat = int(data.get('category_id') or 0)
                except: p_cat = 0
                try: p_ticket = int(data.get('ticket_bonus') or 0)
                except: p_ticket = 0

                if data.get('id'): 
                    conn.execute("""
                        UPDATE products 
                        SET name=?, desc=?, price=?, stock=?, category_id=?, images=?, unit=?, step=?, old_price=?, stickers=?, variations=?, ticket_bonus=? 
                        WHERE id=?
                    """, (data.get('name', ''), data.get('desc', ''), p_price, p_stock, p_cat, img_json, data.get('unit', 'шт'), p_step, p_old, stickers_json, variations, p_ticket, data['id']))
                else: 
                    conn.execute("""
                        INSERT INTO products 
                        (name, desc, price, stock, category_id, images, unit, step, old_price, stickers, variations, ticket_bonus) 
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (data.get('name', ''), data.get('desc', ''), p_price, p_stock, p_cat, img_json, data.get('unit', 'шт'), p_step, p_old, stickers_json, variations, p_ticket))
            
            elif entity == 'category':
                try: c_sort = int(data.get('sort_order') or 1)
                except: c_sort = 1
                try: c_hid = int(data.get('is_hidden') or 0)
                except: c_hid = 0
                try: c_main = int(data.get('is_on_main') or 0)
                except: c_main = 0

                if data.get('id'): conn.execute("UPDATE categories SET name=?, icon=?, sort_order=?, is_hidden=?, is_on_main=? WHERE id=?", (data.get('name', ''), data.get('icon', ''), c_sort, c_hid, c_main, data['id']))
                else: conn.execute("INSERT INTO categories (name, icon, sort_order, is_hidden, is_on_main) VALUES (?,?,?,?,?)", (data.get('name', ''), data.get('icon', ''), c_sort, c_hid, c_main))
            
            elif entity == 'banners':
                if data.get('id'): conn.execute("UPDATE banners SET title=?, subtitle=?, img_url=?, bg_color=?, link_cat=?, link_url=? WHERE id=?", (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat'], data.get('link_url', ''), data['id']))
                else: conn.execute("INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat, link_url) VALUES (?,?,?,?,?,?)", (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat'], data.get('link_url', '')))
            
            elif entity == 'homepage_blocks':
                if data.get('id'): conn.execute("UPDATE homepage_blocks SET title=?, block_type=?, category_id=?, sort_order=?, active=? WHERE id=?", (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active'], data['id']))
                else: conn.execute("INSERT INTO homepage_blocks (title, block_type, category_id, sort_order, active) VALUES (?,?,?,?,?)", (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active']))
            
            elif entity == 'promocodes':
                if data.get('id'): conn.execute("UPDATE promocodes SET code=?, discount_percent=?, discount_rub=?, min_sum=?, is_active=?, is_sysadmin_only=? WHERE id=?", (data['code'], data['discount_percent'], data['discount_rub'], data['min_sum'], data['is_active'], data['is_sysadmin_only'], data['id']))
                else: conn.execute("INSERT INTO promocodes (code, discount_percent, discount_rub, min_sum, is_active, is_sysadmin_only) VALUES (?,?,?,?,?,?)", (data['code'], data['discount_percent'], data['discount_rub'], data['min_sum'], data['is_active'], data['is_sysadmin_only']))
            
            elif entity == 'promotions':
                if data.get('id'): conn.execute("UPDATE promotions SET title=?, promo_type=?, target_id=?, discount_val=?, min_sum=?, time_start=?, time_end=?, active=? WHERE id=?", (data['title'], data['promo_type'], data['target_id'], data['discount_val'], data['min_sum'], data['time_start'], data['time_end'], data['active'], data['id']))
                else: conn.execute("INSERT INTO promotions (title, promo_type, target_id, discount_val, min_sum, time_start, time_end, active) VALUES (?,?,?,?,?,?,?,?)", (data['title'], data['promo_type'], data['target_id'], data['discount_val'], data['min_sum'], data['time_start'], data['time_end'], data['active']))

            elif entity == 'wheel_sectors': 
                if data.get('id'): conn.execute("UPDATE wheel_sectors SET title=?, type=?, value=?, weight=?, stock=?, color=?, icon=?, banner_url=?, partner_link=?, promo_code=?, description=? WHERE id=?", (data['title'], data['type'], data['value'], data['weight'], data['stock'], data['color'], data['icon'], data.get('banner_url', ''), data.get('partner_link', ''), data.get('promo_code', ''), data.get('description', ''), data['id']))
                else: conn.execute("INSERT INTO wheel_sectors (title, type, value, weight, stock, color, icon, banner_url, partner_link, promo_code, description) VALUES (?,?,?,?,?,?,?,?,?,?,?)", (data['title'], data['type'], data['value'], data['weight'], data['stock'], data['color'], data['icon'], data.get('banner_url', ''), data.get('partner_link', ''), data.get('promo_code', ''), data.get('description', '')))

            elif entity == 'settings':
                for key, val in data.items(): conn.execute("INSERT INTO settings (key_name, value) VALUES (?,?) ON CONFLICT(key_name) DO UPDATE SET value=?", (key, val, val))
            
            elif entity == 'reviews':
                conn.execute("UPDATE reviews SET rating=?, text=?, is_approved=? WHERE id=?", (data['rating'], data['text'], data['is_approved'], data['id']))
            
            elif entity == 'contests':
                if data.get('id'): conn.execute("UPDATE contests SET title=?, description=?, img_url=?, min_sum=?, active=? WHERE id=?", (data['title'], data['description'], data['img_url'], data['min_sum'], data['active'], data['id']))
                else: conn.execute("INSERT INTO contests (title, description, img_url, min_sum, active) VALUES (?,?,?,?,?)", (data['title'], data['description'], data['img_url'], data['min_sum'], data['active']))
            
            elif entity == 'users':
                u = get_db_query("SELECT * FROM users WHERE id=?", (data['id'],), fetch_one=True)
                if u:
                    conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, addresses=?, age_verified=?, balance=?, role=?, comm_type=?, comm_val=?, password=?, tickets_balance=? WHERE id=?", 
                        (data.get('full_name', u.get('full_name')), data.get('phone', u.get('phone')), data.get('social_link', u.get('social_link')), data.get('addresses', u.get('addresses')), 
                         data.get('age_verified', u.get('age_verified')), data.get('balance', u.get('balance')), data.get('role', u.get('role')), data.get('comm_type', u.get('comm_type')), 
                         data.get('comm_val', u.get('comm_val')), data.get('password', u.get('password')), data.get('tickets_balance', u.get('tickets_balance')), data['id']))
            
            elif entity == 'orders':
                order_id = data.get('id')
                new_status = data.get('status')
                cid_raw = data.get('courier_id')
                new_courier_id = int(cid_raw) if cid_raw and str(cid_raw).isdigit() else 0
                
                old_order = conn.execute("SELECT status, final_total, is_paid_to_courier, courier_id, user_id, delivery_type, is_paid_to_sysadmin, items FROM orders WHERE id=?", (order_id,)).fetchone()
                if old_order:
                    conn.execute("UPDATE orders SET status=?, courier_id=? WHERE id=?", (new_status, new_courier_id, order_id))
                    if new_status == 'Выполнен':
                        if old_order[2] == 0:
                            if new_courier_id > 0:
                                courier = conn.execute("SELECT comm_type, comm_val FROM users WHERE id=?", (new_courier_id,)).fetchone()
                                if courier:
                                    payout = float(courier[1]) if courier[0] == 'fixed' else (float(old_order[1]) * float(courier[1]) / 100)
                                    conn.execute("UPDATE users SET balance = balance + ? WHERE id=?", (payout, new_courier_id))
                            conn.execute("UPDATE orders SET is_paid_to_courier=1 WHERE id=?", (order_id,))
                            award_tickets(conn, order_id, old_order[4], old_order[1], old_order[7])
                            
                        if len(old_order) > 6 and old_order[6] == 0:
                            sysadmin_bonus = float(old_order[1]) * 0.01
                            conn.execute("UPDATE users SET balance = balance + ? WHERE role='sysadmin'", (sysadmin_bonus,))
                            conn.execute("UPDATE orders SET is_paid_to_sysadmin=1 WHERE id=?", (order_id,))
                            conn.execute("INSERT INTO sysadmin_logs (amount, description) VALUES (?, ?)", (sysadmin_bonus, f"Начисление 1% за заказ #{order_id} (Выполнен)"))

        return jsonify({"status": "ok"})

@app.route('/api/admin/order_chat/<int:order_id>', methods=['GET'])
def get_order_chat(order_id):
    if not session.get('is_admin'): return jsonify({'error': 'Unauthorized'}), 403
    order = get_db_query("SELECT * FROM orders WHERE id=?", (order_id,), fetch_one=True)
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    order['items'] = json.loads(order['items'])
    return jsonify({"order": order, "user": user, "messages": get_db_query("SELECT * FROM chat_messages WHERE user_id=? ORDER BY id ASC", (user['id'],)) if user else []})

@app.route('/api/admin/chat_send', methods=['POST'])
def admin_chat_send():
    if not session.get('is_admin'): return jsonify({'error': 'Unauthorized'}), 403
    data = request.json
    order = get_db_query("SELECT * FROM orders WHERE id=?", (data.get('order_id'),), fetch_one=True)
    user = get_db_query("SELECT * FROM users WHERE id=?", (order['user_id'],), fetch_one=True)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    text = f"💳 Оплата комплектации:\nПереведите по реквизитам:\n{settings.get('payment_details', 'Не указано')}\nПосле перевода отправьте скриншот сюда." if data.get('msg_type') == 'req' else (f"🚕 Николаич проверил тариф Яндекс.Логистики: {data.get('custom_val', '')} ₽." if data.get('msg_type') == 'taxi' else ("✅ Денежку увидел! Ваш заказ передан в комплектацию." if data.get('msg_type') == 'paid' else data.get('text')))
    full_text = f"👨‍🌾 Николаич:\n{text}"
    
    send_vk_message(user['id'], user['social_link'], full_text)
    with sqlite3.connect('shop.db') as conn: 
        conn.execute("INSERT INTO chat_messages (user_id, is_incoming, text) VALUES (?, 0, ?)", (user['id'], full_text))
    return jsonify({"status": "ok"})

@app.route('/api/admin/all_chats', methods=['GET'])
def admin_all_chats():
    if not session.get('is_admin'): return jsonify({'error': 'Unauthorized'}), 403
    return jsonify([get_db_query("SELECT id, phone, full_name, social_link FROM users WHERE id=?", (u['user_id'],), fetch_one=True) for u in get_db_query("SELECT DISTINCT user_id FROM chat_messages ORDER BY id DESC") if u])

if __name__ == '__main__': 
    app.run(host='0.0.0.0', port=8085)
