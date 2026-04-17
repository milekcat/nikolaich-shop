import os
import sqlite3
import requests
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- НАСТРОЙКИ ИИ (ARTEMOX) ---
AI_API_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A" # Твой ключ
AI_MODEL = "gemini-2.0-flash-lite"

# --- 1. БАЗА ДАННЫХ И ИНИЦИАЛИЗАЦИЯ ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT, description TEXT, price REAL, image_url TEXT, FOREIGN KEY(category_id) REFERENCES categories(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY AUTOINCREMENT, image_url TEXT, promo_text TEXT, linked_category_id INTEGER)''')
    conn.commit()
    conn.close()

def get_setting(key, default_value=""):
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else default_value

def populate_dummy_data():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM categories")
    if c.fetchone()[0] == 0:
        categories = ['Напитки', 'Снэки', 'Горячее', 'Десерты']
        for cat in categories:
            c.execute("INSERT INTO categories (name) VALUES (?)", (cat,))
        
        products = [
            (1, 'Лимонад Николаич', 'Освежающий крафтовый лимонад', 150.0, '/static/limonad.jpg'),
            (2, 'Чипсы Мясные', 'Сушеное мясо со специями', 250.0, '/static/chips.jpg')
        ]
        c.executemany("INSERT INTO products (category_id, name, description, price, image_url) VALUES (?, ?, ?, ?, ?)", products)
        
        settings = [
            ('delivery_base_price', '150'),
            ('delivery_per_km', '20'),
            ('package_price', '30'),
            ('theme_color_main', '#4CAF50') # Базовый зеленый цвет
        ]
        c.executemany("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", settings)
    conn.commit()
    conn.close()

init_db()
populate_dummy_data()

# --- 2. ВИТРИНА (ГЛАВНАЯ) ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    categories = c.execute("SELECT * FROM categories").fetchall()
    products = c.execute("SELECT * FROM products").fetchall()
    banners = c.execute("SELECT * FROM banners").fetchall()
    theme_color = get_setting('theme_color_main', '#4CAF50')
    
    conn.close()
    return render_template('index.html', categories=categories, products=products, banners=banners, theme_color=theme_color)

# --- 3. ИНТЕЛЛЕКТУАЛЬНАЯ ДОСТАВКА ---
@app.route('/api/calculate_delivery', methods=['POST'])
def calculate_delivery():
    data = request.json
    cart_total = float(data.get('cart_total', 0))
    distance_km = float(data.get('distance_km', 0))
    
    base_price = float(get_setting('delivery_base_price', 150))
    price_per_km = float(get_setting('delivery_per_km', 20))
    
    final_delivery_price = base_price + (distance_km * price_per_km) if cart_total < 2000 else 0
    package_price = float(get_setting('package_price', 30)) if cart_total < 500 else 0
        
    return jsonify({
        "delivery_price": round(final_delivery_price, 2),
        "package_price": package_price,
        "total": round(cart_total + final_delivery_price + package_price, 2)
    })

# --- 4. МАСШТАБНЫЙ ИИ РАЗДЕЛ (АДМИНКА) ---

# Функция для связи с Artemox API (через обычные POST запросы, чтобы не ставить новые библиотеки)
def call_artemox_ai(prompt):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AI_API_KEY}"
    }
    payload = {
        "model": AI_MODEL,
        "messages": [{"role": "user", "content": prompt}]
    }
    try:
        response = requests.post(AI_API_URL, headers=headers, json=payload)
        response.raise_for_status() # Проверка на ошибки (401, 500 и тд)
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Ошибка ИИ: {str(e)}"

@app.route('/admin/ai/generate_promo', methods=['POST'])
def ai_generate_promo():
    """ИИ генерирует продающий текст для баннера"""
    topic = request.json.get('topic', 'скидки на выходных')
    prompt = f"Напиши короткий, яркий продающий слоган (максимум 5-7 слов) для магазина еды на тему: {topic}."
    
    ai_text = call_artemox_ai(prompt)
    return jsonify({"success": True, "promo_text": ai_text})

@app.route('/admin/ai/generate_description', methods=['POST'])
def ai_generate_description():
    """ИИ генерирует вкусное описание товара"""
    product_name = request.json.get('product_name')
    prompt = f"Напиши аппетитное и краткое описание для еды (до 2 предложений). Название блюда: {product_name}."
    
    ai_text = call_artemox_ai(prompt)
    return jsonify({"success": True, "description": ai_text})

@app.route('/admin/ai/suggest_theme', methods=['POST'])
def ai_suggest_theme():
    """ИИ подбирает цвета для праздничного дизайна"""
    holiday = request.json.get('holiday', 'Новый год')
    prompt = f"Выдай только один правильный CSS HEX-код цвета (например #FF0000), который лучше всего ассоциируется с праздником: {holiday}. Больше никаких слов, только код."
    
    ai_color = call_artemox_ai(prompt).strip()
    
    # Сразу сохраняем этот цвет в базу, чтобы дизайн сайта мгновенно поменялся
    if ai_color.startswith('#') and len(ai_color) in [4, 7]:
        conn = sqlite3.connect('shop.db')
        c = conn.cursor()
        c.execute("UPDATE settings SET value=? WHERE key='theme_color_main'", (ai_color,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "new_color": ai_color, "message": "Дизайн сайта обновлен!"})
    else:
        return jsonify({"success": False, "error": "ИИ выдал некорректный цвет"})

if __name__ == '__main__':
    app.run(debug=True, port=8085)
