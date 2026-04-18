import sqlite3, json, urllib.parse, requests, uuid, datetime
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = 'nikolaich_premium_key_2026'

# --- ИНТЕГРАЦИЯ AI (5 ФУНКЦИЙ) ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True):
    payload = {"model": model, "temperature": 0.25, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]}
    if is_json: payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=50)
        return json.loads(r.json()['choices'][0]['message']['content']) if is_json else r.json()['choices'][0]['message']['content']
    except Exception as e: return {"error": str(e)} if is_json else f"Ошибка ИИ: {str(e)}"

# --- БАЗА ДАННЫХ 6.0 (ПРОМО, БОНУСЫ, РЕФЕРАЛЫ) ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    # Базовые таблицы
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT UNIQUE, sort_order INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, img TEXT, active INTEGER DEFAULT 1, is_18 INTEGER DEFAULT 0)')
    # Таблица юзеров (Добавлены бонусы и рефералы)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, vk_id TEXT, vip INTEGER DEFAULT 0, bonuses INTEGER DEFAULT 0, ref_code TEXT UNIQUE, referred_by INTEGER)')
    # Таблица заказов (Учет скидок)
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, subtotal REAL, discount REAL, delivery_cost REAL, final_total REAL, used_bonuses INTEGER, earned_bonuses INTEGER, items TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    # Промокоды (Вводятся вручную)
    c.execute('CREATE TABLE IF NOT EXISTS promocodes (id INTEGER PRIMARY KEY, code TEXT UNIQUE, type TEXT, val REAL, min_cart REAL, active INTEGER DEFAULT 1)')
    # Авто-акции (Применяются сами)
    c.execute('CREATE TABLE IF NOT EXISTS promotions (id INTEGER PRIMARY KEY, name TEXT, condition_type TEXT, condition_val REAL, reward_type TEXT, reward_val REAL, active INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    
    # Инициализация демо-данных
    c.execute("SELECT COUNT(*) FROM settings")
    if c.fetchone()[0] == 0:
        c.executemany('INSERT INTO settings VALUES (?,?)', [('base_delivery', '150'), ('km_price', '30'), ('cashback_percent', '5')])
        c.executemany('INSERT INTO categories (name) VALUES (?)', [('🔥 Популярное',), ('🥛 Молочное',), ('🥩 Мясо',)])
        c.executemany('INSERT INTO promocodes (code, type, val, min_cart) VALUES (?,?,?,?)', [('START', 'percent', 10, 1000)]) # Скидка 10%
        c.executemany('INSERT INTO promotions (name, condition_type, condition_val, reward_type, reward_val) VALUES (?,?,?,?,?)', [('Бесплатная доставка от 2000', 'cart_total', 2000, 'free_delivery', 0)])
        c.executemany('INSERT INTO products (name, desc, price, stock, category_id, img, is_18) VALUES (?,?,?,?,?,?,?)', [
            ('Молоко Фермерское', '1 литр', 120, 50, 2, '🥛', 0),
            ('Стейк Рибай', 'Мраморная говядина', 850, 15, 3, '🥩', 0),
            ('Настойка Николаича', '40 градусов', 900, 10, 1, '🍷', 1)
        ])
    conn.commit(); conn.close()

init_db()

# --- ВСПМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_user(phone):
    conn = sqlite3.connect('shop.db'); conn.row_factory = sqlite3.Row
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close(); return dict(user) if user else None

def get_set(k, default=0):
    conn = sqlite3.connect('shop.db')
    r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    conn.close(); return float(r[0]) if r else default

# --- ВИТРИНА ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db'); conn.row_factory = sqlite3.Row
    cats = conn.execute("SELECT * FROM categories ORDER BY sort_order").fetchall()
    prods = conn.execute("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1").fetchall()
    user = get_user(session.get('phone'))
    conn.close()
    return render_template('index.html', categories=cats, products=prods, user=user)

# --- ДВИЖОК АКЦИЙ И РАСЧЕТ КОРЗИНЫ (PROMO ENGINE) ---
@app.route('/api/cart/calculate', methods=['POST'])
def calc_cart():
    data = request.json
    cart_total = float(data.get('cart_total', 0))
    promo_code = data.get('promo_code', '').upper().strip()
    use_bonuses = bool(data.get('use_bonuses', False))
    phone = session.get('phone') or data.get('phone')
    
    discount = 0
    delivery = get_set('base_delivery', 150)
    
    conn = sqlite3.connect('shop.db'); conn.row_factory = sqlite3.Row
    
    # 1. Применяем Авто-Акции
    promos = conn.execute("SELECT * FROM promotions WHERE active=1").fetchall()
    for p in promos:
        if p['condition_type'] == 'cart_total' and cart_total >= p['condition_val']:
            if p['reward_type'] == 'free_delivery': delivery = 0
            elif p['reward_type'] == 'discount_percent': discount += cart_total * (p['reward_val'] / 100)
            elif p['reward_type'] == 'discount_fixed': discount += p['reward_val']
            
    # 2. Проверяем Промокод (или Реферальный код)
    msg = ""
    if promo_code:
        pc = conn.execute("SELECT * FROM promocodes WHERE code=? AND active=1", (promo_code,)).fetchone()
        ref_user = conn.execute("SELECT id FROM users WHERE ref_code=?", (promo_code,)).fetchone()
        
        if pc and cart_total >= pc['min_cart']:
            if pc['type'] == 'percent': discount += cart_total * (pc['val'] / 100)
            elif pc['type'] == 'fixed': discount += pc['val']
            elif pc['type'] == 'free_delivery': delivery = 0
            msg = "Промокод применен!"
        elif ref_user:
            discount += 300 # Скидка 300р за реф код друга
            msg = "Код друга применен!"
        else: msg = "Неверный код или сумма мала"

    # 3. Бонусы
    bonuses_to_spend = 0
    earned_bonuses = int(cart_total * (get_set('cashback_percent', 5) / 100))
    user = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone() if phone else None
    
    if user and use_bonuses and user['bonuses'] > 0:
        max_spend = cart_total * 0.5 # Оплатить можно до 50%
        bonuses_to_spend = min(user['bonuses'], max_spend)
        discount += bonuses_to_spend
        earned_bonuses = 0 # За заказы с бонусами кэшбек не даем (логика Лавки)

    conn.close()
    
    final_total = max(0, cart_total - discount) + delivery
    
    return jsonify({
        "subtotal": cart_total, "discount": round(discount, 2), "delivery": delivery, 
        "final_total": round(final_total, 2), "bonuses_spent": bonuses_to_spend, 
        "bonuses_earned": earned_bonuses, "msg": msg
    })

# --- ОФОРМЛЕНИЕ ЗАКАЗА (С РЕФЕРАЛАМИ) ---
@app.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.json
    phone, name = data.get('phone'), data.get('name')
    calc_data = data.get('calc_data') # Данные из calc_cart
    promo_code = data.get('promo_code', '').upper().strip()
    
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    
    # Ищем или создаем юзера
    c.execute("SELECT id, bonuses FROM users WHERE phone=?", (phone,))
    u = c.fetchone()
    
    if not u:
        ref_code = f"REF-{uuid.uuid4().hex[:6].upper()}"
        # Проверяем, был ли введен код друга
        ref_by = None
        if promo_code:
            friend = c.execute("SELECT id FROM users WHERE ref_code=?", (promo_code,)).fetchone()
            if friend: ref_by = friend[0]
            
        c.execute("INSERT INTO users (phone, name, ref_code, referred_by) VALUES (?, ?, ?, ?)", (phone, name, ref_code, ref_by))
        user_id = c.lastrowid
        user_bonuses = 0
    else:
        user_id, user_bonuses = u[0], u[1]

    # Списываем бонусы, если юзер их применил
    if calc_data['bonuses_spent'] > 0:
        c.execute("UPDATE users SET bonuses = bonuses - ? WHERE id=?", (calc_data['bonuses_spent'], user_id))
    
    # Начисляем кэшбек
    if calc_data['bonuses_earned'] > 0:
        c.execute("UPDATE users SET bonuses = bonuses + ? WHERE id=?", (calc_data['bonuses_earned'], user_id))

    # Логика рефералки: Начисляем 500 бонусов другу, если это первый заказ юзера
    if not u and ref_by:
        c.execute("UPDATE users SET bonuses = bonuses + 500 WHERE id=?", (ref_by,))

    # Сохраняем заказ
    c.execute("INSERT INTO orders (user_id, subtotal, discount, delivery_cost, final_total, used_bonuses, earned_bonuses, items) VALUES (?,?,?,?,?,?,?,?)",
              (user_id, calc_data['subtotal'], calc_data['discount'], calc_data['delivery'], calc_data['final_total'], calc_data['bonuses_spent'], calc_data['bonuses_earned'], json.dumps(data.get('cart', []))))
    
    conn.commit(); conn.close()
    session['phone'] = phone
    return jsonify({"status": "ok"})


# --- CRUD АДМИНКИ (ПОЛНОЕ УПРАВЛЕНИЕ) ---
@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/products', methods=['GET', 'POST', 'PUT', 'DELETE'])
def admin_products():
    conn = sqlite3.connect('shop.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
    if request.method == 'GET':
        p = c.execute("SELECT p.*, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id=c.id").fetchall(); conn.close(); return jsonify([dict(x) for x in p])
    
    d = request.json
    if request.method == 'POST': c.execute("INSERT INTO products (name, desc, price, old_price, stock, category_id, img, active, is_18) VALUES (?,?,?,?,?,?,?,?,?)", (d['name'], d['desc'], d['price'], d['old_price'], d['stock'], d['cat_id'], d['img'], d['active'], d['is_18']))
    elif request.method == 'PUT': c.execute("UPDATE products SET name=?, desc=?, price=?, old_price=?, stock=?, category_id=?, img=?, active=?, is_18=? WHERE id=?", (d['name'], d['desc'], d['price'], d['old_price'], d['stock'], d['cat_id'], d['img'], d['active'], d['is_18'], d['id']))
    elif request.method == 'DELETE': c.execute("DELETE FROM products WHERE id=?", (d['id'],))
    
    conn.commit(); conn.close(); return jsonify({"status": "ok"})

# --- AI ФУНКЦИИ (5 РОЛЕЙ) ---
@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    role, msg = request.json.get('role'), request.json.get('msg')
    sys_prompts = {"marketer": "Ты маркетолог. Выдай стратегию или акцию.", "lawyer": "Ты старший юрист РФ.", "accountant": "Ты главбух."}
    m = "gemini-3.1-pro" if role in ['lawyer', 'accountant'] else "gemini-2.5-pro"
    return jsonify({"reply": call_ai(msg, sys_prompts.get(role, "Ты помощник"), m, False)})

@app.route('/api/ai/banner', methods=['POST'])
def ai_banner():
    topic = request.json.get('topic')
    ai = call_ai(f"Сделай акцию про: {topic}. JSON: title, text, color(HEX), img_prompt(ENG)", "Ты креативный директор", "gemini-2.5-pro", True)
    if "error" in ai: return jsonify(ai), 500
    return jsonify({"title": ai['title'], "text": ai['text'], "bg": ai['color'], "img": f"https://image.pollinations.ai/prompt/{urllib.parse.quote(ai['img_prompt'])}?width=800&height=400&nologo=true"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
