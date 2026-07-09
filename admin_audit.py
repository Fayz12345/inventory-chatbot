"""Admin action audit trail — one row per state-changing admin action. Stored in
the users DB (USERS_DB_PATH) so it survives with the accounts it describes."""
import os
import sqlite3

DB_PATH = os.environ.get('USERS_DB_PATH') or os.path.join(os.path.dirname(__file__), 'users.db')


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = _conn()
    c.execute('''CREATE TABLE IF NOT EXISTS admin_audit (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        actor      TEXT,
        action     TEXT NOT NULL,
        target     TEXT,
        detail     TEXT
    )''')
    c.commit(); c.close()


def log_action(actor, action, target=None, detail=None):
    try:
        c = _conn()
        c.execute("INSERT INTO admin_audit (actor, action, target, detail) VALUES (?,?,?,?)",
                  (actor, action, target, detail))
        c.commit(); c.close()
    except Exception:
        pass  # audit must never break the action it records


def recent(limit=200):
    c = _conn()
    rows = c.execute("SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    c.close()
    return [dict(r) for r in rows]
