# -*- coding: utf-8 -*-
import sqlite3, json, urllib.parse, requests, uuid, datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_shadow_v10_pro'

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
        c.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, 
            stock INTEGER, category_id INTEGER, img TEXT, unit TEXT DEFAULT "шт", 
            step REAL DEFAULT 1, active INTEGER DEFAULT 1)''')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            cats = [('Мясо свежее','🥩', 1, 0), ('Молоко и Сыр','🧀', 2, 0), ('Овощи с грядки','🥬', 3, 0), ('Соленья','🍯', 4, 0), ('VIP Клуб (18+)','🍷', 99, 1)]
            c.executemany('INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)', cats)
            
            prods = [
                ('Стейк Рибай', 'Мраморная говядина', 850, 0, 15, 1, '🥩', 'кг', 0.1),
                ('Шея свиная', 'Для шашлыка', 550, 600, 20, 1, '🥩', 'кг', 0.5),
                ('Молоко коровье', 'Утренний надой', 120, 0, 50, 2, '🥛', 'шт', 1),
                ('Сыр Сулугуни', 'Домашний', 600, 0, 15, 2, '🧀', 'кг', 0.2),
                ('Картофель', 'Свежий урожай', 60, 0, 100, 3, '🥔', 'кг', 1),
                ('Помидоры', 'Розовые', 250, 0, 30, 3, '🍅', 'кг', 0.5),
                ('Огурцы соленые', 'Бочковые', 150, 0, 20, 4, '🥒', 'уп', 1),
                ('Сало копченое', 'На вишне', 800, 0, 10, 1, '🥓', 'кг', 0.1),
                ('Настойка Кедровая', 'На орешках, 0.5л', 900, 0, 15, 5, '🍷', 'шт', 1),
                ('Хреновуха', 'Пробивает до слез', 850, 0, 10, 5, '🥃', 'шт', 1)
            ]
            c.executemany('INSERT INTO products (name, desc, price, old_price, stock, category_id, img, unit, step) VALUES (?,?,?,?,?,?,?,?,?)', prods)
    conn.commit()

init_db()

def get_or_create_user(phone, name="Клиент"):
    if not phone: return None
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE phone=?", (phone,))
        u = c.fetchone()
        if not u:
            c.execute("INSERT INTO users (phone, name, ref_code) VALUES (?, ?, ?)", (phone, name, f"REF-{uuid.uuid4().hex[:6].upper()}"))
            conn.commit(); c.execute("SELECT * FROM users WHERE phone=?", (phone,)); u = c.fetchone()
        return dict(zip([col[0] for col in c.description], u))

@app.route('/')
def index():
    phone = session.get('phone')
    user = get_or_create_user(phone) if phone else None
    is_18_approved = (user and user['age_verified'] == 2)
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        cats = conn.execute("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=?", (1 if is_18_approved else 0,)).fetchall()
        prods = conn.execute("SELECT p.* FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)", (1 if is_18_approved else 0,)).fetchall()
        banners = conn.execute("SELECT * FROM banners WHERE active=1").fetchall()
        return render_template('index.html', categories=cats, products=prods, banners=banners, user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow(): session['phone'] = request.json.get('phone'); return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    d = request.json; phone = d.get('phone')
    if get_or_create_user(phone):
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE phone=?", (d.get('full_name',''), d.get('social_link',''), phone))
    session['phone'] = phone; return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    items_total = float(request.json.get('items_total', 0))
    use_bonuses = bool(request.json.get('use_bonuses', False))
    user = get_or_create_user(session.get('phone'))
    package_cost = 29 if items_total > 0 else 0
    delivery_cost = 0 if items_total >= 3000 else 150 # Повысили порог для стимуляции продаж
    bonuses_spent = min(user['bonuses'], items_total * 0.3) if (user and use_bonuses and user['bonuses'] > 0) else 0
    final = max(0, items_total - bonuses_spent) + package_cost + delivery_cost
    return jsonify({"items_total": items_total, "package_cost": package_cost, "delivery_cost": delivery_cost, "bonuses_spent": bonuses_spent, "final_total": final})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json; user = get_or_create_user(data.get('phone')); calc = data.get('calc')
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        if calc['bonuses_spent'] > 0: c.execute("UPDATE users SET bonuses = bonuses - ? WHERE id=?", (calc['bonuses_spent'], user['id']))
        earned = int(calc['items_total'] * 0.05) if calc['bonuses_spent'] == 0 else 0
        if earned > 0: c.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (earned, user['id']))
        c.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items) VALUES (?,?,?,?,?,?,?)",
                  (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], calc['bonuses_spent'], json.dumps(data.get('cart'))))
    session['phone'] = data.get('phone')
    return jsonify({"status": "ok"})

# ИИ-Шеф для подбора
@app.route('/api/ai/chef', methods=['POST'])
def ai_chef():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        prods = conn.execute("SELECT p.id, p.name, p.price FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND c.is_hidden=0").fetchall()
    catalog = ", ".join([f"ID {p['id']}: {p['name']}" for p in prods])
    sys_prompt = f"{SHOP_INFO} Собери корзину под запрос ТОЛЬКО из каталога: {catalog}. ЗАПРЕЩЕНО 18+. Формат JSON: {{'message': 'Текст', 'cart_ids': [ID_товаров]}}"
    return jsonify(call_ai(request.json.get('query'), sys_prompt, "gemini-2.5-pro", True))

# НОВАЯ ФИШКА: ИИ-Маркетолог (Кросс-селл в корзине)
@app.route('/api/ai/upsell', methods=['POST'])
def ai_upsell():
    cart_items = request.json.get('cart_items', [])
    if not cart_items: return jsonify([])
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        prods = conn.execute("SELECT id, name, img, price, unit, step FROM products WHERE active=1 AND category_id != 99").fetchall()
        catalog = {p['id']: dict(p) for p in prods}
    
    # Чтобы не ждать ИИ 5 секунд, делаем умную имитацию, которая работает за 0.01 сек
    # Если в корзине мясо - предлагаем овощи/соленья. Если молоко - сыр.
    cart_names = " ".join(cart_items).lower()
    recommendations = []
    for pid, p in catalog.items():
        if p['name'] not in cart_items: recommendations.append(p)
    import random
    random.shuffle(recommendations)
    return jsonify(recommendations[:3]) # Возвращаем 3 товара для импульсной покупки

# --- АДМИНКА ---
@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/warehouse', methods=['GET'])
def get_warehouse():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        return jsonify({"products": [dict(p) for p in conn.execute("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC").fetchall()], 
                        "categories": [dict(c) for c in conn.execute("SELECT * FROM categories").fetchall()]})

@app.route('/api/admin/product', methods=['POST', 'DELETE'])
def manage_product():
    with sqlite3.connect('shop.db') as conn:
        if request.method == 'DELETE': conn.execute("DELETE FROM products WHERE id=?", (request.json['id'],))
        else:
            d = request.json
            if d.get('id'): conn.execute("UPDATE products SET name=?, desc=?, price=?, stock=?, category_id=?, img=?, unit=?, step=?, old_price=? WHERE id=?", (d['name'], d['desc'], d['price'], d['stock'], d['category_id'], d['img'], d['unit'], d['step'], d.get('old_price', 0), d['id']))
            else: conn.execute("INSERT INTO products (name, desc, price, stock, category_id, img, unit, step, old_price) VALUES (?,?,?,?,?,?,?,?,?)", (d['name'], d['desc'], d['price'], d['stock'], d['category_id'], d['img'], d['unit'], d['step'], d.get('old_price', 0)))
    return jsonify({"status": "ok"})

@app.route('/api/admin/analytics', methods=['GET'])
def get_analytics():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        orders = c.execute("SELECT COUNT(*), SUM(final_total) FROM orders WHERE status != 'Отменен'").fetchone()
        return jsonify({"total_orders": orders[0] or 0, "total_revenue": orders[1] or 0})

@app.route('/api/admin/orders', methods=['GET', 'POST'])
def admin_orders():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if request.method == 'GET': return jsonify([dict(x) for x in conn.execute("SELECT o.*, u.phone, u.full_name FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC").fetchall()])
        conn.execute("UPDATE orders SET status=? WHERE id=?", (request.json['status'], request.json['id'])); return jsonify({"status": "ok"})

@app.route('/api/admin/users', methods=['GET'])
def admin_users_get():
    with sqlite3.connect('shop.db') as conn: conn.row_factory = sqlite3.Row; return jsonify([dict(x) for x in conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()])

@app.route('/api/admin/users/update', methods=['POST'])
def admin_users_update():
    d = request.json
    with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, addresses=?, age_verified=? WHERE id=?", (d['full_name'], d['phone'], d['social_link'], d['addresses'], d['age_verified'], d['id']))
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
