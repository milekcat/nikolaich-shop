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
app.secret_key = 'nikolaich_erp_v15_nocode'

# Папка для загрузки фотографий товаров
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- НАСТРОЙКИ ИИ ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

# --- НАСТРОЙКИ VK ---
VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"
VK_API_VERSION = "5.131"


# ==========================================
# 1. ЯДРО СИСТЕМЫ (VK и AI)
# ==========================================

def send_vk_message(user_vk_link, text):
    """Отправка сообщений пользователям в VK"""
    if not user_vk_link or "vk.com" not in user_vk_link: 
        return False
    try:
        domain = user_vk_link.split('/')[-1]
        req_url = f"https://api.vk.com/method/utils.resolveScreenName?screen_name={domain}&access_token={VK_TOKEN}&v={VK_API_VERSION}"
        r_id = requests.get(req_url).json()
        
        if r_id.get('response') and r_id['response']['type'] == 'user':
            peer_id = r_id['response']['object_id']
            payload = {
                "user_id": peer_id, 
                "random_id": 0, 
                "message": text, 
                "access_token": VK_TOKEN, 
                "v": VK_API_VERSION
            }
            requests.post("https://api.vk.com/method/messages.send", data=payload)
            return True
    except Exception as e:
        print(f"VK Error: {e}")
    return False

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True):
    """Единая функция обращения к нейросети"""
    payload = {
        "model": model, 
        "temperature": 0.3, 
        "messages": [
            {"role": "system", "content": sys_prompt}, 
            {"role": "user", "content": prompt}
        ]
    }
    if is_json: 
        payload["response_format"] = {"type": "json_object"}
        
    try:
        headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
        r = requests.post(AI_URL, json=payload, headers=headers, timeout=50)
        response_text = r.json()['choices'][0]['message']['content']
        return json.loads(response_text) if is_json else response_text
    except Exception as e: 
        return {"error": str(e)} if is_json else f"Ошибка ИИ: {e}"


# ==========================================
# 2. БАЗА ДАННЫХ
# ==========================================

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        
        # Настройки магазина
        c.execute('CREATE TABLE IF NOT EXISTS settings (key_name TEXT PRIMARY KEY, value TEXT)')
        
        # Каталог
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL DEFAULT 0, old_price REAL DEFAULT 0, 
            stock INTEGER DEFAULT 0, category_id INTEGER, images TEXT DEFAULT "[]", 
            unit TEXT DEFAULT "шт", step REAL DEFAULT 1, active INTEGER DEFAULT 1
        )''')
        
        # Баннеры
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        
        # НОВОЕ: Блоки главной страницы (No-Code конструктор)
        c.execute('''CREATE TABLE IF NOT EXISTS homepage_blocks (
            id INTEGER PRIMARY KEY, title TEXT, block_type TEXT, category_id INTEGER, 
            sort_order INTEGER, active INTEGER DEFAULT 1
        )''')
        
        # Клиенты и Заказы
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", 
            social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, 
            age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, 
            delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, 
            delivery_type TEXT, payment_type TEXT, status TEXT DEFAULT "Новый", 
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Базовое наполнение, если база пустая
        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (key_name, value) VALUES (?,?)', [
                ('shop_name', 'У Николаича'), 
                ('footer_text', 'Фермерские продукты с доставкой. Безупречное качество.')
            ])
            c.executemany('INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)', [
                ('Мясо свежее', '🥩', 1, 0), ('Молоко и Сыр', '🧀', 2, 0), 
                ('Овощи с грядки', '🥬', 3, 0), ('VIP Клуб (18+)', '🍷', 99, 1)
            ])
            c.execute('''INSERT INTO products (name, desc, price, old_price, stock, category_id, images, unit, step) 
                         VALUES (?,?,?,?,?,?,?,?,?)''', 
                      ('Стейк Рибай', 'Мраморная говядина, выдержка 21 день', 850, 0, 15, 1, 
                       '["https://images.unsplash.com/photo-1600891964092-4316c288032e?w=500"]', 'кг', 0.1))
            c.execute('''INSERT INTO products (name, desc, price, old_price, stock, category_id, images, unit, step) 
                         VALUES (?,?,?,?,?,?,?,?,?)''', 
                      ('Шея свиная (Акция)', 'Идеально для шашлыка', 550, 650, 20, 1, 
                       '["https://images.unsplash.com/photo-1607623814075-e51df1bd682f?w=500"]', 'кг', 0.5))
                       
            # Наполняем стартовые блоки для главной страницы
            c.executemany('INSERT INTO homepage_blocks (title, block_type, category_id, sort_order, active) VALUES (?,?,?,?,?)', [
                ('🔥 Товары по акции', 'sale', 0, 1, 1),
                ('🥩 Лучшее мясо', 'category', 1, 2, 1),
                ('🧀 Свежая молочка', 'category', 2, 3, 1)
            ])
    conn.commit()

init_db()

def get_db_query(query, args=(), fetch_one=False):
    """Вспомогательная функция для чистых SQL запросов"""
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(query, args)
        if fetch_one:
            res = cur.fetchone()
            return dict(res) if res else None
        return [dict(row) for row in cur.fetchall()]

def get_or_create_user(phone, name="Клиент", social_link=""):
    """Ищет клиента по телефону или создает нового"""
    if not phone: 
        return None
    user = get_db_query("SELECT * FROM users WHERE phone=?", (phone,), fetch_one=True)
    if not user:
        ref_code = f"REF-{uuid.uuid4().hex[:6].upper()}"
        with sqlite3.connect('shop.db') as conn:
            conn.execute("INSERT INTO users (phone, name, social_link, ref_code) VALUES (?, ?, ?, ?)", 
                         (phone, name, social_link, ref_code))
        user = get_db_query("SELECT * FROM users WHERE phone=?", (phone,), fetch_one=True)
    return user


# ==========================================
# 3. ВИТРИНА ДЛЯ КЛИЕНТОВ (FRONTEND API)
# ==========================================

@app.route('/')
def index():
    phone = session.get('phone')
    user = get_or_create_user(phone) if phone else None
    is_18_approved = (user and user['age_verified'] == 2)
    
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    
    cats = get_db_query("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=? ORDER BY sort_order", 
                        (1 if is_18_approved else 0,))
    
    prods = get_db_query("""SELECT p.* FROM products p 
                            JOIN categories c ON p.category_id = c.id 
                            WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)""", 
                         (1 if is_18_approved else 0,))
    
    for p in prods: 
        p['images'] = json.loads(p['images']) if p['images'] else []
        
    banners = get_db_query("SELECT * FROM banners WHERE active=1")
    
    # НОВОЕ: Отправляем блоки в шаблон
    blocks = get_db_query("SELECT * FROM homepage_blocks WHERE active=1 ORDER BY sort_order")
    
    return render_template('index.html', settings=settings, categories=cats, products=prods, banners=banners, blocks=blocks, user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    session['phone'] = request.json.get('phone')
    return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    data = request.json
    phone = data.get('phone')
    if get_or_create_user(phone):
        with sqlite3.connect('shop.db') as conn:
            conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE phone=?", 
                         (data.get('full_name',''), data.get('social_link',''), phone))
    session['phone'] = phone
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    data = request.json
    base_total = float(data.get('items_total', 0))
    delivery_type = data.get('delivery_type', 'pickup')
    
    items_total = base_total * 1.05 if delivery_type == 'courier' else base_total
    package_cost = 29 if items_total > 0 else 0
    delivery_cost = 0
    
    if delivery_type == 'courier':
        delivery_cost = 0 if items_total >= 3000 else 150
    
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
        cur.execute("""INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, 
                       final_total, bonuses_spent, items, delivery_type, payment_type) 
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], 
                     calc['final_total'], 0, json.dumps(data.get('cart')), d_type, p_type))
        order_id = cur.lastrowid
        
    session['phone'] = data.get('phone')
    
    if user['social_link']:
        d_str = {"pickup": "Самовывоз", "courier": "Курьер", "taxi": "Такси"}.get(d_type, d_type)
        p_str = {"cash": "Наличными", "transfer": "Перевод на карту"}.get(p_type, p_type)
        
        msg = f"🚜 Заказ #{order_id} принят!\nСумма: {calc['final_total']:.0f} ₽.\nДоставка: {d_str}.\nОплата: {p_str}."
        
        if p_type == 'transfer': 
            msg += "\n\n💳 Ожидайте, сейчас Николаич пришлет реквизиты для перевода."
        if d_type == 'taxi': 
            msg += "\n\n🚕 Николаич уточняет тариф такси до вашего адреса. Скоро напишет стоимость!"
            
        send_vk_message(user['social_link'], msg)
        
    return jsonify({"status": "ok"})


# ==========================================
# 4. ИИ - НЕЙРОСЕТЕВЫЕ МОДУЛИ
# ==========================================

@app.route('/api/ai/product_card', methods=['POST'])
def ai_product_card():
    name = request.json.get('name')
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    prompt = f"{settings.get('shop_name', 'Наш магазин')}. Напиши аппетитное короткое описание и 1 классный совет по приготовлению для товара '{name}'. Верни результат в HTML-формате (без тегов html/body)."
    return jsonify({"html": call_ai(prompt, "Ты профессиональный шеф-повар.", "gemini-2.5-pro", False)})

@app.route('/api/ai/upsell', methods=['POST'])
def ai_upsell():
    cart_items = request.json.get('cart_items', [])
    if not cart_items: 
        return jsonify([])
        
    prods = get_db_query("SELECT id, name, images, price, unit, step FROM products WHERE active=1 AND category_id != 99")
    for p in prods: 
        p['images'] = json.loads(p['images'])
        
    recommendations = [p for p in prods if p['name'] not in cart_items]
    random.shuffle(recommendations)
    return jsonify(recommendations[:3])

@app.route('/api/ai/chef', methods=['POST'])
def ai_chef():
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    prods = get_db_query("SELECT p.id, p.name FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND c.is_hidden=0")
    catalog = ", ".join([f"ID {p['id']}: {p['name']}" for p in prods])
    
    sys_prompt = f"{settings.get('shop_name', 'Наш магазин')}. Собери корзину продуктов под запрос пользователя ТОЛЬКО из этого каталога: {catalog}. ЗАПРЕЩЕНО добавлять товары 18+. Формат JSON: {{'message': 'Твой комментарий', 'cart_ids': [Массив_ID_товаров]}}"
    return jsonify(call_ai(request.json.get('query'), sys_prompt, "gemini-2.5-pro", True))

@app.route('/api/ai/gen_banner', methods=['POST'])
def ai_gen_banner():
    settings = {s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")}
    topic = request.json.get('topic')
    sys_prompt = "Ты креативный директор маркетплейса."
    prompt = f"{settings.get('shop_name', 'Магазин')}. Придумай акцию на тему: {topic}. Выдай JSON: title (заголовок), subtitle (подзаголовок), bg_color (hex код пастельного цвета), img_prompt (короткий промпт на английском для генерации картинки без текста)."
    
    res = call_ai(prompt, sys_prompt, "gemini-2.5-pro", True)
    if "error" not in res: 
        res["img_url"] = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(res['img_prompt'])}?width=800&height=400&nologo=true"
    return jsonify(res)

@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    role = request.json.get('role')
    sys_prompt = f"Ты {'опытный маркетолог' if role == 'marketer' else 'строгий юрист РФ'}."
    return jsonify({"reply": call_ai(request.json.get('msg'), sys_prompt, "gemini-2.5-pro", False)})


# ==========================================
# 5. ЦЕНТР УПРАВЛЕНИЯ (ADMIN API)
# ==========================================

@app.route('/admin')
def admin(): 
    return render_template('admin.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files: 
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    if file.filename == '': 
        return jsonify({'error': 'Empty filename'})
        
    filename = secure_filename(str(uuid.uuid4())[:8] + "_" + file.filename)
    file.save(os.path.join(UPLOAD_FOLDER, filename))
    return jsonify({'url': f'/{UPLOAD_FOLDER}/{filename}'})

@app.route('/api/admin/<entity>', methods=['GET', 'POST', 'DELETE'])
def admin_crud(entity):
    
    # GET ЗАПРОСЫ
    if request.method == 'GET':
        if entity == 'warehouse': 
            prods = get_db_query("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC")
            for p in prods: p['images'] = json.loads(p['images'])
            cats = get_db_query("SELECT * FROM categories ORDER BY sort_order")
            return jsonify({"products": prods, "categories": cats})
            
        elif entity == 'orders': 
            return jsonify(get_db_query("SELECT o.*, u.phone, u.full_name, u.social_link FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC"))
            
        elif entity == 'users': 
            return jsonify(get_db_query("SELECT * FROM users ORDER BY created_at DESC"))
            
        elif entity == 'banners': 
            return jsonify(get_db_query("SELECT * FROM banners ORDER BY id DESC"))
            
        elif entity == 'settings': 
            return jsonify({s['key_name']: s['value'] for s in get_db_query("SELECT * FROM settings")})
            
        elif entity == 'homepage_blocks': 
            # НОВОЕ: Отдаем блоки для админки
            return jsonify(get_db_query("SELECT * FROM homepage_blocks ORDER BY sort_order"))
            
        elif entity == 'analytics': 
            return jsonify(get_db_query("SELECT COUNT(*), SUM(final_total) FROM orders WHERE status != 'Отменен'", fetch_one=True))

    data = request.json
    
    # DELETE ЗАПРОСЫ
    if request.method == 'DELETE':
        with sqlite3.connect('shop.db') as conn:
            conn.execute(f"DELETE FROM {entity} WHERE id=?", (data['id'],))
        return jsonify({"status": "ok"})
        
    # POST ЗАПРОСЫ
    if request.method == 'POST':
        with sqlite3.connect('shop.db') as conn:
            if entity == 'product':
                img_json = json.dumps(data['images'])
                if data.get('id'): 
                    conn.execute("""UPDATE products SET name=?, desc=?, price=?, stock=?, category_id=?, 
                                    images=?, unit=?, step=?, old_price=? WHERE id=?""", 
                                 (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], 
                                  img_json, data['unit'], data['step'], data.get('old_price', 0), data['id']))
                else: 
                    conn.execute("""INSERT INTO products (name, desc, price, stock, category_id, images, unit, step, old_price) 
                                    VALUES (?,?,?,?,?,?,?,?,?)""", 
                                 (data['name'], data['desc'], data['price'], data['stock'], data['category_id'], 
                                  img_json, data['unit'], data['step'], data.get('old_price', 0)))
                                  
            elif entity == 'category':
                if data.get('id'): 
                    conn.execute("UPDATE categories SET name=?, icon=?, sort_order=?, is_hidden=? WHERE id=?", 
                                 (data['name'], data['icon'], data['sort_order'], data['is_hidden'], data['id']))
                else: 
                    conn.execute("INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)", 
                                 (data['name'], data['icon'], data['sort_order'], data['is_hidden']))
                                 
            elif entity == 'banners':
                if data.get('id'): 
                    conn.execute("UPDATE banners SET title=?, subtitle=?, img_url=?, bg_color=?, link_cat=? WHERE id=?", 
                                 (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat'], data['id']))
                else: 
                    conn.execute("INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat) VALUES (?,?,?,?,?)", 
                                 (data['title'], data['subtitle'], data['img_url'], data['bg_color'], data['link_cat']))
            
            # НОВОЕ: Сохранение блоков главной страницы
            elif entity == 'homepage_blocks':
                if data.get('id'): 
                    conn.execute("UPDATE homepage_blocks SET title=?, block_type=?, category_id=?, sort_order=?, active=? WHERE id=?", 
                                 (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active'], data['id']))
                else: 
                    conn.execute("INSERT INTO homepage_blocks (title, block_type, category_id, sort_order, active) VALUES (?,?,?,?,?)", 
                                 (data['title'], data['block_type'], data['category_id'], data['sort_order'], data['active']))
                                 
            elif entity == 'settings':
                for key, val in data.items(): 
                    conn.execute("INSERT INTO settings (key_name, value) VALUES (?,?) ON CONFLICT(key_name) DO UPDATE SET value=?", 
                                 (key, val, val))
                                 
            elif entity == 'orders':
                conn.execute("UPDATE orders SET status=? WHERE id=?", (data['status'], data['id']))
                if data.get('social_link'): 
                    send_vk_message(data['social_link'], f"🚜 Статус заказа #{data['id']} изменен на: {data['status']}!")
                    
            elif entity == 'users':
                conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, age_verified=? WHERE id=?", 
                             (data['full_name'], data['phone'], data['social_link'], data['age_verified'], data['id']))
                             
        return jsonify({"status": "ok"})


@app.route('/api/admin/vk_action', methods=['POST'])
def admin_vk_action():
    data = request.json
    msg_type = data.get('msg_type')
    vk_link = data.get('vk_link')
    custom_val = data.get('custom_val', '')
    
    if msg_type == 'broadcast':
        users = get_db_query("SELECT social_link FROM users WHERE social_link != '' AND social_link IS NOT NULL")
        success_count = 0
        for u in users: 
            if send_vk_message(u['social_link'], f"📣 Новости от Николаича:\n\n{custom_val}"):
                success_count += 1
        return jsonify({"status": "ok", "sent": success_count, "total": len(users)})
    
    text = ""
    if msg_type == 'req': text = "💳 Оплата заказа:\nПереведи по номеру +7 (999) 000-00-00 (Сбербанк, Иван И.).\nКак переведешь - отправь скриншот сюда, братуха!"
    elif msg_type == 'taxi': text = f"🚕 Посмотрел такси до тебя. Выходит {custom_val} ₽. Оплачиваем или сам заберешь?"
    elif msg_type == 'paid': text = "✅ Денежку увидел! Заказ пакуется, скоро отправим!"
    else: text = custom_val
        
    is_sent = send_vk_message(vk_link, f"👨‍🌾 Николаич:\n{text}")
    return jsonify({"status": "ok" if is_sent else "error"})


if __name__ == '__main__': 
    app.run(host='0.0.0.0', port=8085)
