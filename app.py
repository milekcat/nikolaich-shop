import sqlite3
import csv
import io
import requests
from flask import Flask, render_template, request, jsonify, make_response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# --- НАСТРОЙКИ ИИ ---
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A" # ВНИМАНИЕ: Не свети этот ключ в публичном доступе!
AI_URL = "https://api.artemox.com/v1/chat/completions"

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ---
def init_db():
    conn = sqlite3.connect('shop.db')
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, category_id INTEGER, name TEXT, price REAL, image_url TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, promo_text TEXT, bg_color TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, total REAL, date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Базовые настройки
    c.execute('INSERT OR IGNORE INTO settings VALUES ("theme_color", "#ff6600")')
    c.execute('INSERT OR IGNORE INTO settings VALUES ("delivery_base", "150")')
    c.execute('INSERT OR IGNORE INTO settings VALUES ("delivery_km", "20")')
    
    # Фейковые данные для Николаича, если база пустая
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO products (name, price, image_url) VALUES ("Шаурма PRO", 350, "https://via.placeholder.com/150")')
        c.execute('INSERT INTO orders (total) VALUES (1500), (450), (2200), (350)') # Тестовые продажи для статы
    
    conn.commit()
    conn.close()

init_db()

def get_setting(key, default=""):
    conn = sqlite3.connect('shop.db')
    res = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return res[0] if res else default

# --- ВИТРИНА (КЛИЕНТЫ) ---
@app.route('/')
def index():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    products = conn.execute("SELECT * FROM products").fetchall()
    banners = conn.execute("SELECT * FROM banners ORDER BY id DESC LIMIT 3").fetchall()
    theme_color = get_setting('theme_color', '#ff6600')
    conn.close()
    return render_template('index.html', products=products, banners=banners, theme_color=theme_color)

# --- АДМИНКА (НИКОЛАИЧ И ТЫ) ---
@app.route('/admin')
def admin():
    return render_template('admin.html', 
                           base=get_setting('delivery_base'), 
                           km=get_setting('delivery_km'),
                           theme=get_setting('theme_color'))

# --- ИИ РАЗДЕЛ ---
def ask_ai(prompt):
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    data = {"model": "gemini-2.0-flash-lite", "messages": [{"role": "user", "content": prompt}]}
    try:
        r = requests.post(AI_URL, json=data, headers=headers, timeout=15)
        return r.json()['choices'][0]['message']['content'].strip()
    except: return "Ошибка связи с ИИ"

@app.route('/admin/ai/promo', methods=['POST'])
def ai_promo():
    topic = request.json.get('topic', 'еда')
    res = ask_ai(f"Напиши один короткий, взрывной слоган для баннера про: {topic}. Не больше 5 слов.")
    
    # Сохраняем сгенерированный баннер в базу
    conn = sqlite3.connect('shop.db')
    conn.execute("INSERT INTO banners (promo_text, bg_color) VALUES (?, ?)", (res, "#333333"))
    conn.commit()
    conn.close()
    return jsonify({"promo": res})

# --- УПРАВЛЕНИЕ НАСТРОЙКАМИ (ДОСТАВКА И ЦВЕТ) ---
@app.route('/admin/settings', methods=['POST'])
def save_settings():
    data = request.json
    conn = sqlite3.connect('shop.db')
    for key, value in data.items():
        conn.execute("UPDATE settings SET value=? WHERE key=?", (str(value), key))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# --- СКАЧИВАНИЕ СТАТИСТИКИ (CSV) ---
@app.route('/admin/export_stats')
def export_stats():
    conn = sqlite3.connect('shop.db')
    orders = conn.execute("SELECT id, total, date FROM orders").fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID Заказа', 'Сумма (руб)', 'Дата'])
    cw.writerows(orders)

    output = make_response(si.getvalue().encode('utf-8-sig')) # utf-8-sig для русского языка в Excel
    output.headers["Content-Disposition"] = "attachment; filename=sales_stats.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8085)
