import telebot
import threading
import time
from datetime import datetime, timedelta
from collections import Counter

from loader import bot, orders_sheet
from config import MANAGER_ID
from database.database import get_db_connection, is_admin
import utils.utils
from utils.utils import admin_required, update_catalog_cache, CACHE_LOCK, escape_markdown

# ==========================================
#        ГЛАВНОЕ МЕНЮ АДМИНА
# ==========================================

@bot.message_handler(regexp='^👑 Админ-панель$')
@admin_required
def handle_admin_panel_button(message):
    show_admin_panel(message)

@bot.message_handler(commands=['admin'])
@admin_required
def show_admin_panel(message):
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(text="👥 Управление Пользователями", callback_data="admin_users_menu"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="🏪 Управление Магазином", callback_data="admin_shop_menu"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="⚙️ Проверить статус", callback_data="admin_check_status"))
    
    # Отправляем новое сообщение или редактируем старое
    if isinstance(message, telebot.types.CallbackQuery):
        bot.edit_message_text("👑 Админ-панель", chat_id=message.message.chat.id, message_id=message.message.message_id, reply_markup=keyboard)
    else:
        bot.send_message(message.chat.id, "👑 Админ-панель", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_panel_main')
def back_to_admin_panel(call):
    bot.answer_callback_query(call.id)
    show_admin_panel(call)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_check_status')
def handle_check_status(call):
    # Проверка прав внутри декоратора может не сработать на callback, проверяем явно или доверяем логике меню
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "✅ Бот онлайн и работает стабильно!")

# ==========================================
#        УПРАВЛЕНИЕ МАГАЗИНОМ
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == 'admin_shop_menu')
def handle_shop_menu(call):
    bot.answer_callback_query(call.id)
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(text="🔄 Синхронизировать каталог", callback_data="admin_sync"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="🏷️ Управление промокодами", callback_data="admin_promo_menu"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_panel_main"))
    bot.edit_message_text("🏪 Управление Магазином", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == 'admin_sync')
def handle_sync_callback(call):
    bot.answer_callback_query(call.id, "Запускаю синхронизацию...")
    bot.send_message(call.from_user.id, "⏳ Начинаю обновление кэша...")
    if update_catalog_cache():
        bot.send_message(call.from_user.id, "✅ Кэш успешно обновлен.")
    else:
        bot.send_message(call.from_user.id, "❌ Ошибка при обновлении кэша.")

@bot.message_handler(commands=['sync'])
@admin_required
def sync_command_handler(message):
    bot.send_message(message.from_user.id, "Запускаю принудительное обновление кэша...")
    if update_catalog_cache():
        bot.send_message(message.from_user.id, "✅ Кэш успешно обновлен.")
    else:
        bot.send_message(message.from_user.id, "❌ Произошла ошибка.")

# --- ПРОМОКОДЫ ---
@bot.callback_query_handler(func=lambda call: call.data == 'admin_promo_menu')
def handle_promo_menu(call):
    bot.answer_callback_query(call.id)
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(text="➕ Создать промокод", callback_data="promo_create"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="📋 Список промокодов", callback_data="promo_list"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="🗑️ Удалить промокод", callback_data="promo_delete"))
    keyboard.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад в меню магазина", callback_data="admin_shop_menu"))
    bot.edit_message_text("🏷️ Управление промокодами", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == 'promo_create')
def handle_promo_create(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, "Введите данные: `КОД %СКИДКИ КОЛ-ВО`\nПример: `SALE20 20 50`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_promo_creation)

def process_promo_creation(message):
    try:
        code, discount_str, uses_str = message.text.split()
        discount = int(discount_str)
        uses = int(uses_str)
        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO promo_codes (code, discount_percent, uses_left) VALUES (?, ?, ?)", (code.upper(), discount, uses))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Промокод `{code.upper()}` создан.")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка формата: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'promo_list')
def handle_promo_list(call):
    bot.answer_callback_query(call.id)
    conn = get_db_connection()
    promos = conn.execute("SELECT code, discount_percent, uses_left FROM promo_codes").fetchall()
    conn.close()
    
    response = "📋 *Список промокодов:*\n\n" if promos else "Активных промокодов нет."
    for p in promos:
        response += f"Code: `{p['code']}` | -{p['discount_percent']}% | Осталось: {p['uses_left']}\n"
        
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_promo_menu"))
    bot.edit_message_text(response, chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode="Markdown", reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data == 'promo_delete')
def handle_promo_delete_prompt(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, "Введите код промокода для удаления:")
    bot.register_next_step_handler(msg, process_promo_deletion)

def process_promo_deletion(message):
    code = message.text.upper()
    conn = get_db_connection()
    cursor = conn.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
    conn.commit()
    conn.close()
    if cursor.rowcount > 0:
        bot.reply_to(message, f"✅ Промокод `{code}` удален.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Промокод `{code}` не найден.", parse_mode="Markdown")

# ==========================================
#        УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ==========================================

USERS_PER_PAGE = 8

@bot.callback_query_handler(func=lambda call: call.data == 'admin_users_menu')
def handle_user_management_menu(call):
    bot.answer_callback_query(call.id)
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("👥 Список всех пользователей", callback_data="list_users_page_0"))
    keyboard.add(telebot.types.InlineKeyboardButton("📋 Список партнеров", callback_data="list_partners_page_0"))
    keyboard.add(telebot.types.InlineKeyboardButton("📈 Статистика по ID", callback_data="admin_partner_stats_prompt"))
    keyboard.add(telebot.types.InlineKeyboardButton("💰 Изменить баланс по ID", callback_data="admin_edit_balance_prompt"))
    keyboard.add(telebot.types.InlineKeyboardButton("👑 Добавить админа по ID", callback_data="admin_add_admin_prompt"))
    keyboard.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel_main"))
    bot.edit_message_text("👥 Управление Пользователями", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=keyboard)

def generate_paginated_list(page=0, list_type='all'):
    offset = page * USERS_PER_PAGE
    conn = get_db_connection()
    cursor = conn.cursor()

    if list_type == 'partners':
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_partner = 1")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT user_id, username, commission_percent FROM users WHERE is_partner = 1 LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset))
        header = "📋 *Список партнеров:*\n\n"
        prefix = "list_partners_page_"
    else:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT user_id, username, is_partner FROM users LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset))
        header = "👥 *Список пользователей:*\n\n"
        prefix = "list_users_page_"
    
    users = cursor.fetchall()
    conn.close()

    if not users: return "Список пуст.", None

    keyboard = telebot.types.InlineKeyboardMarkup()
    for user in users:
        info = f"👤 @{user['username']}" if user['username'] else f"ID: {user['user_id']}"
        if list_type == 'partners': info += f" ({user['commission_percent']}%)"
        elif user['is_partner']: info += " (Партнер)"
        
        keyboard.add(telebot.types.InlineKeyboardButton(text=info, callback_data=f"view_user_{user['user_id']}_{page}_{list_type}"))

    total_pages = (total_users + USERS_PER_PAGE - 1) // USERS_PER_PAGE if total_users > 0 else 1
    nav_btns = []
    if page > 0: nav_btns.append(telebot.types.InlineKeyboardButton("⬅️", callback_data=f"{prefix}{page-1}"))
    if page < total_pages - 1: nav_btns.append(telebot.types.InlineKeyboardButton("➡️", callback_data=f"{prefix}{page+1}"))
    if nav_btns: keyboard.add(*nav_btns)
    
    keyboard.add(telebot.types.InlineKeyboardButton("⬅️ Назад в меню", callback_data="admin_users_menu"))
    return header + f"\nСтраница {page + 1} из {total_pages}", keyboard

@bot.callback_query_handler(func=lambda call: call.data.startswith(('list_users_page_', 'list_partners_page_')))
def handle_list_pagination(call):
    page = int(call.data.split('_')[-1])
    l_type = 'partners' if 'partners' in call.data else 'all'
    text, kb = generate_paginated_list(page, l_type)
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=kb)

# --- ПРОСМОТР ПРОФИЛЯ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith('view_user_'))
def handle_view_user(call):
    _, _, user_id, page, list_type = call.data.split('_')
    user_id = int(user_id)

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()

    if not user:
        bot.answer_callback_query(call.id, "Пользователь не найден!", show_alert=True)
        return

    username = f"@{user['username']}" if user['username'] else "Нет"
    text = (f"👤 *Профиль*\nID: `{user['user_id']}`\nUsername: {escape_markdown(username)}\n"
            f"Вход: {user['first_seen']}\nАктивность: {user['last_seen']}\n")

    keyboard = telebot.types.InlineKeyboardMarkup()

    if user['is_partner']:
        text += f"Статус: Партнер ({user['commission_percent']}%)\nБаланс: {user['balance']:.2f} zl.\n"
        keyboard.add(telebot.types.InlineKeyboardButton("💰 Изменить баланс", callback_data=f"edit_balance_profile_{user_id}"))
        keyboard.add(telebot.types.InlineKeyboardButton("🔄 Изменить %", callback_data=f"change_commission_{user_id}"))
        keyboard.add(telebot.types.InlineKeyboardButton("📈 Статистика", callback_data=f"partner_stats_{user_id}"))
        keyboard.add(telebot.types.InlineKeyboardButton("❌ Удалить партнера", callback_data=f"remove_partner_{user_id}"))
    else:
        text += "Статус: Пользователь\n"
        keyboard.add(telebot.types.InlineKeyboardButton("✅ Сделать партнером", callback_data=f"make_partner_{user_id}"))

    back_cb = f"list_users_page_{page}" if list_type == 'all' else f"list_partners_page_{page}"
    keyboard.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data=back_cb))
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=keyboard)

# --- ДЕЙСТВИЯ С ПОЛЬЗОВАТЕЛЯМИ ---

# 1. Изменение баланса
@bot.callback_query_handler(func=lambda call: call.data.startswith('edit_balance_profile_'))
def prompt_edit_balance_profile(call):
    uid = int(call.data.split('_')[-1])
    msg = bot.send_message(call.from_user.id, f"Введите сумму (+ или -) для ID {uid}:")
    bot.register_next_step_handler(msg, process_edit_balance_input_id_known, uid)

def process_edit_balance_input_id_known(message, user_id):
    try:
        amount = float(message.text)
        conn = get_db_connection()
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        new_bal = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()[0]
        conn.close()
        
        bot.reply_to(message, f"✅ Баланс изменен. Новый: {new_bal:.2f} zl.")
        try: bot.send_message(user_id, f"ℹ️ Ваш баланс изменен на {amount:.2f} zl.")
        except: pass
    except ValueError:
        bot.reply_to(message, "❌ Введите число.")

# 2. Сделать партнером
@bot.callback_query_handler(func=lambda call: call.data.startswith('make_partner_'))
def prompt_make_partner(call):
    uid = int(call.data.split('_')[-1])
    msg = bot.send_message(call.from_user.id, f"Введите % комиссии для ID {uid}:")
    bot.register_next_step_handler(msg, process_make_partner, uid)

def process_make_partner(message, user_id):
    try:
        pct = float(message.text)
        conn = get_db_connection()
        conn.execute("UPDATE users SET is_partner = 1, commission_percent = ? WHERE user_id = ?", (pct, user_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Партнер создан ({pct}%).")
        try: bot.send_message(user_id, "🎉 Вы стали партнером!")
        except: pass
    except: bot.reply_to(message, "❌ Ошибка.")

# 3. Удалить партнера
@bot.callback_query_handler(func=lambda call: call.data.startswith('remove_partner_'))
def handle_remove_partner(call):
    uid = int(call.data.split('_')[-1])
    conn = get_db_connection()
    conn.execute("UPDATE users SET is_partner = 0, commission_percent = 0 WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()
    bot.answer_callback_query(call.id, "Партнер удален.", show_alert=True)
    # Возвращаем в меню
    handle_user_management_menu(call)

# 4. Изменить %
@bot.callback_query_handler(func=lambda call: call.data.startswith('change_commission_'))
def prompt_change_com(call):
    uid = int(call.data.split('_')[-1])
    msg = bot.send_message(call.from_user.id, "Введите НОВЫЙ %:")
    bot.register_next_step_handler(msg, process_change_com, uid)

def process_change_com(message, user_id):
    try:
        pct = float(message.text)
        conn = get_db_connection()
        conn.execute("UPDATE users SET commission_percent = ? WHERE user_id = ?", (pct, user_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Процент изменен на {pct}%.")
    except: bot.reply_to(message, "❌ Ошибка.")

# 5. Статистика партнера
@bot.callback_query_handler(func=lambda call: call.data.startswith('partner_stats_'))
def handle_partner_stats(call):
    uid = int(call.data.split('_')[-1])
    conn = get_db_connection()
    cur = conn.cursor()
    
    user = cur.execute("SELECT commission_percent, balance, username FROM users WHERE user_id = ?", (uid,)).fetchone()
    refs = cur.execute("SELECT COUNT(id) FROM referrals WHERE referrer_id = ?", (uid,)).fetchone()[0]
    orders = cur.execute("SELECT COUNT(id), SUM(order_amount), SUM(commission_amount) FROM referred_orders WHERE partner_id = ?", (uid,)).fetchone()
    conn.close()

    if not user: return
    
    text = (f"📈 *Статистика @{escape_markdown(user['username'])}*\n\n"
            f"Комиссия: {user['commission_percent']}%\nБаланс: {user['balance']:.2f} zl.\n"
            f"Рефералов: {refs}\nЗаказов: {orders[0] or 0}\n"
            f"Сумма заказов: {orders[1] or 0:.2f} zl.\nЗаработано: {orders[2] or 0:.2f} zl.")
    
    bot.send_message(call.from_user.id, text, parse_mode="Markdown")

# 6. Команды ввода ID (для кнопок "по ID")
@bot.callback_query_handler(func=lambda call: call.data == 'admin_partner_stats_prompt')
def prompt_stats_id(call):
    bot.send_message(call.from_user.id, "Введите ID партнера:")
    bot.register_next_step_handler(call.message, lambda m: handle_partner_stats(type('obj', (object,), {'data': f'partner_stats_{m.text}', 'message': m, 'from_user': m.from_user})))

@bot.callback_query_handler(func=lambda call: call.data == 'admin_add_admin_prompt')
def prompt_add_admin(call):
    msg = bot.send_message(call.from_user.id, "Введите ID нового админа:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    try:
        uid = int(message.text)
        conn = get_db_connection()
        if not conn.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone():
            bot.reply_to(message, "❌ Юзер не найден в БД.")
            return
        conn.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ Админ добавлен.")
        try: bot.send_message(uid, "👑 Вам выданы права администратора.")
        except: pass
    except: bot.reply_to(message, "❌ Ошибка.")

@bot.callback_query_handler(func=lambda call: call.data == 'admin_edit_balance_prompt')
def prompt_edit_bal_manual(call):
    msg = bot.send_message(call.from_user.id, "Введите `ID СУММА` (напр. `12345 50`):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_edit_bal_manual)

def process_edit_bal_manual(message):
    try:
        uid_str, amt_str = message.text.split()
        process_edit_balance_input_id_known(type('obj', (object,), {'text': amt_str, 'chat': message.chat, 'reply_to': bot.reply_to}), int(uid_str))
    except: bot.reply_to(message, "❌ Ошибка формата.")

# ==========================================
#        РАССЫЛКА И СТАТИСТИКА
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == 'admin_broadcast')
def handle_broadcast_callback(call):
    msg = bot.send_message(call.from_user.id, "Введите текст рассылки (/cancel_broadcast для отмены):")
    bot.register_next_step_handler(msg, process_broadcast_text)

def process_broadcast_text(message):
    if message.text == '/cancel_broadcast':
        bot.send_message(message.chat.id, "Отмена.")
        return
    bot.send_message(message.chat.id, "⏳ Рассылка запущена...")
    threading.Thread(target=broadcast_message, args=(message.from_user.id, message.text)).start()

def broadcast_message(admin_id, text):
    conn = get_db_connection()
    users = conn.execute("SELECT user_id FROM users").fetchall()
    conn.close()
    ok, fail = 0, 0
    for u in users:
        try:
            bot.send_message(u['user_id'], text, parse_mode="Markdown")
            ok += 1
        except: fail += 1
        time.sleep(0.05)
    bot.send_message(admin_id, f"✅ Рассылка завершена!\nУспешно: {ok}\nОшибок: {fail}")

def get_general_stats_text():
    """Считает статистику и возвращает текст. Не требует прав админа для вызова (права проверяются выше)."""
    try:
        all_orders = orders_sheet.get_all_records()
        confirmed = [o for o in all_orders if o.get('Статус') == 'Подтверждён']
        total_rev = sum(float(str(o.get('Сумма', 0)).replace(',', '.')) for o in confirmed)
        
        conn = get_db_connection()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d") + "%"
        new_today = conn.execute("SELECT COUNT(*) FROM users WHERE first_seen LIKE ?", (today,)).fetchone()[0]
        conn.close()
        
        return (f"📊 *Сводка*\n\n"
                f"Заказов всего: {len(all_orders)}\nПодтверждено: {len(confirmed)}\n"
                f"Выручка: {total_rev:.2f} zl.\n\n"
                f"Пользователей: {total_users}\nНовых сегодня: {new_today}")
    except Exception as e:
        return f"Ошибка при расчете статистики: {e}"

# --- СТАТИСТИКА ---
@bot.callback_query_handler(func=lambda call: call.data == 'admin_stats')
def admin_stats_menu(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Нет прав")
        return

    bot.answer_callback_query(call.id)
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("📊 Общая сводка", callback_data="stats_general"))
    kb.add(telebot.types.InlineKeyboardButton("🔥 Топ товаров", callback_data="stats_top_products"))
    kb.add(telebot.types.InlineKeyboardButton("🏆 Топ клиентов", callback_data="stats_top_users"))
    kb.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_panel_main"))
    bot.edit_message_text("📊 Выберите тип статистики:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == 'stats_general')
def handle_stats_general(call):
    text = get_general_stats_text()
    
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_stats"))
    
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=kb)

@bot.message_handler(commands=['stats'])
@admin_required
def stats_handler(message):
    try:
        all_orders = orders_sheet.get_all_records()
        confirmed = [o for o in all_orders if o.get('Статус') == 'Подтверждён']
        total_rev = sum(float(str(o.get('Сумма', 0)).replace(',','.')) for o in confirmed)
        
        conn = get_db_connection()
        total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        today = datetime.now().strftime("%Y-%m-%d") + "%"
        new_today = conn.execute("SELECT COUNT(*) FROM users WHERE first_seen LIKE ?", (today,)).fetchone()[0]
        conn.close()
        
        text = (f"📊 *Сводка*\n\n"
                f"Заказов всего: {len(all_orders)}\nПодтверждено: {len(confirmed)}\n"
                f"Выручка: {total_rev:.2f} zl.\n\n"
                f"Пользователей: {total_users}\nНовых сегодня: {new_today}")
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'stats_top_products')
def handle_stats_top_products(call):
    bot.answer_callback_query(call.id, "Считаю...")
    try:
        orders = [o for o in orders_sheet.get_all_records() if o.get('Статус') == 'Подтверждён']
        cnt = Counter()
        for o in orders:
            cnt.update(str(o.get('Состав заказа', '')).split('; '))
        
        # Используем кэш из модуля utils
        with CACHE_LOCK:
             all_items = {str(i['id']).strip(): i for i in utils.CATALOG_CACHE}

        text = "🔥 *Топ товаров:*\n\n"
        for i, (pid, count) in enumerate(cnt.most_common(10), 1):
            name = all_items.get(pid.strip(), {}).get('Название', f"ID {pid}")
            text += f"{i}. {escape_markdown(name)} - {count} шт.\n"
            
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_stats")))
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'stats_top_users')
def handle_stats_top_users(call):
    bot.answer_callback_query(call.id, "Считаю...")
    try:
        orders = [o for o in orders_sheet.get_all_records() if o.get('Статус') == 'Подтверждён']
        user_spend = {}
        for o in orders:
            uid = str(o.get('ID Пользователя'))
            amt = float(str(o.get('Сумма', 0)).replace(',','.'))
            if uid not in user_spend: user_spend[uid] = 0
            user_spend[uid] += amt
            
        sorted_users = sorted(user_spend.items(), key=lambda x: x[1], reverse=True)[:10]
        text = "🏆 *Топ клиентов:*\n\n"
        for i, (uid, amt) in enumerate(sorted_users, 1):
            text += f"{i}. ID `{uid}` — {amt:.2f} zl.\n"
            
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=telebot.types.InlineKeyboardMarkup().add(telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_stats")))
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

# ==========================================
#        ПРОЧИЕ КОМАНДЫ (/cancel и др)
# ==========================================

@bot.message_handler(commands=['cancel'])
@admin_required
def cancel_order_command(message):
    try:
        oid = message.text.split()[1]
        cell = orders_sheet.find(oid)
        if cell:
            orders_sheet.update_cell(cell.row, 6, "Отменён")
            bot.reply_to(message, f"✅ Заказ `{oid}` отменен.", parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Не найден.")
    except:
        bot.reply_to(message, "Формат: `/cancel ID`", parse_mode="Markdown")

@bot.message_handler(commands=['addpartner'])
@admin_required
def add_partner_cmd(message):
    try:
        _, uid, pct = message.text.split()
        process_make_partner(type('obj', (object,), {'text': pct, 'chat': message.chat, 'reply_to': bot.reply_to}), int(uid))
    except: bot.reply_to(message, "Формат: `/addpartner ID %`")

@bot.message_handler(commands=['removepartner'])
@admin_required
def remove_partner_cmd(message):
    try:
        handle_remove_partner(type('obj', (object,), {'data': f"remove_{message.text.split()[1]}", 'id': '0'})) # Упрощенный вызов
        bot.reply_to(message, "Партнер удален.")
    except: bot.reply_to(message, "Формат: `/removepartner ID`")

@bot.message_handler(commands=['editbalance'])
@admin_required
def edit_balance_cmd(message):
    process_edit_bal_manual(message)