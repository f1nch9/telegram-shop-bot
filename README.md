# 🛒 Modular Telegram Vape Shop Bot

A professional, modular Telegram bot designed for e-commerce (specifically Vape Shops).
The bot features a hierarchical catalog, a smart shopping cart, Google Sheets integration for product management, and a comprehensive admin panel.

## ✨ Features

### 👤 User Experience
* **Catalog Navigation:** Step-by-step menu (Category ➡️ Manufacturer ➡️ Line ➡️ Product).
* **Smart Cart:** Add/remove items, manage quantities, and apply promo codes.
* **Discounts:**
    * **Volume Discount:** Automatic discount when buying X+ items (configurable).
    * **Promo Codes:** Support for limited-use discount codes.
* **User Profile:** View order history and referral statistics.
* **Referral System:** Users earn a commission percentage from their invitees' purchases.
* **Payment & Delivery:** Support for various delivery methods (Pickup, InPost) and payments (Cash, Blik, Crypto, Transfers).

### 👑 Admin & Management
* **Google Sheets Sync:** Manage your inventory (stock, prices, photos) directly in Google Sheets. No database knowledge required.
* **Admin Panel:** GUI inside Telegram to view stats, managing users, and broadcast messages.
* **Order Management:** Real-time order notifications with "Confirm" and "Cancel" buttons that update stock automatically.
* **Automated Backups:** The bot automatically sends database backups to a private technical channel.

## 🛠 Tech Stack
* **Python 3.8+**
* **pyTelegramBotAPI (Telebot)**
* **Google Sheets API (gspread)**
* **SQLite** (Database)
* **Threading** (Background tasks)

## 📂 Project Structure

```
├── database/
│   ├── database.py       # SQLite connection and queries
│   └── bot_database.db   # User and order data 
├── handlers/
│   ├── handlers_user.py  # User interaction logic (catalog, cart)
│   ├── handlers_admin.py # Admin panel logic
├── utils/
│   └── utils.py          # Helper functions (caching, backups)
├── config.py             # Configuration settings
├── loader.py             # Bot and API initialization
├── main.py               # Entry point
├── your-google-key.json  # your-google-key
└── requirements.txt      # Python dependencies
```

## 🚀 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/f1nch9/telegram-shop-bot.git](https://github.com/f1nch9/telegram-shop-bot.git)
   cd telegram-shop-bot
   ```

2. **Install dependencies:**

```bash
pip install -r requirements.txt
```

3. **Google Cloud Setup:**

Create a project in Google Cloud Console.

Enable Google Sheets API and Google Drive API.

Create a Service Account, download the JSON key file, and place it in the project root folder.

Share your Google Sheet with the client_email found in the JSON key.

4. **Configuration:**

Open config.py.

Replace the placeholder values (YOUR_BOT_TOKEN, MANAGER_ID, etc.) with your real data.

Update the Google Sheet tab names if necessary.

5. **Run the bot:**

```bash
python main.py
```


📜**License**

This project is licensed under the **MIT License with Commons Clause**.

✅ **You are free to**: Use this bot for your own business, modify the code, and host it.

✅ **You must**: Keep the author's name and copyright notice.

❌ **You may not**: Sell this source code or resell it as a standalone software product.



👨‍💻 **Services & Custom Development**
Do you like this bot but don't know how to set it up? Or do you need a custom feature?

I offer professional development services:

🚀 **Hosting & Setup**: I can deploy this bot to a VPS (server) for you, ensuring it runs 24/7.

🔧 **Customization**: I can add new payment methods, change the design, or other.

🤖 **Custom Bots**: Development of Telegram bots of any complexity (Shops, AI Assistants, Parsers).


**Contact me on Telegram: 👉 @f1nch_gg**
