# -*- coding: utf-8 -*-
import sqlite3
import json
import urllib.parse
import requests
import uuid
import datetime
import random
import os
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'nikolaich_erp_v22_ultimate'

UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- НАСТРОЙКИ ИИ ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

# --- НАСТРОЙКИ VK ---
VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"
VK_API_VERSION = "5.131"

def send_vk_message(user_vk_link, text):
    if not user_vk_link or "vk.com" not in user_vk_link: return False
    try:
        domain = user_vk_link.split('/')[-1]
        req_url = f"https://api.vk.com/method/utils.resolveScreenName?screen_name={domain}&access_token={VK_TOKEN}&v={VK_API_VERSION}"
        r_id = requests.get(req_url).json()
        if r_id.get('response') and r_id['response']['type'] == 'user':
            payload = {
                "user_id": r_id['response']['object_id'], "random_id": 0, 
                "message": text, "access_token": VK_TOKEN, "v": VK_API_VERSION
            }
            res = requests.post("https://api.vk.com/method/messages.send", data=payload).json()
            if 'error' in res: return False
            return True
    except Exception as e: print(f"VK Error: {e}")
    return False

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True, messages_history=None):
    payload = {"model": model, "temperature": 0.3}
    if messages_history:
        # Для чата передаем историю
        msgs = [{"role": "system", "content": sys_prompt}] + messages_history
        payload["messages"] = msgs
    else:
        # Для обычных запросов
        payload["messages"] = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]
        
    if is_json: payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=50)
        return json.loads(r.json()['choices'][0]['message']['content']) if is_json else r.json()['choices'][0]['message']['content']
    except Exception as e: 
        return {"error": str(e)} if is_json else f"Ошибка ИИ: {e}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (key_name TEXT PRIMARY KEY, value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL DEFAULT 0, old_price REAL DEFAULT 0, stock INTEGER DEFAULT 0, category_id INTEGER, images TEXT DEFAULT "[]", unit TEXT DEFAULT "шт", step REAL DEFAULT 1, active INTEGER DEFAULT 1)''')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('''CREATE TABLE IF NOT EXISTS homepage_blocks (id INTEGER PRIMARY KEY, title TEXT, block_type TEXT, category_id INTEGER, sort_order INTEGER, active INTEGER DEFAULT 1)''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, delivery_type TEXT, payment_type TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # Настройки по умолчанию
        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (key_name, value) VALUES (?,?)', [
                ('shop_name', 'У Николаича'), 
                ('footer_text', 'Фермерские продукты с доставкой.'),
                ('package_cost', '29'),
                ('courier_cost', '150'),
                ('free_delivery_threshold', '3000')
            ])
            c.executemany('INSERT INTO homepage_blocks (title, block_type, category_id, sort_order, active) VALUES (?,?,?,?,?)', [('🔥 Товары по акции', 'sale', 0, 1, 1)])
    conn.commit()

init_db()

def get_db_query(query, args=(), fetch_one=False):
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        if fetch_one: res = cur.fetchone(); return dict(res) if res else None
        return [dict(row) for row in cur.fetchall()]

def get_or_create_user(phone, name="Клиент", social_link=""):
    if not phone: return None
    user = get_db_query("SELECT * FROM users WHERE phone=?", (phone,), fetch_one=True)
    if not user:
        with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO users (phone, name, social_link, ref_code) VALUES (?, ?, ?, ?)", (phone, name, social_link, f"REF-{uuid.uuid4().hex[:6].upper()}"))
        user = get_db_query("SELECT * FROM users WHERE phone=?", (phone,), fetch_one=True)
    return user

@app.route('/')
def index():
    phone = session.get('phone')
    user = get_or_create_user(phone) if phone else None
    is_18_approved = (user and user['age_verified'] == 2)
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    cats = get_db_query("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=? ORDER BY sort_order", (1 if is_18_approved else 0,))
    prods = get_db_query("SELECT p.* FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)", (1 if is_18_approved else 0,))
    for p in prods: p['images'] = json.loads(p['images']) if p['images'] else []
    banners = get_db_query("SELECT * FROM banners WHERE active=1")
    blocks = get_db_query("SELECT * FROM homepage_blocks WHERE active=1 ORDER BY sort_order")
    return render_template('index.html', settings=settings, categories=cats, products=prods, banners=banners, blocks=blocks, user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    session['phone'] = request.json.get('phone')
    return jsonify({"status": "ok"})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.pop('phone', None)
    return jsonify({"status": "ok"})

@app.route('/api/user/cabinet', methods=['GET'])
def user_cabinet():
    phone = session.get('phone')
    if not phone: return jsonify({"error": "unauthorized"})
    user = get_or_create_user(phone)
    orders = get_db_query("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC", (user['id'],))
    for o in orders: o['items'] = json.loads(o['items'])
    return jsonify({"user": user, "orders": orders})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    data = request.json
    phone = data.get('phone')
    if get_or_create_user(phone):
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE phone=?", (data.get('full_name',''), data.get('social_link',''), phone))
    session['phone'] = phone
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    data = request.json
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    base_total = float(data.get('items_total', 0))
    delivery_type = data.get('delivery_type', 'pickup')
    
    package_cost = float(settings.get('package_cost', 29)) if base_total > 0 else 0
    courier_cost = float(settings.get('courier_cost', 150))
    free_threshold = float(settings.get('free_delivery_threshold', 3000))
    
    # Наценку 5% убираем, так как теперь есть фиксированная стоимость курьера из БД
    items_total = base_total
    
    delivery_cost = 0
    if delivery_type == 'courier':
        delivery_cost = 0 if items_total >= free_threshold else courier_cost
        
    return jsonify({
        "items_total": items_total, 
        "package_cost": package_cost, 
        "delivery_cost": delivery_cost, 
        "final_total": items_total + package_cost + delivery_cost
    })

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    user = get_or_create_user(data.get('phone'), social_link=data.get('social_link', ''))
    calc = data.get('calc')
    d_type = data.get('delivery_type', 'pickup')
    p_type = data.get('payment_type', 'cash')
    with sqlite3.connect('shop.db') as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items, delivery_type, payment_type) VALUES (?,?,?,?,?,?,?,?,?)", (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], 0, json.dumps(data.get('cart')), d_type, p_type))
        order_id = cur.lastrowid
    session['phone'] = data.get('phone')
    
    if user['social_link']:
        d_str = {"pickup": "Самовывоз", "courier": "Курьер", "taxi": "Такси"}.get(d_type, d_type)
        p_str = {"cash": "Наличными", "transfer": "Перевод"}.get(p_type, p_type)
        msg = f"🚜 Заказ #{order_id} принят!\nСумма: {calc['final_total']:.0f} ₽.\nДоставка: {d_str}.\nОплата: {p_str}."
        if p_type == 'transfer': msg += "\n\n💳 Ожидайте, сейчас Николаич пришлет реквизиты."
        if d_type == 'taxi': msg += "\n\n🚕 Николаич уточняет тариф такси. Скоро пришлет стоимость!"
        send_vk_message(user['social_link'], msg)
        
    return jsonify({"status": "ok", "order_id": order_id})

@app.route('/api/ai/product_card', methods=['POST'])
def ai_product_card():
    name = request.json.get('name')
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    prompt = f"{settings.get('shop_name', 'Магазин')}. Напиши аппетитное описание и совет для товара '{name}'. Верни HTML."
    return jsonify({"html": call_ai(prompt, "Ты профессиональный шеф-повар.", "gemini-2.5-pro", False)})

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
    sys_prompt = f"{settings.get('shop_name', 'Магазин')}. Собери корзину продуктов ТОЛЬКО из: {catalog}. Без 18+. JSON: {{'message': 'Текст', 'cart_ids': [ID]}}"
    return jsonify(call_ai(request.json.get('query'), sys_prompt, "gemini-2.5-pro", True))

@app.route('/api/ai/gen_banner', methods=['POST'])
def ai_gen_banner():
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    topic = request.json.get('topic', '')
    cat_name = request.json.get('category_name', '')
    context = f" Идея: {topic}."
    if cat_name: context += f" Категория: {cat_name}."
    sys_prompt = "Ты креативный директор маркетплейса."
    prompt = f"Магазин: {settings.get('shop_name', 'Ферма')}.{context} Выдай JSON: title, subtitle, bg_color (hex пастельный), img_prompt (короткий промпт на английском для 3D картинки продукта без текста)."
    res = call_ai(prompt, sys_prompt, "gemini-2.5-pro", True)
    if "error" not in res: 
        res["img_url"] = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(res.get('img_prompt', 'food'))}?width=800&height=400&nologo=true"
    return jsonify(res)

@app.route('/api/ai/agent_chat', methods=['POST'])
def ai_agent_chat():
    """Новый эндпоинт для полноценного чата с ИИ"""
    role = "опытный маркетолог, помогающий фермерскому магазину" if request.json.get('role') == 'marketer' else "строгий юрист РФ по торговле"
    messages = request.json.get('messages', [])
    reply = call_ai(None, f"Ты {role}.", "gemini-2.5-pro", False, messages_history=messages)
    return jsonify({"reply": reply})

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
            elif entity == 'settings':
                for key, val in data.items(): conn.execute("INSERT INTO settings (key_name, value) VALUES (?,?) ON CONFLICT(key_name) DO UPDATE SET value=?", (key, val, val))
            elif entity == 'orders':
                conn.execute("UPDATE orders SET status=? WHERE id=?", (data['status'], data['id']))
                if data.get('social_link'): send_vk_message(data['social_link'], f"🚜 Статус заказа #{data['id']} изменен на: {data['status']}!")
            elif entity == 'users':
                conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, age_verified=? WHERE id=?", (data['full_name'], data['phone'], data['social_link'], data['age_verified'], data['id']))
        return jsonify({"status": "ok"})

@app.route('/api/admin/vk_action', methods=['POST'])
def admin_vk_action():
    data = request.json
    msg_type = data.get('msg_type')
    vk_link = data.get('vk_link')
    custom_val = data.get('custom_val', '')
    
    if msg_type == 'broadcast':
        users = get_db_query("SELECT social_link FROM users WHERE social_link != '' AND social_link IS NOT NULL")
        success_count = sum(1 for u in users if send_vk_message(u['social_link'], f"📣 Новости от Николаича:\n\n{custom_val}"))
        return jsonify({"status": "ok", "sent": success_count, "total": len(users)})
    
    text = {"req": "💳 Оплата заказа:\nПереведи по номеру +7 (999) 000-00-00. Скриншот скинь сюда!", "taxi": f"🚕 Такси до тебя выходит {custom_val} ₽. Оплачиваем или сам заберешь?", "paid": "✅ Денежку увидел! Заказ пакуется!", "direct": custom_val}.get(msg_type, custom_val)
    return jsonify({"status": "ok" if send_vk_message(vk_link, f"👨‍🌾 Николаич:\n{text}") else "error"})

if __name__ == '__main__': app.run(host='0.0.0.0', port=8085)
