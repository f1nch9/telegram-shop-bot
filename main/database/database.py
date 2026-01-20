import sqlite3
from config import DB_NAME, MANAGER_ID

def get_db_connection():
    """Создает и настраивает соединение с базой данных для быстрой работы."""
    conn = sqlite3.connect(DB_NAME, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row # Для удобного доступа к колонкам по имени
    return conn

def init_db():
    """Инициализация базы данных: создание таблиц и миграции."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY, username TEXT, first_seen TEXT, last_seen TEXT,
            is_partner INTEGER DEFAULT 0, commission_percent REAL DEFAULT 0, balance REAL DEFAULT 0,
            is_admin INTEGER DEFAULT 0 
        )
    ''')
    
    # Таблицы для партнерской программы
    cursor.execute('CREATE TABLE IF NOT EXISTS referrals (id INTEGER PRIMARY KEY, referrer_id INTEGER, referred_id INTEGER UNIQUE)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS referred_orders (
            id INTEGER PRIMARY KEY, order_id TEXT, partner_id INTEGER, buyer_id INTEGER,
            order_amount REAL, commission_amount REAL, order_items TEXT, order_date TEXT
        )
    ''')

    # Таблица корзины
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart_items (
            user_id INTEGER,
            product_id TEXT,
            quantity INTEGER,
            promo_code TEXT,
            PRIMARY KEY (user_id, product_id)
        )
    ''')

    # Таблица промокодов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            discount_percent INTEGER,
            uses_left INTEGER
        )
    ''')

    # Миграции (добавление новых колонок в существующие таблицы без их удаления)
    try:
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'balance' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
        if 'last_seen' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN last_seen TEXT")
        if 'is_admin' not in columns: cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except Exception as e:
        print(f"Ошибка при миграции базы данных: {e}")
        
    conn.commit()
    conn.close()

def get_cart_items(user_id):
    """Получает товары в корзине пользователя из БД в формате словаря {id: qty}."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT product_id, quantity FROM cart_items WHERE user_id = ?", (user_id,))
    items = cursor.fetchall()
    conn.close()
    return {item['product_id']: item['quantity'] for item in items}

def is_partner(user_id):
    """Проверяет, является ли пользователь партнером."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_partner FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result['is_partner'] == 1

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором."""
    # Главный админ (из конфига) всегда имеет доступ
    if user_id == MANAGER_ID:
        return True
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_admin FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    
    return result and result['is_admin'] == 1