import telebot
import uuid
import threading
from datetime import datetime
from collections import Counter

# Импорты из наших модулей
from loader import bot, sheet, orders_sheet, user_order_data
from config import MANAGER_ID, MANAGER_USERNAME
from database.database import get_db_connection, get_cart_items, is_partner
import utils.utils
from utils.utils import (
    update_last_seen, update_cart_message, escape_markdown, 
    calculate_volume_discount, CACHE_LOCK
)

# ==========================================
#        ГЛАВНОЕ МЕНЮ И START
# ==========================================

def get_main_keyboard(user_id):
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Каталог", "Корзина")
    keyboard.add("Мои заказы 📋")
    if is_partner(user_id):
        keyboard.add("Партнерская программа 📈")
 
    if utils.is_admin(user_id): 
        keyboard.add("👑 Админ-панель")
    return keyboard

@bot.message_handler(commands=['start'])
@update_last_seen
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # --- Логика рефералов ---
    parts = message.text.split()
    if len(parts) > 1 and parts[1].startswith('ref'):
        referrer_id = parts[1][3:]
        if referrer_id.isdigit() and int(referrer_id) != user_id:
            conn = get_db_connection()
            try:
                # Пытаемся записать реферала (UNIQUE игнорирует дубли)
                conn.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (int(referrer_id), user_id))
                if conn.total_changes > 0: # Если запись произошла
                    conn.commit()
                    try:
                        u_info = f"@{username}" if username else f"ID: {user_id}"
                        bot.send_message(int(referrer_id), f"🎉 Новый реферал: *{u_info}*!", parse_mode="Markdown")
                    except: pass
            except Exception as e:
                print(f"Ошибка реферала: {e}")
            finally:
                conn.close()

    bot.send_message(message.chat.id, "Здравствуйте! Воспользуйтесь меню для навигации.", reply_markup=get_main_keyboard(user_id))

@bot.message_handler(regexp='^Главное меню$')
@update_last_seen
def back_to_main_menu(message):
    bot.send_message(message.chat.id, "Вы вернулись в главное меню.", reply_markup=get_main_keyboard(message.from_user.id))

# ==========================================
#        НАВИГАЦИЯ ПО КАТАЛОГУ
# ==========================================

@bot.message_handler(regexp='^Каталог$')
@update_last_seen
def show_categories(message):
    with CACHE_LOCK:
        data = utils.CATALOG_CACHE
    
    # Фильтруем категории, где есть товары > 0
    categories = sorted(list(set(
        item['Категория'] for item in data 
        if item.get('Категория') and int(item.get('Количество', 0)) > 0
    )))
    
    if not categories:
        bot.send_message(message.chat.id, "Каталог пуст.")
        return

    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for category in categories:
        keyboard.add(category)
    keyboard.add("Главное меню")
    
    bot.send_message(message.chat.id, "Выберите категорию:", reply_markup=keyboard)

@bot.message_handler(regexp='^Назад$')
@update_last_seen
def back_handler(message):
    # Универсальная кнопка назад возвращает в категории
    show_categories(message)

# Обработчик Категорий (показывает Производителей)
@bot.message_handler(func=lambda message: message.text in {item.get('Категория') for item in utils.CATALOG_CACHE})
@update_last_seen
def show_manufacturers(message):
    category = message.text
    with CACHE_LOCK:
        data = utils.CATALOG_CACHE
        
    manufacturers = sorted(list(set(
        item['Производитель'] for item in data 
        if item.get('Категория') == category and int(item.get('Количество', 0)) > 0
    )))
    
    if not manufacturers:
        bot.send_message(message.chat.id, "Нет товаров.")
        return
        
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    for manufacturer in manufacturers:
        keyboard.add(f"Производитель: {manufacturer} ({category})")
    keyboard.add("Назад", "Корзина", "Главное меню")
    
    bot.send_message(message.chat.id, f"Категория '{category}':", reply_markup=keyboard)

# Обработчик Производителей (показывает Линейки)
@bot.message_handler(regexp='^Производитель: ')
@update_last_seen
def show_flavor_lines(message):
    try:
        # Парсим "Производитель: Имя (Категория)"
        parts = message.text.replace('Производитель: ', '').split(' (')
        manufacturer = parts[0]
        category = parts[1][:-1]
        
        with CACHE_LOCK:
            data = utils.CATALOG_CACHE
            
        flavor_lines = sorted(list(set(
            item['Линейка'] for item in data 
            if item['Производитель'] == manufacturer and item['Категория'] == category
        )))
        
        # Если линейка всего одна - сразу показываем товары (оптимизация кликов)
        if len(flavor_lines) == 1:
            # Создаем фейковое сообщение для следующей функции
            mock_text = f"{manufacturer} - {flavor_lines[0]} ({category})"
            message.text = mock_text
            show_products_by_flavor_line(message)
            return

        keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        for line in flavor_lines:
            keyboard.add(f"{manufacturer} - {line} ({category})")
        keyboard.add("Назад", "Корзина", "Главное меню")
        
        bot.send_message(message.chat.id, f"Линейки {manufacturer}:", reply_markup=keyboard)
    except Exception as e:
        print(f"Ошибка навигации: {e}")

# Обработчик Линеек (показывает Товары)
# Ловит строки вида "Производитель - Линейка (Категория)"
@bot.message_handler(func=lambda message: ' - ' in message.text and not message.text.startswith('Производитель: '))
@update_last_seen
def show_products_by_flavor_line(message):
    try:
        parts = message.text.split(' - ')
        manufacturer = parts[0]
        rest = parts[1] # "Линейка (Категория)"
        flavor_line = rest.split(' (')[0]
        category = rest.split(' (')[1][:-1]

        with CACHE_LOCK:
            data = utils.CATALOG_CACHE
            
        products = [item for item in data if item['Производитель'] == manufacturer and item['Линейка'] == flavor_line and item['Категория'] == category and int(item.get('Количество', 0)) > 0]
        
        if not products:
            bot.send_message(message.chat.id, "Товары закончились.")
            return

        # Показываем первый товар как "витрину" с фото
        first_item = products[0]
        info_text = f"**{escape_markdown(first_item['Название'])}**\n" \
                    f"Цена: {first_item['Цена']} zl."
        
        # Кнопки для ВСЕХ товаров этой линейки (вкусов)
        keyboard = telebot.types.InlineKeyboardMarkup(row_width=2)
        for p in products:
            keyboard.add(telebot.types.InlineKeyboardButton(text=p['Описание'], callback_data=f"add_to_cart_{p['id']}"))
        
        keyboard.add(telebot.types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"back_to_manufacturers_{category}"))
        
        if first_item['URL_фото']:
            try:
                bot.send_photo(message.chat.id, first_item['URL_фото'], caption=info_text, parse_mode="Markdown", reply_markup=keyboard)
            except:
                bot.send_message(message.chat.id, info_text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            bot.send_message(message.chat.id, info_text, parse_mode="Markdown", reply_markup=keyboard)
            
    except Exception as e:
        print(f"Ошибка отображения товаров: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_manufacturers_'))
def back_to_manufacturers_callback(call):
    bot.answer_callback_query(call.id)
    cat = call.data.replace('back_to_manufacturers_', '')
    # Эмулируем нажатие кнопки категории
    call.message.text = cat
    show_manufacturers(call.message)
    # Удаляем старое сообщение с фото
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass

# ==========================================
#        КОРЗИНА
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('add_to_cart_'))
@update_last_seen
def add_to_cart_handler(call):
    product_id = call.data.replace('add_to_cart_', '')
    user_id = call.from_user.id
    
    with CACHE_LOCK:
        all_items = {str(item['id']).strip(): item for item in utils.CATALOG_CACHE}
    
    item = all_items.get(product_id)
    if item and int(item['Количество']) > 0:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Проверяем текущее кол-во в корзине
        cur.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        res = cur.fetchone()
        current_qty = res['quantity'] if res else 0
        
        if current_qty < int(item['Количество']):
            cur.execute("INSERT OR REPLACE INTO cart_items (user_id, product_id, quantity) VALUES (?, ?, ?)", 
                        (user_id, product_id, current_qty + 1))
            conn.commit()
            bot.answer_callback_query(call.id, "✅ Добавлено!")
        else:
            bot.answer_callback_query(call.id, "❌ Больше нет в наличии.")
        conn.close()
    else:
        bot.answer_callback_query(call.id, "❌ Товар закончился.")

@bot.message_handler(regexp='^Корзина$')
@update_last_seen
def show_cart(message):
    update_cart_message(message.from_user.id, message.chat.id, message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('change_qty_') or call.data in ['clear_cart', 'ignore'])
def modify_cart(call):
    if call.data == 'ignore': 
        bot.answer_callback_query(call.id)
        return

    user_id = call.from_user.id
    conn = get_db_connection()
    
    if call.data == 'clear_cart':
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        bot.answer_callback_query(call.id, "Корзина очищена.")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        bot.send_message(user_id, "Ваша корзина пуста.")
    else:
        action, item_id = call.data.replace('change_qty_', '').split('_', 1)
        
        if action == 'increase':
            with CACHE_LOCK:
                item = next((i for i in utils.CATALOG_CACHE if str(i['id']) == item_id), None)
            
            cur_qty = conn.execute("SELECT quantity FROM cart_items WHERE user_id=? AND product_id=?", (user_id, item_id)).fetchone()
            if item and cur_qty and cur_qty['quantity'] < int(item['Количество']):
                conn.execute("UPDATE cart_items SET quantity = quantity + 1 WHERE user_id=? AND product_id=?", (user_id, item_id))
            else:
                bot.answer_callback_query(call.id, "Максимум доступно.")
                
        elif action == 'decrease':
            cur_qty = conn.execute("SELECT quantity FROM cart_items WHERE user_id=? AND product_id=?", (user_id, item_id)).fetchone()
            if cur_qty and cur_qty['quantity'] > 1:
                conn.execute("UPDATE cart_items SET quantity = quantity - 1 WHERE user_id=? AND product_id=?", (user_id, item_id))
            else:
                conn.execute("DELETE FROM cart_items WHERE user_id=? AND product_id=?", (user_id, item_id))
                
        elif action == 'remove':
            conn.execute("DELETE FROM cart_items WHERE user_id=? AND product_id=?", (user_id, item_id))
            
    conn.commit()
    conn.close()
    update_cart_message(user_id, call.message.chat.id, call.message.message_id)

# Промокоды
@bot.callback_query_handler(func=lambda call: call.data == 'apply_promo')
def promo_prompt(call):
    bot.answer_callback_query(call.id)
    msg = bot.send_message(call.from_user.id, "Введите промокод:")
    bot.register_next_step_handler(msg, process_promo, call.message.chat.id, call.message.message_id)

def process_promo(message, chat_id, message_id):
    code = message.text.upper()
    conn = get_db_connection()
    res = conn.execute("SELECT 1 FROM promo_codes WHERE code=? AND uses_left>0", (code,)).fetchone()
    if res:
        conn.execute("UPDATE cart_items SET promo_code=? WHERE user_id=?", (code, message.from_user.id))
        conn.commit()
        bot.send_message(message.chat.id, "✅ Промокод применен!")
    else:
        bot.send_message(message.chat.id, "❌ Неверный код.")
    conn.close()
    update_cart_message(message.from_user.id, chat_id, message_id)

# ==========================================
#        ОФОРМЛЕНИЕ ЗАКАЗА
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == 'checkout')
@update_last_seen
def checkout_handler(call):
    uid = call.from_user.id
    if not get_cart_items(uid):
        bot.answer_callback_query(call.id, "Корзина пуста!", show_alert=True)
        return

    user_order_data[uid] = {'chat_id': call.message.chat.id, 'message_id': call.message.message_id}
    
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("Самовывоз 🚶(Swiebodzin)", callback_data="delivery_pickup"))
    kb.add(telebot.types.InlineKeyboardButton("InPost 📦", callback_data="delivery_inpost"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text="Выберите способ доставки:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith('delivery_'))
def delivery_handler(call):
    uid = call.from_user.id
    method = call.data.replace('delivery_', '')
    if uid in user_order_data:
        user_order_data[uid]['delivery'] = method
        
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("Наличными 💵", callback_data="payment_cash"))
    kb.add(telebot.types.InlineKeyboardButton("Blik 📱", callback_data="payment_blik"))
    kb.add(telebot.types.InlineKeyboardButton("Перевод PLN 🇵🇱", callback_data="payment_pln"))
    kb.add(telebot.types.InlineKeyboardButton("Перевод UA 🇺🇦", callback_data="payment_ua"))
    kb.add(telebot.types.InlineKeyboardButton("Crypto ₿", callback_data="payment_crypto"))
    
    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, 
                          text=f"Доставка: **{method}**.\nВыберите оплату:", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith('payment_'))
def payment_handler(call):
    uid = call.from_user.id
    pay_method = call.data.replace('payment_', '')
    
    if uid not in user_order_data or 'delivery' not in user_order_data[uid]:
        bot.send_message(uid, "Ошибка сессии. Попробуйте заново.")
        return

    del_method = user_order_data[uid]['delivery']
    cart = get_cart_items(uid)
    if not cart: return

    # Подготовка данных заказа
    with CACHE_LOCK:
        all_items = {str(item['id']).strip(): item for item in utils.CATALOG_CACHE}

    subtotal = 0
    items_list_ids = []
    items_msg_list = Counter()

    for pid, qty in cart.items():
        if pid in all_items:
            subtotal += int(all_items[pid]['Цена']) * qty
            items_list_ids.extend([pid] * qty)
            items_msg_list[pid] += qty
            
    # --- ИТОГОВЫЙ РАСЧЕТ СКИДОК ---
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT promo_code FROM cart_items WHERE user_id = ? LIMIT 1", (uid,))
    res = cursor.fetchone()
    promo_code = res['promo_code'] if res else None
    
    final_price = float(subtotal)
    discount_val = 0.0
    
    # 1. Промокод
    if promo_code:
        cursor.execute("SELECT discount_percent FROM promo_codes WHERE code = ? AND uses_left > 0", (promo_code,))
        disc = cursor.fetchone()
        if disc:
            pct = disc['discount_percent']
            discount_val = final_price * (pct / 100)
            final_price -= discount_val
            cursor.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (promo_code,))
            conn.commit()

    # 2. Объем
    vol_disc, _ = calculate_volume_discount(cart, all_items)
    final_price -= vol_disc
    if final_price < 0: final_price = 0
    
    shipping = 16 if del_method == 'inpost' else 0
    total_with_ship = final_price + shipping
    
    # Сохранение
    order_id = str(uuid.uuid4().hex[:6])
    date_str = datetime.now().strftime("%Y-%m-%d")
    items_str = "; ".join(items_list_ids)
    
    orders_sheet.append_row([order_id, uid, call.from_user.username, items_str, total_with_ship, 'Оформлен', del_method, pay_method, date_str])
    
    # --- ПАРТНЕРСКИЕ НАЧИСЛЕНИЯ (ЗАПИСЬ) ---
    cursor.execute("SELECT referrer_id FROM referrals WHERE referred_id = ?", (uid,))
    ref = cursor.fetchone()
    if ref:
        partner_id = ref[0]
        if is_partner(partner_id):
            item_names = "; ".join([all_items.get(pid, {}).get('Название', pid) for pid in items_list_ids])
            cursor.execute("INSERT INTO referred_orders (order_id, partner_id, buyer_id, order_amount, commission_amount, order_items, order_date) VALUES (?, ?, ?, ?, 0, ?, ?)", 
                           (order_id, partner_id, uid, total_with_ship, item_names, date_str))
            conn.commit()
            try:
                bot.send_message(partner_id, f"🔔 Новый заказ от реферала!\nСумма: {total_with_ship:.2f} zl\n(Комиссия после подтверждения)")
            except: pass
            
    conn.execute("DELETE FROM cart_items WHERE user_id = ?", (uid,))
    conn.commit()
    conn.close()

    # Уведомление Менеджера
    msg_man = (f"🆕 **ЗАКАЗ** `{order_id}`\nUser: @{escape_markdown(call.from_user.username)} (ID:{uid})\n"
               f"Доставка: {del_method}\nОплата: {pay_method}\n\nСостав:\n")
    for pid, c in items_msg_list.items():
        name = all_items.get(pid, {}).get('Название', pid)
        msg_man += f"• {name} x{c}\n"
    msg_man += f"\nИтого: **{total_with_ship:.2f}** zl."
    
    kb_man = telebot.types.InlineKeyboardMarkup()
    kb_man.add(telebot.types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_{order_id}"))
    kb_man.add(telebot.types.InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_{order_id}"))
    
    bot.send_message(MANAGER_ID, msg_man, parse_mode="Markdown", reply_markup=kb_man)
    
    # Сообщение клиенту
    msg_user = (f"✅ **Заказ принят!**\nКод: `{order_id}`\nСумма: **{total_with_ship:.2f}** zl.\n"
                f"Менеджер: @{escape_markdown(MANAGER_USERNAME)}\n\nОжидайте связи!")
    
    bot.edit_message_text(chat_id=user_order_data[uid]['chat_id'], message_id=user_order_data[uid]['message_id'], 
                          text=msg_user, parse_mode="Markdown")
    del user_order_data[uid]

# ==========================================
#        ПОДТВЕРЖДЕНИЕ ЗАКАЗА (Менеджером)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_'))
def confirm_order_handler(call):
    # Эта функция работает от лица менеджера, но находится здесь для целостности процесса покупки
    if call.from_user.id != MANAGER_ID: return
    
    order_id = call.data.replace('confirm_', '')
    bot.answer_callback_query(call.id, "Обработка...")
    bot.edit_message_text(call.message.text + "\n\n⏳ Списываю товары...", call.message.chat.id, call.message.message_id)
    
    def process_background():
        try:
            cell = orders_sheet.find(order_id)
            if not cell: raise ValueError("Не найден")
            
            # Списание остатков
            row_vals = orders_sheet.row_values(cell.row)
            if row_vals[5] == "Подтверждён": return
            
            items = str(row_vals[3]).split('; ')
            cnt = Counter(items)
            for pid, count in cnt.items():
                p_cell = sheet.find(pid)
                if p_cell:
                    curr = int(sheet.cell(p_cell.row, 5).value or 0)
                    sheet.update_cell(p_cell.row, 5, curr - count)
            
            orders_sheet.update_cell(cell.row, 6, "Подтверждён")
            
            # Начисление комиссии партнеру
            conn = get_db_connection()
            ref_ord = conn.execute("SELECT partner_id, order_amount FROM referred_orders WHERE order_id=?", (order_id,)).fetchone()
            if ref_ord:
                pid, amt = ref_ord['partner_id'], ref_ord['order_amount']
                pct = conn.execute("SELECT commission_percent FROM users WHERE user_id=?", (pid,)).fetchone()['commission_percent']
                comm = amt * (pct / 100)
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (comm, pid))
                conn.execute("UPDATE referred_orders SET commission_amount=? WHERE order_id=?", (comm, order_id))
                conn.commit()
                try: bot.send_message(pid, f"💰 Начислено: {comm:.2f} zl за заказ {order_id}")
                except: pass
            conn.close()
            
            bot.edit_message_text(call.message.text.replace("⏳ Списываю товары...", "") + "\n\n✅ ЗАКАЗ ПОДТВЕРЖДЁН", call.message.chat.id, call.message.message_id)
        except Exception as e:
            bot.send_message(call.message.chat.id, f"Ошибка: {e}")

    threading.Thread(target=process_background).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith('cancel_'))
def cancel_order_handler(call):
    if call.from_user.id != MANAGER_ID: return
    oid = call.data.replace('cancel_', '')
    try:
        cell = orders_sheet.find(oid)
        if cell: 
            orders_sheet.update_cell(cell.row, 6, "Отменён")
            bot.edit_message_text(call.message.text + "\n\n❌ ОТМЕНЁН", call.message.chat.id, call.message.message_id)
            
            # Уведомление партнера об отмене
            conn = get_db_connection()
            ref = conn.execute("SELECT partner_id FROM referred_orders WHERE order_id=?", (oid,)).fetchone()
            if ref:
                try: bot.send_message(ref[0], f"❌ Заказ {oid} отменен. Комиссии не будет.")
                except: pass
            conn.close()
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка: {e}")

# ==========================================
#        ЛИЧНЫЙ КАБИНЕТ
# ==========================================

@bot.message_handler(regexp='^Мои заказы 📋$')
@update_last_seen
def my_orders(message):
    uid = message.from_user.id
    try:
        orders = [o for o in orders_sheet.get_all_records() if str(o.get('ID Пользователя')) == str(uid)]
        if not orders:
            bot.send_message(uid, "История пуста.")
            return
            
        text = "📋 *Ваши заказы:*\n\n"
        with CACHE_LOCK: all_items = {str(i['id']).strip(): i for i in utils.CATALOG_CACHE}
        
        for o in orders:
            text += f"🆔 `{o['ID Заказа']}` | {o['Дата']} | {o['Сумма']} zl | {o['Статус']}\n"
            items = str(o['Состав заказа']).split('; ')
            cnt = Counter(items)
            for pid, c in cnt.items():
                name = all_items.get(pid.strip(), {}).get('Название', pid)
                text += f" • {name} x{c}\n"
            text += "\n"
        
        for chunk in telebot.util.smart_split(text, 3000):
            bot.send_message(uid, chunk, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(uid, f"Ошибка: {e}")

@bot.message_handler(regexp='^Партнерская программа 📈$')
@update_last_seen
def partner_program(message):
    uid = message.from_user.id
    if not is_partner(uid): return
    
    conn = get_db_connection()
    user = conn.execute("SELECT commission_percent, balance FROM users WHERE user_id=?", (uid,)).fetchone()
    refs = conn.execute("SELECT COUNT(id) FROM referrals WHERE referrer_id=?", (uid,)).fetchone()[0]
    conn.close()
    
    bot_name = bot.get_me().username
    link = f"https://t.me/{bot_name}?start=ref{uid}"
    
    text = (f"📈 *Партнерка*\n\nКомиссия: {user['commission_percent']}%\nБаланс: **{user['balance']:.2f} zl.**\n\n"
            f"🔗 Ссылка:\n`{link}`\n\nПриглашено: {refs}")
            
    kb = telebot.types.InlineKeyboardMarkup()
    kb.add(telebot.types.InlineKeyboardButton("Вывести средства 💸", callback_data="request_withdrawal"))
    bot.send_message(uid, text, parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data == 'request_withdrawal')
def withdrawal_handler(call):
    msg = bot.send_message(call.from_user.id, "Введите: `СУММА РЕКВИЗИТЫ`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_withdrawal)

def process_withdrawal(message):
    try:
        amt_str, det = message.text.split(maxsplit=1)
        amt = float(amt_str.replace(',', '.'))
        
        conn = get_db_connection()
        bal = conn.execute("SELECT balance FROM users WHERE user_id=?", (message.from_user.id,)).fetchone()[0]
        conn.close()
        
        if amt > bal:
            bot.reply_to(message, f"Не хватает средств. Баланс: {bal}")
            return
            
        bot.send_message(MANAGER_ID, f"💸 **Заявка на вывод**\nUser: @{message.from_user.username}\nID: {message.from_user.id}\nСумма: {amt}\nРеквизиты: `{det}`", parse_mode="Markdown")
        bot.reply_to(message, "Заявка отправлена.")
    except:
        bot.reply_to(message, "Ошибка формата.")

@bot.message_handler(func=lambda m: True)
@update_last_seen
def unknown(message):
    # Ловит всё, что не подошло под фильтры
    bot.send_message(message.chat.id, "Используйте меню.", reply_markup=get_main_keyboard(message.from_user.id))