"""Admin action audit trail — one row per meaningful request (navigation,
mutation, auth, chat). Stored in the users DB (USERS_DB_PATH) so it survives
with the accounts it describes. NOT the bridge SQL Server — this module never
touches it.

Handlers no longer write rows directly (see `log_action` — kept only for
back-compat). Instead they call `stash(...)` to enrich the pending request's
`flask.g.audit`, and the central `app.py` `after_request` hook composes the
final row and calls `log_request(...)` exactly once per request. `/ask/stream`
is the one exception: it stashes `skip=True` and calls `log_request` itself
once the NDJSON stream completes.

Everything here is best-effort: `stash`, `redact`, and `log_request` each
swallow their own exceptions so a bug in auditing can never break the request
it's trying to describe.
"""
import json
import os
import sqlite3

DB_PATH = os.environ.get('USERS_DB_PATH') or os.path.join(os.path.dirname(__file__), 'users.db')

_MAX_DETAIL_STR = 2000     # per-string cap inside redact()
_MAX_DETAIL_JSON = 8000    # cap on the serialized detail blob stored in the DB
_MAX_REDACT_DEPTH = 6


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def _column_exists(conn, table, column):
    cols = [r['name'] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    return column in cols


def init_db():
    c = _conn()
    try:
        c.execute('''CREATE TABLE IF NOT EXISTS admin_audit (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            actor      TEXT,
            action     TEXT NOT NULL,
            target     TEXT,
            detail     TEXT
        )''')
        # Guarded backfill (mirrors users_db.init_db()) so pre-existing DBs
        # gain the richer columns without losing their history.
        for col, typedef in [
            ('path',     'TEXT'),      # request.path ('/set-password/<token>' stored redacted)
            ('method',   'TEXT'),      # GET/POST/...
            ('category', 'TEXT'),      # 'navigation' | 'action' | 'chat' | 'auth'
            ('status',   'INTEGER'),   # HTTP status code of the response
            ('ip',       'TEXT'),      # client IP (first X-Forwarded-For entry, else remote_addr)
        ]:
            if not _column_exists(c, 'admin_audit', col):
                c.execute(f'ALTER TABLE admin_audit ADD COLUMN {col} {typedef}')
        c.execute('CREATE INDEX IF NOT EXISTS ix_admin_audit_created ON admin_audit (created_at)')
        c.execute('CREATE INDEX IF NOT EXISTS ix_admin_audit_action  ON admin_audit (action)')
        c.commit()
    finally:
        c.close()


def log_action(actor, action, target=None, detail=None):
    """Back-compat thin wrapper -> log_request(...) with null path/method/etc.
    Nothing in the app should call this anymore (use `stash` instead), but it
    stays for any external script / older test relying on the old signature."""
    log_request(actor=actor, action=action, target=target, detail=detail)


def recent(limit=200):
    c = _conn()
    try:
        rows = c.execute("SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# Substring match (covers prefixed/suffixed variants like new_password, csrf_token).
SENSITIVE_KEY_PARTS = ('password', 'passwd', 'pwd', 'secret', 'csrf', 'api_key', 'apikey',
                        'authorization', 'client_secret', 'access_token', 'refresh_token',
                        'invite_token')
# Exact match only — 'token' etc. would otherwise blow away legitimate fields
# like input_tokens/output_tokens/in_tok/out_tok/row_count (never redact counts).
# NOTE: 'new' is deliberately NOT here — the ubiquitous change-tracking shape
# used everywhere (changes={'field': {'old': .., 'new': ..}}) also keys its
# inner dict 'new', so blanket-redacting it in the default set would replace
# every audited old->new value (username/role/email/active/price changes, ...)
# with '[redacted]', defeating the audit trail. The raw-capture leak this used
# to enable (e.g. /profile/password's CSRF-rejected requests never reach the
# handler's `stash(..., note='password_change')` marker, since `_csrf_guard`
# 403s in before_request before the view runs — so the hook's generic
# body/args capture below would ship the raw {current, new} POST body) is
# closed by `redact_raw` below, used ONLY for that generic raw capture. Raw
# request params are never the changes={'f': {'old', 'new'}} shape, so nothing
# legitimate is lost by treating 'new'/'old' as sensitive there.
SENSITIVE_KEY_EXACT = ('token', 'auth', 'key', 'current', 'confirm')
SENSITIVE_KEY_EXACT_RAW = SENSITIVE_KEY_EXACT + ('new', 'old')
REDACTED = '[redacted]'


def _is_sensitive(key, exact=SENSITIVE_KEY_EXACT):
    k = str(key).lower()
    return any(p in k for p in SENSITIVE_KEY_PARTS) or k in exact


def _cap_str(s):
    return s if len(s) <= _MAX_DETAIL_STR else s[:_MAX_DETAIL_STR] + '...'


def _redact(value, depth, exact=SENSITIVE_KEY_EXACT):
    if depth >= _MAX_REDACT_DEPTH:
        if isinstance(value, str):
            return _cap_str(value)
        if isinstance(value, (dict, list, tuple)):
            return '[max-depth]'
        return value
    if isinstance(value, dict):
        return {k: (REDACTED if _is_sensitive(k, exact) else _redact(v, depth + 1, exact))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_redact(v, depth + 1, exact) for v in value]
    if isinstance(value, str):
        return _cap_str(value)
    return value


def redact(value, _depth=0):
    """Recursively replace values of sensitive keys with REDACTED; cap strings at
    2000 chars; max depth 6. Never raises — this is the safety net for whatever
    handlers stash, not the plan (never stash secrets in the first place)."""
    try:
        return _redact(value, _depth)
    except Exception:
        return '[unredactable]'


def redact_raw(value, _depth=0):
    """Stricter redact for RAW request params (the hook's generic body/args
    capture): also treats 'new'/'old' as sensitive. Raw params are never the
    changes={'f':{'old','new'}} shape, so nothing legitimate is lost. Never raises."""
    try:
        return _redact(value, _depth, SENSITIVE_KEY_EXACT_RAW)
    except Exception:
        return '[unredactable]'


# ---------------------------------------------------------------------------
# Per-request enrichment contract
# ---------------------------------------------------------------------------

def stash(action=None, target=None, category=None, actor=None, skip=None, **detail):
    """Merge per-handler enrichment onto flask.g.audit for the central hook to
    pick up in app.py's after_request. Call it any number of times per request
    (scalars overwrite — last wins; **detail kwargs merge via dict.update).
    Safe with no app/request context (imports flask.g lazily) and NEVER raises."""
    try:
        from flask import g
        audit = getattr(g, 'audit', None)
        if audit is None:
            audit = {'detail': {}}
            g.audit = audit
        elif 'detail' not in audit:
            audit['detail'] = {}
        if action is not None:
            audit['action'] = action
        if target is not None:
            audit['target'] = target
        if category is not None:
            audit['category'] = category
        if actor is not None:
            audit['actor'] = actor
        if skip is not None:
            audit['skip'] = skip
        if detail:
            audit['detail'].update(detail)
    except Exception:
        pass  # auditing must never break the request it's describing


def log_request(*, actor, action, target=None, detail=None, category=None,
                 path=None, method=None, status=None, ip=None):
    """INSERT one full audit row. detail: dict -> json.dumps(default=str), capped
    at 8000 chars; str -> stored as-is; None -> NULL. Never raises."""
    try:
        if isinstance(detail, str) or detail is None:
            detail_str = detail
        else:
            detail_str = json.dumps(detail, default=str)[:_MAX_DETAIL_JSON]
        c = _conn()
        try:
            c.execute(
                "INSERT INTO admin_audit (actor, action, target, detail, category, path, method, status, ip) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (actor, action, target, detail_str, category, path, method, status, ip))
            c.commit()
        finally:
            c.close()
    except Exception:
        pass  # audit must never break the action it records (incl. 'database is locked')


# ---------------------------------------------------------------------------
# Read side — the /admin/audit UI
# ---------------------------------------------------------------------------

def query(*, from_date=None, to_date=None, action=None, actor=None, category=None,
          limit=50, offset=0):
    """Filtered, paginated read. Returns (rows: list[dict], total: int).
    from_date/to_date: 'YYYY-MM-DD' strings, inclusive, compared against the
    UTC created_at column. action/actor/category: exact-match when truthy.
    All predicates are parameterized."""
    where = []
    params = []
    if from_date:
        where.append("created_at >= ?")
        params.append(from_date + ' 00:00:00')
    if to_date:
        where.append("created_at <= ?")
        params.append(to_date + ' 23:59:59')
    if action:
        where.append("action = ?")
        params.append(action)
    if actor:
        where.append("actor = ?")
        params.append(actor)
    if category:
        where.append("category = ?")
        params.append(category)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    c = _conn()
    try:
        total = c.execute(f"SELECT COUNT(*) as cnt FROM admin_audit{where_sql}", params).fetchone()['cnt']
        rows = c.execute(
            f"SELECT * FROM admin_audit{where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset]).fetchall()
        return [dict(r) for r in rows], total
    finally:
        c.close()


def distinct_actions():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT DISTINCT action FROM admin_audit WHERE action IS NOT NULL AND action <> '' "
            "ORDER BY action").fetchall()
        return [r['action'] for r in rows]
    finally:
        c.close()


def distinct_actors():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT DISTINCT actor FROM admin_audit WHERE actor IS NOT NULL AND actor <> '' "
            "ORDER BY actor COLLATE NOCASE").fetchall()
        return [r['actor'] for r in rows]
    finally:
        c.close()
