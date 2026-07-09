"""Telemetry for the chat assistant: one row per /ask. Separate SQLite file so
it never contends with users.db. Path override via CHAT_LOG_DB_PATH (set it to a
persistent location in production, as with USERS_DB_PATH)."""
import os
import sqlite3

DB_PATH = os.environ.get('CHAT_LOG_DB_PATH') or os.path.join(os.path.dirname(__file__), 'chat_log.db')


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    c.execute('''CREATE TABLE IF NOT EXISTS chat_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        username TEXT,
        question TEXT NOT NULL,
        sql TEXT,
        ok INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        row_count INTEGER,
        retries INTEGER NOT NULL DEFAULT 0,
        latency_ms INTEGER,
        input_tokens INTEGER,
        output_tokens INTEGER
    )''')
    c.commit()
    c.close()


def log_query(*, username, question, sql=None, ok=False, error=None,
              row_count=None, retries=0, latency_ms=None,
              input_tokens=None, output_tokens=None):
    c = _conn()
    c.execute('''INSERT INTO chat_log
        (username, question, sql, ok, error, row_count, retries, latency_ms, input_tokens, output_tokens)
        VALUES (?,?,?,?,?,?,?,?,?,?)''',
              (username, question, sql, 1 if ok else 0, error, row_count,
               retries, latency_ms, input_tokens, output_tokens))
    c.commit()
    c.close()


def recent(limit=100):
    c = _conn()
    rows = c.execute('SELECT * FROM chat_log ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
