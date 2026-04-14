import sqlite3
import os
import json
import qrcode
import base64
import requests
from io import BytesIO
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

DB_FILE = 'shop.db'
os.makedirs('static/uploads', exist_ok=True)

# Интеграция API Artemox (Gemini)
AI_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"
AI_URL = "https://api.artemox.com/v1/chat/completions"

def call_ai(prompt, system_instruction, model_name="gemini-2.5-pro"):
    headers = {
        "Authorization": f"Bearer {AI_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post(AI_URL, headers=headers, json=payload, timeout=15)
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        return f"Ошибка AI: {str(e)}"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, address TEXT, password TEXT, is_approved INTEGER DEFAULT 0, vip_code TEXT, role TEXT DEFAULT "client")')
    c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, description TEXT, price REAL, img TEXT, unit TEXT DEFAULT "шт", stock REAL DEFAULT 999, is_vip INTEGER DEFAULT 0, is_available INTEGER DEFAULT 1)')
    c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, phone TEXT, address TEXT, total REAL, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    
    # Создаем админа, если нет
    try: c.execute("INSERT INTO users (phone, name, password, is_approved, role) VALUES ('admin', 'Сергей Павлович', 'admin777', 1, 'admin')")
    except: pass
    conn.commit(); conn.close()

init_db()

@app.route('/')
def index(): return send_from_directory('static', 'index.html')

@app.route('/api/store-data')
def store_data():
    conn = get_db()
    res = {"products": [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_available=1 AND is_vip=0').fetchall()]}
    conn.close(); return jsonify(res)

# VIP СИСТЕМА
@app.route('/api/vip/register', methods=['POST'])
def vip_register():
    d = request.json
    conn = get_db(); c = conn.cursor()
    try:
        c.execute('INSERT INTO users (phone, name, address, password) VALUES (?,?,?,?)', (d['phone'], d['name'], d['address'], d['password']))
        conn.commit(); conn.close()
        return jsonify({"success": True, "msg": "Заявка принята. Дождитесь одобрения администратором."})
    except: return jsonify({"success": False, "msg": "Ошибка регистрации."})

@app.route('/api/vip/login', methods=['POST'])
def vip_login():
    d = request.json
    conn = get_db()
    u = conn.execute('SELECT * FROM users WHERE phone=? AND password=? AND is_approved=1', (d['phone'], d['password'])).fetchone()
    if not u or u['vip_code'] != d['vip_code']: return jsonify({"success": False, "msg": "Доступ запрещен или код неверен."})
    prods = [dict(r) for r in conn.execute('SELECT * FROM products WHERE is_vip=1').fetchall()]
    conn.close(); return jsonify({"success": True, "vip_products": prods})

# AI МОДУЛИ
@app.route('/api/ai/agent', methods=['POST'])
def ai_agent():
    prompt = request.json.get('prompt')
    instr = "Ты — AI-управляющий магазином 'У Николаича'. Твоя цель — помогать владельцу (Сергею) масштабировать бизнес, анализировать тренды и писать скрипты продаж."
    reply = call_ai(prompt, instr, "gemini-2.5-pro")
    return jsonify({"reply": reply})

@app.route('/api/ai/generate_banner', methods=['POST'])
def ai_banner():
    topic = request.json.get('topic')
    instr = "Ты — креативный маркетолог. Напиши заголовок и короткий продающий текст для баннера. Верни ТОЛЬКО JSON: {\"title\": \"...\", \"text\": \"...\"}"
    ai_res = call_ai(f"Тема: {topic}", instr, "gemini-3.1-pro")
    
    try: data = json.loads(ai_res)
    except: data = {"title": "Особое предложение", "text": ai_res}
    
    # Генерация QR
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data("https://nikolaich.shop"); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG")
    data['qr'] = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
    return jsonify(data)

# АДМИНКА
@app.route('/admin')
def admin_page(): return send_from_directory('static', 'admin.html')

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    conn = get_db()
    users = [dict(r) for r in conn.execute('SELECT * FROM users WHERE role="client"').fetchall()]
    conn.close(); return jsonify(users)

@app.route('/api/admin/approve', methods=['POST'])
def admin_approve():
    d = request.json
    conn = get_db()
    conn.execute('UPDATE users SET is_approved=1, vip_code=? WHERE id=?', (d['vip_code'], d['id']))
    conn.commit(); conn.close(); return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
