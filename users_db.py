import sqlite3
import os
import secrets
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'users.db')


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn, table, column):
    cols = [r['name'] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def init_db():
    conn = _get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL DEFAULT '',
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT,
            email TEXT,
            invite_token TEXT,
            invite_token_expires TEXT,
            password_set INTEGER NOT NULL DEFAULT 1
        )
    ''')
    for col, typedef in [
        ('email', 'TEXT'),
        ('invite_token', 'TEXT'),
        ('invite_token_expires', 'TEXT'),
        ('password_set', 'INTEGER NOT NULL DEFAULT 1'),
    ]:
        if not _column_exists(conn, 'users', col):
            conn.execute(f'ALTER TABLE users ADD COLUMN {col} {typedef}')
    conn.commit()
    conn.close()


def seed_admin_if_empty():
    conn = _get_conn()
    row = conn.execute('SELECT COUNT(*) as cnt FROM users').fetchone()
    if row['cnt'] == 0:
        try:
            conn.execute(
                'INSERT INTO users (username, password_hash, is_admin, created_by, password_set) VALUES (?, ?, 1, ?, 1)',
                ('Admin', generate_password_hash('Feather_2026!'), 'system'),
            )
            conn.commit()
        except Exception:
            pass
    conn.close()


def authenticate(username, password):
    conn = _get_conn()
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if row and row['password_set'] and check_password_hash(row['password_hash'], password):
        return dict(row)
    return None


def get_all_users():
    conn = _get_conn()
    rows = conn.execute(
        'SELECT id, username, email, is_admin, created_at, created_by, password_set FROM users ORDER BY id'
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_user(username, email, is_admin=False, created_by=None):
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
    conn = _get_conn()
    conn.execute(
        '''INSERT INTO users (username, password_hash, is_admin, created_by, email, invite_token, invite_token_expires, password_set)
           VALUES (?, '', ?, ?, ?, ?, ?, 0)''',
        (username, 1 if is_admin else 0, created_by, email, token, expires),
    )
    conn.commit()
    conn.close()
    return token


def get_user_by_token(token):
    conn = _get_conn()
    row = conn.execute('SELECT * FROM users WHERE invite_token = ?', (token,)).fetchone()
    conn.close()
    if not row:
        return None
    if row['invite_token_expires'] and datetime.fromisoformat(row['invite_token_expires']) < datetime.utcnow():
        return None
    return dict(row)


def set_password_by_token(token, password):
    conn = _get_conn()
    conn.execute(
        'UPDATE users SET password_hash = ?, password_set = 1, invite_token = NULL, invite_token_expires = NULL WHERE invite_token = ?',
        (generate_password_hash(password), token),
    )
    conn.commit()
    conn.close()


def generate_invite_token(user_id):
    token = secrets.token_urlsafe(32)
    expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
    conn = _get_conn()
    conn.execute(
        'UPDATE users SET invite_token = ?, invite_token_expires = ?, password_set = 0, password_hash = ? WHERE id = ?',
        (token, expires, '', user_id),
    )
    conn.commit()
    conn.close()
    return token


def update_password(user_id, new_password):
    conn = _get_conn()
    conn.execute(
        'UPDATE users SET password_hash = ?, password_set = 1 WHERE id = ?',
        (generate_password_hash(new_password), user_id),
    )
    conn.commit()
    conn.close()


def update_admin_status(user_id, is_admin):
    conn = _get_conn()
    conn.execute(
        'UPDATE users SET is_admin = ? WHERE id = ?',
        (1 if is_admin else 0, user_id),
    )
    conn.commit()
    conn.close()


def delete_user(user_id):
    conn = _get_conn()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()


def get_user_by_id(user_id):
    conn = _get_conn()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
