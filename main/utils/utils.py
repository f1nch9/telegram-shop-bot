import threading
import time
import shutil
import os
import telebot
from datetime import datetime
from functools import wraps

from config import (
    DB_NAME, BACKUP_INTERVAL, SYS_CHAT_ID, 
    DISCOUNT_QTY_THRESHOLD, DISCOUNT_PER_LIQUID
)
from loader import bot, sheet
from database.database import get_db_connection, get_cart_items, is_admin

# --- СИСТЕМА КЭШИРОВАНИЯ ---
CATALOG_CACHE = []
CACHE_LOCK = threading.Lock()

def update_catalog_cache():
    """Обновляет локальный кэш данных из Google Таблицы."""
    global CATALOG_CACHE
    print(f"[{datetime.now()}] Начинаю обновление кэша каталога...")
    try:
        if sheet is None:
            print("❌ Ошибка: Нет подключения к таблице.")
            return False
            
        fresh_data = sheet.get_all_records()
        with CACHE_LOCK:
            CATALOG_CACHE = fresh_data
        print(f"[{datetime.now()}] Кэш успешно обновлен. Загружено {len(fresh_data)} позиций.")
        return True
    except Exception as e:
        print(f"[{datetime.now()}] ОШИБКА при обновлении кэша: {e}")
        return False

def periodic_cache_update():
    """Фоновая задача: обновляет кэш каждые 10 минут."""
    while True:
        update_catalog_cache()
        time.sleep(600)

# --- СИСТЕМА БЭКАПОВ ---
def periodic_backup_task():
    """Создает копию БД и отправляет её в тех. чат каждые 4 часа."""
    time.sleep(60) # Даем боту прогрузиться
    
    while True:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_filename = f"backup_{timestamp}_{DB_NAME}"
            
            print(f"[{datetime.now()}] 📦 Создание бэкапа...")
            shutil.copy2(DB_NAME, backup_filename)

            with open(backup_filename, 'rb') as file:
                bot.send_document(
                    chat_id=SYS_CHAT_ID, 
                    document=file,
                    caption=f"📦 Автоматический бэкап базы данных\n🕒 {timestamp}"
                )
            
            print(f"[{datetime.now()}] ✅ Бэкап отправлен.")
            os.remove(backup_filename)

        except Exception as e:
            error_msg = f"⚠️ Ошибка бэкапа: {e}"
            print(error_msg)
            try:
                bot.send_message(SYS_CHAT_ID, error_msg)
            except: pass

        time.sleep(BACKUP_INTERVAL)

# --- ДЕКОРАТОРЫ ---
def update_last_seen(func):
    """Обновляет время последнего визита пользователя в БД."""
    @wraps(func)
    def wrapper(message_or_call, *args, **kwargs):
        if hasattr(message_or_call, 'from_user'):
            user = message_or_call.from_user
            user_id = user.id
            username = user.username
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                conn = get_db_connection()
                # Пытаемся добавить нового или обновить старого
                conn.execute("INSERT OR IGNORE INTO users (user_id, username, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                             (user_id, username, now, now))
                conn.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Ошибка update_last_seen: {e}")
                
        return func(message_or_call, *args, **kwargs)
    return wrapper

def admin_required(func):
    """Ограничивает доступ к функции только для администраторов."""
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        user_id = message.from_user.id
        if is_admin(user_id):
            return func(message, *args, **kwargs)
        else:
            bot.reply_to(message, "⛔️ У вас нет прав для выполнения этой команды.")
            return
    return wrapper

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def escape_markdown(text):
    """Экранирует спецсимволы для MarkdownV2 (хотя используется Markdown)."""
    if text is None: return ""
    text = str(text)
    escape_chars = '_*`[]()~>#+-=|{}.!'
    return ''.join('\\' + char if char in escape_chars else char for char in text)

def calculate_volume_discount(cart_items_db, all_items):
    """Рассчитывает скидку за объем жидкости."""
    liquid_count = 0
    
    for item_id, count in cart_items_db.items():
        item = all_items.get(item_id)
        if item and item.get('Категория') == 'Жидкости':
            liquid_count += count
            
    discount_amount = 0.0
    if liquid_count >= DISCOUNT_QTY_THRESHOLD:
        discount_amount = liquid_count * DISCOUNT_PER_LIQUID
        
    return discount_amount, liquid_count

def update_cart_message(user_id, chat_id, message_id):
    """
    Генерирует текст корзины, считает все скидки (промокоды + объем) 
    и обновляет сообщение в чате.
    """
    with CACHE_LOCK:
        all_items = {str(item['id']).strip(): item for item in CATALOG_CACHE}
    
    cart_items_db = get_cart_items(user_id)
    if not cart_items_db:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Ваша корзина пуста.", reply_markup=None)
        except: pass
        return

    cart_text = "**Ваша корзина:**\n\n"
    total_price = 0
    keyboard_cart = telebot.types.InlineKeyboardMarkup()

    # Генерация списка товаров
    for item_id, count in cart_items_db.items():
        if item_id in all_items:
            item = all_items[item_id]
            price = int(item['Цена']) * count
            total_price += price
            
            cart_text += f"• {escape_markdown(item['Название'])} ({escape_markdown(item['Описание'])}) x{count} \\- {price} zl\n"
            
            # Кнопки управления количеством
            keyboard_cart.add(
                telebot.types.InlineKeyboardButton(text="➖", callback_data=f"change_qty_decrease_{item_id}"),
                telebot.types.InlineKeyboardButton(text=str(count), callback_data="ignore"),
                telebot.types.InlineKeyboardButton(text="➕", callback_data=f"change_qty_increase_{item_id}"),
                telebot.types.InlineKeyboardButton(text="❌ Удалить", callback_data=f"change_qty_remove_{item_id}")
            )

    # --- РАСЧЕТ СКИДОК ---
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT promo_code FROM cart_items WHERE user_id = ? AND promo_code IS NOT NULL", (user_id,))
    promo_result = cursor.fetchone()
    promo_code = promo_result['promo_code'] if promo_result else None
    
    final_price = float(total_price)
    discount_promo_amount = 0.0
    
    # 1. Промокод
    if promo_code:
        cursor.execute("SELECT discount_percent FROM promo_codes WHERE code = ? AND uses_left > 0", (promo_code,))
        discount_result = cursor.fetchone()
        if discount_result:
            discount_percent = discount_result['discount_percent']
            discount_promo_amount = final_price * (discount_percent / 100)
            final_price -= discount_promo_amount
            cart_text += f"\nСкидка по промокоду *{escape_markdown(promo_code)}* ({discount_percent}%): \\-*{discount_promo_amount:.2f}* zl\n"
    conn.close()
    
    # 2. Объемная скидка
    volume_discount, liquid_qty = calculate_volume_discount(cart_items_db, all_items)
    
    if volume_discount > 0:
        final_price -= volume_discount
        cart_text += f"--- Скидка за объём ---\n"
        cart_text += f"Жидкостей в заказе: *{liquid_qty}* шт\n"
        cart_text += f"Скидка (\\-{DISCOUNT_PER_LIQUID:.2f} zl/шт): \\-*{volume_discount:.2f}* zl\n"
        
    if final_price < 0: final_price = 0.0
    
    cart_text += f"\nИтого: **{final_price:.2f}** zl"
    
    # Кнопки действий
    keyboard_cart.add(telebot.types.InlineKeyboardButton(text="🏷️ Промокод", callback_data="apply_promo"))
    keyboard_cart.add(
        telebot.types.InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"),
        telebot.types.InlineKeyboardButton(text="❌ Очистить корзину", callback_data="clear_cart")
    )

    try:
        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=message_id, 
            text=cart_text, 
            parse_mode="Markdown", 
            reply_markup=keyboard_cart
        )
    except Exception as e:
        error_text = str(e)
        # Игнорируем ошибку, если содержимое сообщения не изменилось
        if "message is not modified" in error_text:
            pass 
        # Если сообщение слишком старое или удалено, отправляем новое
        elif "message to edit not found" in error_text or "message can't be edited" in error_text:
             try:
                 bot.send_message(chat_id, cart_text, parse_mode="Markdown", reply_markup=keyboard_cart)
             except:
                 pass # Если совсем ничего не вышло, молчим
        else:
            print(f"Ошибка обновления корзины: {e}")