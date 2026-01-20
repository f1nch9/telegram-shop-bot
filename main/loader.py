import telebot
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import API_TOKEN, GOOGLE_CREDENTIALS_FILE, SHEET_NAME_CATALOG, SHEET_NAME_ORDERS

# 1. Инициализация бота
bot = telebot.TeleBot(API_TOKEN)

# 2. Подключение к Google Таблицам
scope = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']

try:
    # Авторизация
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    
    # Открываем листы таблиц (названия берутся из config.py)
    sheet = client.open(SHEET_NAME_CATALOG).sheet1
    orders_sheet = client.open(SHEET_NAME_ORDERS).sheet1
    
    print("✅ Успешное подключение к Google Таблицам")
    
except Exception as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА подключения к Google Таблицам: {e}")
    print("Проверьте наличие файла .json и доступ к интернету.")
    # Инициализируем как None, чтобы импорт прошел, но ошибки будут при попытке использования
    sheet = None
    orders_sheet = None

# 3. Временное хранилище данных для процесса оформления заказа (Wizard)
# Структура: {user_id: {'chat_id': ..., 'message_id': ..., 'delivery': ..., ...}}
user_order_data = {}