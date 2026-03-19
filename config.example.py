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
