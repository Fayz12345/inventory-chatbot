# Database connection
DB_SERVER   = 'your_sql_server_ip'
DB_NAME     = 'your_database_name'
DB_USER     = 'your_db_user'
DB_PASSWORD = 'your_db_password'

# Anthropic API
ANTHROPIC_API_KEY = 'sk-ant-...'

# App secret key (used for login sessions - change this to anything random)
SECRET_KEY = 'your_secret_key'

# Users — generate hashes with: python generate_password_hash.py
# Format: 'username': 'hashed_password'
USERS = {
    'admin': 'pbkdf2:sha256:...',
    'john':  'pbkdf2:sha256:...',
}

# --- Ecommerce settings (Phase 1D) ---

# Amazon SP-API — get from Seller Central > Apps & Services > Develop Apps
AMAZON_SELLER_ID = ''
AMAZON_MARKETPLACE_ID = 'A2EUQ1WTGCTBG2'  # Amazon.ca
AMAZON_REFRESH_TOKEN = ''
AMAZON_LWA_APP_ID = ''
AMAZON_LWA_CLIENT_SECRET = ''

# eBay API — get from developer.ebay.com
EBAY_APP_ID = ''
EBAY_CERT_ID = ''
EBAY_REFRESH_TOKEN = ''

# SMTP (for ecommerce digest emails)
SMTP_HOST = ''
SMTP_PORT = 587
SMTP_USER = ''
SMTP_PASSWORD = ''
ECOMMERCE_EMAIL_FROM = ''
ECOMMERCE_EMAIL_TO = ''

# Pricing
ECOMMERCE_MINIMUM_MARGIN = 25.00

# Base URL for approval links (set to your EC2 public IP + port)
APP_BASE_URL = 'http://your-ec2-ip:5000'
