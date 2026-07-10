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
    # --- LiteLLM multi-provider config + shared per-call usage ledger ---
    # Mirrors the tables created on the bridge SQL Server, kept here so the app
    # can run fully on local SQLite (keeps chat's bridge access read-only).
    c.execute('''CREATE TABLE IF NOT EXISTS llm_provider (
        provider     TEXT PRIMARY KEY,            -- 'gemini' | 'anthropic' | 'openai'
        api_key_enc  TEXT NOT NULL,               -- ENCRYPTED at rest (never plaintext)
        enabled      INTEGER NOT NULL DEFAULT 1,
        updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS llm_task_model (
        task               TEXT PRIMARY KEY,       -- 'chat_sql' | 'chat_answer' | 'scrape_extract'
        provider           TEXT NOT NULL,
        model_id           TEXT NOT NULL,
        fallback_provider  TEXT,
        fallback_model     TEXT,
        monthly_budget_usd REAL,
        enabled            INTEGER NOT NULL DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS llm_call_log (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at     TEXT NOT NULL DEFAULT (datetime('now')),
        feature        TEXT NOT NULL,              -- 'chat' | 'scrape'
        task           TEXT NOT NULL,              -- 'chat_sql' | 'chat_answer' | 'scrape_extract'
        provider       TEXT,
        model          TEXT,
        input_tokens   INTEGER,
        output_tokens  INTEGER,
        cost_usd       REAL,                       -- straight from LiteLLM response_cost
        latency_ms     INTEGER,
        ok             INTEGER,
        ref_id         TEXT                        -- chat question id / scrape-job id
    )''')
    c.execute('''CREATE INDEX IF NOT EXISTS ix_llm_call_log_created
        ON llm_call_log (created_at, feature, task)''')
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
