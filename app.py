# -*- coding: utf-8 -*-
import sqlite3, json, urllib.parse, requests, uuid, datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_shadow_v7'

# --- КОНСТАНТЫ И ИИ ---
SHOP_INFO = "Магазин фермерских продуктов 'У Николаича'. г. Ярославль, пер. 1-й Голубятный, 12."
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

# --- БАЗА ДАННЫХ 7.1 (CRM + 18+) ---
def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, img TEXT, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        # Таблица пользователей (age_verified: 0-нет, 1-запрос, 2-одобрен Николаичем)
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        # Заказы (добавлены пакеты и доставка)
        c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        c.execute("SELECT COUNT(*) FROM categories")
        if c.fetchone()[0] == 0:
            c.executemany('INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)', [
                ('Мясо','🥩', 1, 0), ('Молоко','🥛', 2, 0), ('Овощи','🥬', 3, 0), ('Для своих','🍷', 99, 1)
            ])
            c.executemany('INSERT INTO products (name, desc, price, stock, category_id, img) VALUES (?,?,?,?,?,?)', [
                ('Стейк Рибай', 'Мраморная говядина', 850, 15, 1, '🥩'),
                ('Молоко Фермерское', '1 литр', 120, 50, 2, '🥛'),
                ('Картофель', 'Свежий урожай, 1 кг', 60, 100, 3, '🥔'),
                ('Настойка Николаича', 'Крепкая, кедровая', 900, 10, 4, '🍷')
            ])
            c.execute('INSERT INTO banners (title, subtitle, bg_color, link_cat) VALUES (?,?,?,?)', ('Свежее мясо!', 'Прямо с фермы', '#ffebee', 1))
    conn.commit()

init_db()

# --- ХЕЛПЕРЫ ---
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

# --- ВИТРИНА (КЛИЕНТ) ---
@app.route('/')
def index():
    phone = session.get('phone')
    user = get_or_create_user(phone) if phone else None
    is_18_approved = (user and user['age_verified'] == 2)

    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        # Грузим только открытые категории. Скрытые — только если одобрено 18+
        cat_query = "SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=?"
        cats = conn.execute(cat_query, (1 if is_18_approved else 0,)).fetchall()
        
        prods = conn.execute("SELECT * FROM products WHERE active=1").fetchall()
        banners = conn.execute("SELECT * FROM banners WHERE active=1").fetchall()
        
        return render_template('index.html', categories=cats, products=prods, banners=banners, user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth_shadow():
    phone = request.json.get('phone')
    session['phone'] = phone # Простая авторизация по номеру
    return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def request_18():
    phone = request.json.get('phone')
    if not phone: return jsonify({"status": "error", "msg": "Нужен телефон"})
    user = get_or_create_user(phone)
    if user['age_verified'] == 0:
        with sqlite3.connect('shop.db') as conn:
            conn.execute("UPDATE users SET age_verified=1 WHERE phone=?", (phone,))
    session['phone'] = phone
    return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc_cart():
    items_total = float(request.json.get('items_total', 0))
    use_bonuses = bool(request.json.get('use_bonuses', False))
    user = get_or_create_user(session.get('phone'))
    
    package_cost = 29 if items_total > 0 else 0 # Сборка и пакеты
    delivery_cost = 0 if items_total >= 2000 else 150 # Авто-доставка
    
    bonuses_spent = 0
    if user and use_bonuses and user['bonuses'] > 0:
        bonuses_spent = min(user['bonuses'], items_total * 0.5) # До 50% скидки
        
    final = max(0, items_total - bonuses_spent) + package_cost + delivery_cost
    
    return jsonify({
        "items_total": items_total, "package_cost": package_cost, 
        "delivery_cost": delivery_cost, "bonuses_spent": bonuses_spent, 
        "final_total": final
    })

@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    user = get_or_create_user(data.get('phone'))
    calc = data.get('calc')
    cart = data.get('cart')
    
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        if calc['bonuses_spent'] > 0:
            c.execute("UPDATE users SET bonuses = bonuses - ? WHERE id=?", (calc['bonuses_spent'], user['id']))
        # Кэшбек 5% от суммы товаров (без учета пакетов и доставки)
        earned = int(calc['items_total'] * 0.05) if calc['bonuses_spent'] == 0 else 0
        if earned > 0:
            c.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (earned, user['id']))
            
        c.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items) VALUES (?,?,?,?,?,?,?)",
                  (user['id'], calc['items_total'], calc['package_cost'], calc['delivery_cost'], calc['final_total'], calc['bonuses_spent'], json.dumps(cart)))
    
    session['phone'] = data.get('phone')
    return jsonify({"status": "ok"})

# --- ИИ ШЕФ-ПОВАР (ДЛЯ КЛИЕНТА) ---
@app.route('/api/ai/chef', methods=['POST'])
def ai_chef():
    query = request.json.get('query')
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        # Отдаем ИИ только открытые товары (is_hidden=0)
        prods = conn.execute("SELECT p.id, p.name, p.price FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND c.is_hidden=0").fetchall()
    
    catalog = ", ".join([f"ID {p['id']}: {p['name']} ({p['price']}₽)" for p in prods])
    sys_prompt = f"{SHOP_INFO} Ты ИИ-Шефповар. Твоя задача - собрать корзину под рецепт клиента ТОЛЬКО из нашего каталога. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО предлагать алкоголь, табак или любые товары 18+. Если в каталоге чего-то нет, скажи об этом. \nКаталог: {catalog}. \nФормат JSON: {{'message': 'Текст для клиента', 'cart_ids': [ID_товаров_из_каталога]}}"
    
    return jsonify(call_ai(query, sys_prompt, "gemini-2.5-pro", True))

# --- АДМИНКА (CRM И ИИ-ХАБ) ---
@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/users', methods=['GET', 'POST'])
def admin_users():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if request.method == 'GET':
            return jsonify([dict(x) for x in conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()])
        d = request.json
        if d.get('action') == 'approve_18':
            conn.execute("UPDATE users SET age_verified=2 WHERE id=?", (d['id'],))
        elif d.get('action') == 'add_bonus':
            conn.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (d['amount'], d['id']))
    return jsonify({"status": "ok"})

@app.route('/api/admin/orders', methods=['GET', 'POST'])
def admin_orders():
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row
        if request.method == 'GET':
            res = conn.execute("SELECT o.*, u.phone, u.name as user_name FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC").fetchall()
            return jsonify([dict(x) for x in res])
        conn.execute("UPDATE orders SET status=? WHERE id=?", (request.json['status'], request.json['id']))
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
