import sqlite3
import json
import urllib.parse
import csv
import io
import requests
from flask import Flask, render_template, request, jsonify, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- ⚙️ НАСТРОЙКИ ИИ (ПО ТВОЕМУ ТЕХПАСПОРТУ) ---
AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

# Модели из техпаспорта:
# gemini-2.5-flash: Для быстрых задач.
# gemini-2.5-pro: Основной двигатель (маркетинг).
# gemini-3.1-pro: Флагман (для сложнейших генераций, например, правил акции).
MARKETING_MODEL = "gemini-2.5-pro" # Золотая середина для генерации акций

def call_ai(prompt, system_prompt="Ты маркетолог", model=MARKETING_MODEL, temp=0.25):
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": temp,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"} # Важно: требуем JSON
    }
    try:
        r = requests.post(AI_URL, json=payload, headers=headers, timeout=40)
        return json.loads(r.json()['choices'][0]['message']['content'])
    except Exception as e:
        return {"error": str(e)}

# --- 📦 БАЗА ДАННЫХ И ИНИЦИАЛИЗАЦИЯ ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price REAL, stock INTEGER, category TEXT, image_url TEXT, active INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, text TEXT, rules TEXT, bg_color TEXT, image_url TEXT, active INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Дефолтные настройки (Логистика, Пакеты, Дизайн)
    settings = [
        ('delivery_base', '150'), ('delivery_km', '30'), ('free_delivery_limit', '2000'), 
        ('package_fee', '40'), ('free_package_limit', '500'), ('theme_color', '#0b3d2c')
    ]
    c.executemany('INSERT OR IGNORE INTO settings VALUES (?, ?)', settings)
    
    # Тестовые данные, если пусто
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ('Лимонад "Николаич"', 150, 50, 'Напитки', 'https://via.placeholder.com/150'),
            ('Мясные чипсы', 250, 20, 'Снэки', 'https://via.placeholder.com/150'),
            ('Шаурма', 350, 10, 'Горячее', 'https://via.placeholder.com/150')
        ]
        c.executemany('INSERT INTO products (name, price, stock, category, image_url) VALUES (?,?,?,?,?)', products)
        
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = sqlite3.connect('shop.db')
    res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    try: return float(res[0])
    except: return res[0] if res else default

# --- 🛒 1. ВИТРИНА (ДЛЯ КЛИЕНТОВ) ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    data = {
        "products": conn.execute("SELECT * FROM products WHERE active=1").fetchall(),
        "banners": conn.execute("SELECT * FROM banners WHERE active=1 ORDER BY id DESC LIMIT 3").fetchall(),
        "theme": get_setting('theme_color', '#0b3d2c')
    }
    conn.close()
    return render_template('index.html', **data)

# --- 🚚 2. ИНТЕЛЛЕКТУАЛЬНЫЙ РАСЧЕТ ДОСТАВКИ (ВОССТАНОВЛЕНО) ---
@app.route('/api/calculate_delivery', methods=['POST'])
def calculate_delivery():
    data = request.json
    cart_total = float(data.get('cart_total', 0))
    distance_km = float(data.get('distance_km', 0))
    delivery_type = data.get('type', 'taxi') # 'taxi' (яндекс) или 'courier' (свой)
    
    # Получаем актуальные настройки админа
    base_price = get_setting('delivery_base', 150)
    price_per_km = get_setting('delivery_km', 30)
    free_delivery = get_setting('free_delivery_limit', 2000)
    package_fee = get_setting('package_fee', 40)
    free_package = get_setting('free_package_limit', 500)
    
    # Логика 1: Платная сборка (пакеты)
    final_package = 0 if cart_total >= free_package else package_fee
    
    # Логика 2: Доставка
    if cart_total >= free_delivery:
        final_delivery = 0
    else:
        if delivery_type == 'taxi':
            # Такси считается по базе + километражу
            final_delivery = base_price + (distance_km * price_per_km)
        else:
            # Свой курьер (например, фиксированно)
            final_delivery = base_price
            
    total_to_pay = cart_total + final_delivery + final_package
        
    return jsonify({
        "cart_total": cart_total,
        "delivery_price": round(final_delivery, 2),
        "package_price": final_package,
        "total_to_pay": round(total_to_pay, 2)
    })

# --- 👑 3. АДМИНКА (РЕНДЕР И НАСТРОЙКИ) ---
@app.route('/admin')
def admin():
    settings = {
        "base": get_setting('delivery_base'), "km": get_setting('delivery_km'),
        "free_del": get_setting('free_delivery_limit'), "pack": get_setting('package_fee'),
        "free_pack": get_setting('free_package_limit'), "theme": get_setting('theme_color')
    }
    return render_template('admin.html', **settings)

@app.route('/admin/settings', methods=['POST'])
def save_settings():
    conn = sqlite3.connect('shop.db')
    for key, value in request.json.items():
        conn.execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- 🧠 4. AI МАРКЕТИНГ (МОЩНАЯ ГЕНЕРАЦИЯ АКЦИЙ) ---
@app.route('/admin/ai/full_campaign', methods=['POST'])
def ai_campaign():
    topic = request.json.get('topic')
    
    # Промпт для мощной модели (gemini-2.5-pro)
    sys_prompt = "Ты креативный директор магазина еды 'Николаич.Shop'. Создай комплексную акцию."
    prompt = f"""Тема акции: {topic}. 
    Выдай СТРОГИЙ JSON формат: 
    {{
      "title": "Короткий заголовок", 
      "text": "Продающий слоган", 
      "rules": "Правила акции (например: 'Скидка 15% при заказе от 1000р' или 'Подарок за 3 товара')",
      "color": "HEX цвет фона (ассоциирующийся с темой)", 
      "img_prompt": "English prompt for food photography generator (vivid, high quality, appetizing)"
    }}"""
    
    ai_data = call_ai(prompt, sys_prompt, MARKETING_MODEL, 0.5)
    
    if "error" in ai_data: return jsonify(ai_data), 500
        
    # Графический ИИ (Pollinations)
    img_url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(ai_data['img_prompt'])}?width=800&height=400&nologo=true"
    
    # Сохраняем всё в БД
    conn = sqlite3.connect('shop.db')
    conn.execute("UPDATE settings SET value=? WHERE key='theme_color'", (ai_data['color'],))
    conn.execute("INSERT INTO banners (title, text, rules, bg_color, image_url) VALUES (?, ?, ?, ?, ?)", 
                 (ai_data['title'], ai_data['text'], ai_data['rules'], ai_data['color'], img_url))
    conn.commit()
    conn.close()
    
    return jsonify({"title": ai_data['title'], "text": ai_data['text'], "rules": ai_data['rules'], "image_url": img_url, "color": ai_data['color']})

# --- 📦 5. СКЛАД (УПРАВЛЕНИЕ) ---
@app.route('/api/products', methods=['GET', 'POST', 'PUT'])
def api_products():
    conn = sqlite3.connect('shop.db')
    if request.method == 'GET':
        p = conn.execute("SELECT * FROM products").fetchall()
        conn.close()
        return jsonify([dict(zip(['id','name','price','stock','cat','img','active'], x)) for x in p])
    
    data = request.json
    if request.method == 'POST':
        conn.execute("INSERT INTO products (name, price, stock, category) VALUES (?,?,?,?)", 
                     (data['name'], data['price'], data['stock'], data.get('cat', 'Разное')))
    elif request.method == 'PUT':
        conn.execute("UPDATE products SET name=?, price=?, stock=?, active=? WHERE id=?", 
                     (data['name'], data['price'], data['stock'], data['active'], data['id']))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# --- 📊 6. АНАЛИТИКА ---
@app.route('/admin/export')
def export_stats():
    conn = sqlite3.connect('shop.db')
    orders = conn.execute("SELECT id, total, date FROM orders").fetchall()
    conn.close()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID Заказа', 'Сумма (руб)', 'Дата'])
    cw.writerows(orders)
    output = make_response(si.getvalue().encode('utf-8-sig'))
    output.headers["Content-Disposition"] = "attachment; filename=nikolaich_stats.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
