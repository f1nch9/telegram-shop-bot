import os

# Get the base directory of the project (where this file is located)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Main Telegram Settings ---
# Replace with your own Bot Token obtained from @BotFather
API_TOKEN = 'YOUR_BOT_API_TOKEN_HERE'

# Admin and Chat IDs
# Replace with your Telegram ID (integer)
MANAGER_ID = 12345678            # Main Admin ID (Orders are sent here)
# Replace with your private group ID for backups (integer, starts with -100...)
SYS_CHAT_ID = -100123456789      # ID of the technical channel/group for backups

# Manager's username (displayed to the client after checkout)
MANAGER_USERNAME = "your_username"

# --- Database Settings ---
# The database file is located inside the 'database' folder
# Uses absolute path construction for stability
DB_NAME = os.path.join(BASE_DIR, 'database', 'bot_database.db')

# --- Google Sheets Settings ---
# Name of the JSON key file (must be located in the root project folder)
# Replace 'your-google-key.json' with your actual file name
GOOGLE_CREDENTIALS_FILE = os.path.join(BASE_DIR, 'your-google-key.json')

# Names of the tabs (sheets) in your Google Spreadsheet
# IMPORTANT: These names must match exactly with the tabs in your Google Sheet
SHEET_NAME_CATALOG = 'Catalog'   # Sheet with products
SHEET_NAME_ORDERS = 'Orders'     # Sheet for new orders

# --- Discount Settings ---
DISCOUNT_QTY_THRESHOLD = 5       # Minimum quantity of liquids to trigger a discount
DISCOUNT_PER_LIQUID = 5.0        # Discount amount per item (in currency units)

# --- Backup Settings ---
BACKUP_INTERVAL = 4 * 3600       # Interval for creating backups (in seconds, 4 hours)