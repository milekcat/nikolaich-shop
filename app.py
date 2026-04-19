# -*- coding: utf-8 -*-
import sqlite3, json, urllib.parse, requests, uuid, datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_shadow_v8'

SHOP_INFO = "Магазин фермерских продуктов 'У Николаича'. г. Ярославль."
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True):
    payload = {"model": model, "temperature": 0.2, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]}
    if is_json: payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=50)
        content = r.json()['choices'][0]['message']['content']
        return json.loads(content) if is_json else content
    except Exception as e: return {"error": str(e)} if is_json else f"Ошибка ИИ: {e}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, img TEXT, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT '', 
            social_link TEXT DEFAULT '', addresses TEXT DEFAULT '[]', bonuses INTEGER DEFAULT 0, 
            age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            # 7 КАТЕГОРИЙ
            cats = [
                ('Мясо свежее','🥩', 1, 0), ('Молоко и Сыр','🧀', 2, 0), ('Овощи с грядки','🥬', 3, 0), 
                ('Птица и Яйца','🥚', 4, 0), ('Домашняя лепка','🥟', 5, 0), ('Соленья и Варенья','🍯', 6, 0), 
                ('VIP Клуб (18+)','🍷', 99, 1)
            ]
            c.executemany('INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)', cats)
            
            # 30+ ТОВАРОВ
            prods = [
                # Мясо (1)
                ('Стейк Рибай', 'Мраморная говядина, выдержка 21 день', 850, 15, 1, '🥩'),
                ('Шея свиная', 'Идеально для шашлыка, 1 кг', 550, 20, 1, '🥩'),
                ('Бараньи ребрышки', 'Молодой барашек, 1 кг', 700, 10, 1, '🍖'),
                ('Фарш домашний', 'Свинина + Говядина, 1 кг', 450, 25, 1, '🥩'),
                ('Сало копченое', 'На вишневой щепе, 500г', 350, 15, 1, '🥓'),
                
                # Молоко и Сыр (2)
                ('Молоко коровье', 'Утренний надой, 1 литр', 120, 50, 2, '🥛'),
                ('Творог 9%', 'Деревенский, 500г', 250, 30, 2, '🥣'),
                ('Сметана густая', 'Ложка стоит, 250г', 150, 40, 2, '🍶'),
                ('Сыр Сулугуни', 'Домашний, слабосоленый, 300г', 380, 15, 2, '🧀'),
                ('Масло сливочное', '82.5%, ГОСТ, 200г', 220, 25, 2, '🧈'),
                
                # Овощи (3)
                ('Картофель', 'Сорт Гала, желтый, 1 кг', 60, 100, 3, '🥔'),
                ('Помидоры розовые', 'Сладкие, мясистые, 1 кг', 280, 40, 3, '🍅'),
                ('Огурцы хрустящие', 'С пупырышками, 1 кг', 180, 50, 3, '🥒'),
                ('Лук репчатый', 'Острый, 1 кг', 50, 80, 3, '🧅'),
                ('Зелень свежая', 'Укроп, петрушка, кинза (пучок)', 70, 60, 3, '🌿'),
                
                # Птица (4)
                ('Курица суповая', 'Фермерская, тушка ~1.5 кг', 350, 20, 4, '🐔'),
                ('Филе индейки', 'Диетическое мясо, 1 кг', 480, 15, 4, '🦃'),
                ('Яйца куриные', 'Отборные, желток яркий, 10 шт', 130, 100, 4, '🥚'),
                ('Яйца перепелиные', 'Полезные, 20 шт', 160, 40, 4, '🥚'),
                
                # Лепка (5)
                ('Пельмени с говядиной', 'Ручная лепка, 1 кг', 650, 30, 5, '🥟'),
                ('Вареники с картошкой', 'С жареным лучком, 1 кг', 350, 25, 5, '🥟'),
                ('Котлеты по-киевски', 'С маслицем внутри, 4 шт', 420, 20, 5, '🧆'),
                ('Блинчики с мясом', 'Тонкие, домашние, 500г', 320, 20, 5, '🥞'),
                
                # Соленья (6)
                ('Огурчики соленые', 'Бочковые, с чесноком, 1л', 250, 15, 6, '🥒'),
                ('Капуста квашеная', 'Хрустящая, с клюквой, 1 кг', 180, 20, 6, '🥗'),
                ('Грибочки маринованные', 'Белые и подосиновики, 0.5л', 450, 10, 6, '🍄'),
                ('Мед липовый', 'Своя пасека, 0.5л', 500, 15, 6, '🍯'),
                ('Варенье малиновое', 'Как у бабушки, 0.5л', 350, 12, 6, '🍓'),
                
                # VIP 18+ (7)
                ('Настойка Кедровая', 'На орешках, 0.5л', 900, 15, 7, '🍷'),
                ('Хреновуха', 'Пробивает до слез, 0.5л', 850, 10, 7, '🥃'),
                ('Самогон Пшеничный', 'Двойной перегон, 0.5л', 1200, 8, 7, '🍶'),
                ('Наливка Вишневая', 'Сладкая, дамская, 0.5л', 950, 12, 7, '🍒')
            ]
            c.executemany('INSERT INTO products (name, desc, price, stock, category_id, img) VALUES (?,?,?,?,?,?)', prods)
    conn.commit()

init_db()

def get_or_create_user(phone, name="Клиент"):
    if not phone: return None
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE phone=?", (phone,))
        u = c.fetchone()
        if not u:
            ref = f"REF-{uuid.uuid4().hex[:6].upper()}"
            c.execute("INSERT INTO users (phone, name, ref_code) VALUES (?, ?, ?)", (phone, name, ref))
            conn.commit()
            c.execute("SELECT * FROM users WHERE phone=?", (phone,))
            u = c.fetchone()
        return dict(zip([col[0] for col in c.description], u))

@app.route('/')
def index():
    phone = session.get('phone')
    user = get_or_create_user(phone) if phone else None
    is_18_approved = (user and user['age_verified'] == 2)

    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cats = conn.execute("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=?", (1 if is_18_approved else 0,)).fetchall()
        
        # ИСПРАВЛЕННЫЙ ЗАПРОС ТОВАРОВ: Теперь товары фильтруются вместе с категориями
        prods = conn.execute("""
            SELECT p.* FROM products p 
            JOIN categories c ON p.category_id = c.id 
            WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)
        """, (1 if is_18_approved else 0,)).fetchall()
        
        banners = conn.execute("SELECT * FROM banners WHERE active=1").fetchall()
        return render_template('index.html', categories=cats, products=prods, banners=banners, user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    session['phone'] = request.json.get('phone')
    return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    d = request.json
    phone = d.get('phone')
    user = get_or_create_user(phone)
    if user:
        with sqlite3.connect('shop.db') as conn:
            conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE phone=?", (d.get('full_name',''), d.get('social_link',''), phone))
    session['phone'] = phone
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    items_total = float(request.json.get('items_total', 0))
    use_bonuses = bool(request.json.get('use_bonuses', False))
    user = get_or_create_user(session.get('phone'))
    package_cost = 29 if items_total > 0 else 0
    delivery_cost = 0 if items_total >= 2000 else 150
    bonuses_spent = min(user['bonuses'], items_total * 0.5) if (user and use_bonuses and user['bonuses'] > 0) else 0
    final = max(0, items_total - bonuses_spent) + package_cost + delivery_cost
    return jsonify({"items_total": items_total, "package_cost": package_cost, "delivery_cost": delivery_cost, "bonuses_spent": bonuses_spent, "final_total": final})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    user = get_or_create_user(data.get('phone'))
    calc = data.get('calc')
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        if calc['bonuses_spent'] > 0: c.execute("UPDATE users SET bonuses = bonuses - ? WHERE id=?", (calc['bonuses_spent'], user['id']))
        earned = int(calc['items_total'] * 0.05) if calc['bonuses_spent'] == 0 else 0
        if earned > 0: c.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (earned, user['id']))
        c.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items) VALUES (?,?,?,?,?,?,?)",
                  (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], calc['bonuses_spent'], json.dumps(data.get('cart'))))
    session['phone'] = data.get('phone')
    return jsonify({"status": "ok"})

@app.route('/api/ai/chef', methods=['POST'])
def ai_chef():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        prods = conn.execute("SELECT p.id, p.name, p.price FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND c.is_hidden=0").fetchall()
    catalog = ", ".join([f"ID {p['id']}: {p['name']}" for p in prods])
    sys_prompt = f"{SHOP_INFO} Собери корзину под запрос ТОЛЬКО из каталога: {catalog}. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО 18+. Формат JSON: {{'message': 'Текст', 'cart_ids': [ID_товаров]}}"
    return jsonify(call_ai(request.json.get('query'), sys_prompt, "gemini-2.5-pro", True))

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/users', methods=['GET'])
def admin_users_get():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        return jsonify([dict(x) for x in conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()])

@app.route('/api/admin/users/update', methods=['POST'])
def admin_users_update():
    d = request.json
    with sqlite3.connect('shop.db') as conn:
        conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, addresses=?, age_verified=? WHERE id=?", (d['full_name'], d['phone'], d['social_link'], d['addresses'], d['age_verified'], d['id']))
    return jsonify({"status": "ok"})

@app.route('/api/admin/orders', methods=['GET', 'POST'])
def admin_orders():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if request.method == 'GET':
            res = conn.execute("SELECT o.*, u.phone, u.full_name FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC").fetchall()
            return jsonify([dict(x) for x in res])
        conn.execute("UPDATE orders SET status=? WHERE id=?", (request.json['status'], request.json['id']))
    return jsonify({"status": "ok"})

@app.route('/api/ai/gen_banner', methods=['POST'])
def ai_gen_banner():
    prompt = f"{SHOP_INFO} Акция: {request.json.get('topic')}. Выдай JSON: title, subtitle, bg_color (hex пастельный), img_prompt (англ без текста)."
    res = call_ai(prompt, "Креативный директор", "gemini-2.5-pro", True)
    if "error" not in res: res["img_url"] = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(res['img_prompt'])}?width=800&height=400&nologo=true"
    return jsonify(res)

@app.route('/api/banners/publish', methods=['POST'])
def publish_banner():
    d = request.json
    with sqlite3.connect('shop.db') as conn:
        conn.execute("INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat) VALUES (?,?,?,?,?)", (d['title'], d['subtitle'], d['img_url'], d['bg_color'], d['link_cat']))
    return jsonify({"status": "ok"})

@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    role = request.json.get('role')
    sys = f"{SHOP_INFO} Ты маркетолог." if role == 'marketer' else f"{SHOP_INFO} Ты юрист."
    return jsonify({"reply": call_ai(request.json.get('msg'), sys, "gemini-2.5-pro", False)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
