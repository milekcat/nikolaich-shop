# -*- coding: utf-8 -*-
import sqlite3, json, urllib.parse, requests, uuid, datetime, random, os
from flask import Flask, render_template, request, jsonify, session
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'nikolaich_erp_v13_max'
UPLOAD_FOLDER = 'static/uploads'; os.makedirs(UPLOAD_FOLDER, exist_ok=True)

AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

# ТВОЙ БОЕВОЙ ТОКЕН ВК (Уже вшит!)
VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"
VK_API = "5.131"

def vk_msg(vk_link, text):
    if not vk_link or "vk.com" not in vk_link: return False
    try:
        r = requests.get(f"https://api.vk.com/method/utils.resolveScreenName?screen_name={vk_link.split('/')[-1]}&access_token={VK_TOKEN}&v={VK_API}").json()
        if r.get('response') and r['response']['type'] == 'user':
            requests.post("https://api.vk.com/method/messages.send", data={"user_id": r['response']['object_id'], "random_id": 0, "message": text, "access_token": VK_TOKEN, "v": VK_API})
            return True
    except: pass
    return False

def call_ai(prompt, sys_prompt, model="gemini-2.5-pro", is_json=True):
    payload = {"model": model, "temperature": 0.3, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": prompt}]}
    if is_json: payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}, timeout=50)
        return json.loads(r.json()['choices'][0]['message']['content']) if is_json else r.json()['choices'][0]['message']['content']
    except Exception as e: return {"error": str(e)} if is_json else f"Ошибка ИИ: {e}"

def init_db():
    with sqlite3.connect('shop.db') as conn:
        c = conn.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS settings (k TEXT PRIMARY KEY, v TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT, icon TEXT, sort_order INTEGER, is_hidden INTEGER DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, desc TEXT, price REAL, old_price REAL, stock INTEGER, category_id INTEGER, images TEXT DEFAULT "[]", unit TEXT DEFAULT "шт", step REAL DEFAULT 1, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS banners (id INTEGER PRIMARY KEY, title TEXT, subtitle TEXT, img_url TEXT, bg_color TEXT, link_cat INTEGER, active INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, phone TEXT UNIQUE, name TEXT, full_name TEXT DEFAULT "", social_link TEXT DEFAULT "", addresses TEXT DEFAULT "[]", bonuses INTEGER DEFAULT 0, age_verified INTEGER DEFAULT 0, ref_code TEXT UNIQUE, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        c.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, items_total REAL, package_cost REAL, delivery_cost REAL, final_total REAL, bonuses_spent INTEGER, items TEXT, delivery_type TEXT, payment_type TEXT, status TEXT DEFAULT "Новый", date TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        
        if c.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
            c.executemany('INSERT INTO settings (k, v) VALUES (?,?)', [('shop_name', 'У Николаича'), ('footer_text', 'Фермерские продукты с доставкой. Ярославль.')])
            c.executemany('INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)', [('Мясо','🥩',1,0),('Овощи','🥬',2,0),('18+','🍷',99,1)])
            c.executemany('INSERT INTO products (name, desc, price, stock, category_id, images, unit, step) VALUES (?,?,?,?,?,?,?,?)', [('Рибай', 'Говядина', 850, 15, 1, '["https://images.unsplash.com/photo-1600891964092-4316c288032e?w=500"]', 'кг', 0.1)])
            c.execute('INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat) VALUES (?,?,?,?,?)', ('Свежее мясо!', 'Прямо с фермы', 'https://images.unsplash.com/photo-1600891964092-4316c288032e?w=500', '#ffebee', 1))
    conn.commit()
init_db()

def get_db(q, args=(), one=False):
    with sqlite3.connect('shop.db') as conn:
        conn.row_factory = sqlite3.Row; cur = conn.execute(q, args)
        return dict(cur.fetchone()) if one else [dict(x) for x in cur.fetchall()]

def get_user(phone, name="Клиент", social=""):
    if not phone: return None
    u = get_db("SELECT * FROM users WHERE phone=?", (phone,), True)
    if not u:
        with sqlite3.connect('shop.db') as conn: conn.execute("INSERT INTO users (phone, name, social_link, ref_code) VALUES (?,?,?,?)", (phone, name, social, f"REF-{uuid.uuid4().hex[:6]}"))
        u = get_db("SELECT * FROM users WHERE phone=?", (phone,), True)
    return u

@app.route('/')
def index():
    user = get_user(session.get('phone'))
    is_18 = (user and user['age_verified'] == 2)
    st = {s['k']: s['v'] for s in get_db("SELECT * FROM settings")}
    cats = get_db("SELECT * FROM categories WHERE is_hidden=0 OR is_hidden=? ORDER BY sort_order", (1 if is_18 else 0,))
    prods = get_db("SELECT p.* FROM products p JOIN categories c ON p.category_id = c.id WHERE p.active=1 AND (c.is_hidden=0 OR c.is_hidden=?)", (1 if is_18 else 0,))
    for p in prods: p['images'] = json.loads(p['images']) if p['images'] else []
    return render_template('index.html', st=st, cats=cats, prods=prods, banners=get_db("SELECT * FROM banners WHERE active=1"), user=user)

@app.route('/api/auth/shadow', methods=['POST'])
def auth(): session['phone'] = request.json.get('phone'); return jsonify({"status": "ok"})

@app.route('/api/18plus/request', methods=['POST'])
def req_18():
    d = request.json; phone = d.get('phone')
    if get_user(phone):
        with sqlite3.connect('shop.db') as conn: conn.execute("UPDATE users SET full_name=?, social_link=?, age_verified=1 WHERE phone=?", (d.get('full_name',''), d.get('social_link',''), phone))
    session['phone'] = phone; return jsonify({"status": "ok"})

@app.route('/api/cart/calc', methods=['POST'])
def calc():
    d = request.json; t = float(d.get('items_total', 0)); dt = d.get('delivery_type', 'pickup')
    t = t * 1.05 if dt == 'courier' else t
    pkg = 29 if t > 0 else 0; del_c = 0 if dt == 'pickup' else (0 if t >= 3000 and dt == 'courier' else 150) if dt == 'courier' else 0
    return jsonify({"items_total": t, "package_cost": pkg, "delivery_cost": del_c, "final_total": t + pkg + del_c})

@app.route('/api/checkout', methods=['POST'])
def checkout():
    d = request.json; u = get_user(d.get('phone'), social=d.get('social_link', '')); c = d.get('calc'); dt = d.get('delivery_type'); pt = d.get('payment_type')
    with sqlite3.connect('shop.db') as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO orders (user_id, items_total, package_cost, delivery_cost, final_total, bonuses_spent, items, delivery_type, payment_type) VALUES (?,?,?,?,?,?,?,?,?)", (u['id'], c['items_total'], c['package_cost'], c['delivery_cost'], c['final_total'], 0, json.dumps(d.get('cart')), dt, pt))
        oid = cur.lastrowid
    session['phone'] = d.get('phone')
    if u['social_link']:
        msg = f"🚜 Заказ #{oid} принят!\nСумма: {c['final_total']:.0f} ₽.\nДоставка: {dt}\nОплата: {pt}."
        if pt == 'transfer': msg += "\n💳 Жди реквизиты для перевода!"
        if dt == 'taxi': msg += "\n🚕 Скоро Николаич напишет цену такси!"
        vk_msg(u['social_link'], msg)
    return jsonify({"status": "ok"})

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files: return jsonify({'error': 'No file'})
    f = request.files['file']; fn = secure_filename(str(uuid.uuid4())[:8] + "_" + f.filename)
    f.save(os.path.join(UPLOAD_FOLDER, fn)); return jsonify({'url': f'/{UPLOAD_FOLDER}/{fn}'})

@app.route('/api/ai/<action>', methods=['POST'])
def ai_api(action):
    d = request.json; st = {s['k']: s['v'] for s in get_db("SELECT * FROM settings")}
    if action == 'product_card':
        return jsonify({"html": call_ai(f"{st.get('shop_name')} Напиши аппетитное описание и 1 совет для '{d.get('name')}'. Формат HTML (без тегов html).", "Ты шеф-повар.", "gemini-2.5-pro", False)})
    if action == 'upsell':
        prods = get_db("SELECT id, name, images, price, unit, step FROM products WHERE active=1 AND category_id != 99")
        for p in prods: p['images'] = json.loads(p['images'])
        rec = [p for p in prods if p['name'] not in d.get('cart_items', [])]; random.shuffle(rec)
        return jsonify(rec[:3])
    if action == 'chef':
        cat = ", ".join([f"ID {p['id']}: {p['name']}" for p in get_db("SELECT p.id, p.name FROM products p JOIN categories c ON p.category_id=c.id WHERE p.active=1 AND c.is_hidden=0")])
        return jsonify(call_ai(d.get('query'), f"{st.get('shop_name')} Собери корзину ТОЛЬКО из: {cat}. JSON: {{'message': 'Текст', 'cart_ids': [ID]}}", "gemini-2.5-pro", True))
    if action == 'gen_banner':
        res = call_ai(f"{st.get('shop_name')} Акция: {d.get('topic')}. JSON: title, subtitle, bg_color (hex), img_prompt.", "Креативный директор", "gemini-2.5-pro", True)
        if "error" not in res: res["img_url"] = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(res['img_prompt'])}?width=800&height=400&nologo=true"
        return jsonify(res)

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/admin/<entity>', methods=['GET', 'POST', 'DELETE'])
def admin_api(entity):
    if request.method == 'GET':
        if entity == 'warehouse': return jsonify({"products": [dict(p) for p in get_db("SELECT p.*, c.name as cat_name FROM products p JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC")], "categories": get_db("SELECT * FROM categories ORDER BY sort_order")})
        if entity == 'orders': return jsonify(get_db("SELECT o.*, u.phone, u.full_name, u.social_link FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.id DESC"))
        if entity == 'users': return jsonify(get_db("SELECT * FROM users ORDER BY created_at DESC"))
        if entity == 'banners': return jsonify(get_db("SELECT * FROM banners ORDER BY id DESC"))
        if entity == 'settings': return jsonify({s['k']: s['v'] for s in get_db("SELECT * FROM settings")})
        if entity == 'analytics': return jsonify(get_db("SELECT COUNT(*), SUM(final_total) FROM orders WHERE status != 'Отменен'", one=True))
    
    d = request.json
    with sqlite3.connect('shop.db') as conn:
        if request.method == 'DELETE': conn.execute(f"DELETE FROM {entity} WHERE id=?", (d['id'],))
        elif request.method == 'POST':
            if entity == 'product':
                img = json.dumps(d['images'])
                if d.get('id'): conn.execute("UPDATE products SET name=?, desc=?, price=?, stock=?, category_id=?, images=?, unit=?, step=?, old_price=? WHERE id=?", (d['name'], d['desc'], d['price'], d['stock'], d['category_id'], img, d['unit'], d['step'], d.get('old_price',0), d['id']))
                else: conn.execute("INSERT INTO products (name, desc, price, stock, category_id, images, unit, step, old_price) VALUES (?,?,?,?,?,?,?,?,?)", (d['name'], d['desc'], d['price'], d['stock'], d['category_id'], img, d['unit'], d['step'], d.get('old_price',0)))
            elif entity == 'category':
                if d.get('id'): conn.execute("UPDATE categories SET name=?, icon=?, sort_order=?, is_hidden=? WHERE id=?", (d['name'], d['icon'], d['sort_order'], d['is_hidden'], d['id']))
                else: conn.execute("INSERT INTO categories (name, icon, sort_order, is_hidden) VALUES (?,?,?,?)", (d['name'], d['icon'], d['sort_order'], d['is_hidden']))
            elif entity == 'banners':
                if d.get('id'): conn.execute("UPDATE banners SET title=?, subtitle=?, img_url=?, bg_color=?, link_cat=? WHERE id=?", (d['title'], d['subtitle'], d['img_url'], d['bg_color'], d['link_cat'], d['id']))
                else: conn.execute("INSERT INTO banners (title, subtitle, img_url, bg_color, link_cat) VALUES (?,?,?,?,?)", (d['title'], d['subtitle'], d['img_url'], d['bg_color'], d['link_cat']))
            elif entity == 'settings':
                for k, v in d.items(): conn.execute("INSERT INTO settings (k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=?", (k, v, v))
            elif entity == 'orders':
                conn.execute("UPDATE orders SET status=? WHERE id=?", (d['status'], d['id']))
                if d.get('social_link'): vk_msg(d['social_link'], f"🚜 Статус заказа #{d['id']}: {d['status']}!")
            elif entity == 'users':
                conn.execute("UPDATE users SET full_name=?, phone=?, social_link=?, age_verified=? WHERE id=?", (d['full_name'], d['phone'], d['social_link'], d['age_verified'], d['id']))
    return jsonify({"status": "ok"})

@app.route('/api/admin/vk_action', methods=['POST'])
def admin_vk_action():
    d = request.json; mtype = d.get('msg_type'); link = d.get('vk_link'); val = d.get('custom_val', '')
    if mtype == 'broadcast':
        users = get_db("SELECT social_link FROM users WHERE social_link != ''")
        for u in users: vk_msg(u['social_link'], f"📣 Новости от Николаича: {val}")
        return jsonify({"status": "ok", "sent": len(users)})
    
    txt = "💳 Переведи на +7 (999) 000-00-00. Жду скриншот!" if mtype == 'req' else f"🚕 Цена такси: {val} ₽." if mtype == 'taxi' else "✅ Деньги пришли, заказ пакуется!" if mtype == 'paid' else val
    return jsonify({"status": "ok" if vk_msg(link, f"👨‍🌾 Николаич: {txt}") else "error"})

if __name__ == '__main__': app.run(host='0.0.0.0', port=8085)
