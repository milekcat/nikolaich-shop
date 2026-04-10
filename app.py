from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

def get_db_connection():
    conn = sqlite3.connect('shop.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def serve_index():
    return send_from_directory('static', 'index.html')

@app.route('/api/products', methods=['GET'])
def get_products():
    try:
        conn = get_db_connection()
        products = conn.execute('SELECT * FROM products WHERE is_available = 1').fetchall()
        conn.close()
        return jsonify([dict(ix) for ix in products])
    except sqlite3.OperationalError:
        return jsonify({"error": "База данных еще не создана"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
