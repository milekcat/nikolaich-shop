import sqlite3

def get_db_connection():
    connection = sqlite3.connect('shop.db')
    connection.row_factory = sqlite3.Row
    return connection

def init_db():
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            amount REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            user_email TEXT NOT NULL,
            yookassa_payment_id TEXT
        )
    ''')
    connection.commit()
    connection.close()

def create_order(amount, user_email):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        'INSERT INTO orders (amount, status, user_email) VALUES (?, ?, ?)',
        (amount, 'pending', user_email)
    )
    order_id = cursor.lastrow_id
    connection.commit()
    connection.close()
    return order_id

def update_order_payment(order_id, yookassa_payment_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        'UPDATE orders SET yookassa_payment_id = ? WHERE id = ?',
        (yookassa_payment_id, order_id)
    )
    connection.commit()
    connection.close()

def update_order_status(order_id, status):
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute(
        'UPDATE orders SET status = ? WHERE id = ?',
        (status, order_id)
    )
    connection.commit()
    connection.close()

def get_order_by_payment_id(yookassa_payment_id):
    connection = get_db_connection()
    cursor = connection.cursor()
    order = cursor.execute(
        'SELECT * FROM orders WHERE yookassa_payment_id = ?',
        (yookassa_payment_id,)
    ).fetchone()
    connection.close()
    return order
