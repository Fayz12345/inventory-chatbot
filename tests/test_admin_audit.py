import sqlite3

import pytest
import admin_audit


@pytest.fixture(autouse=True)
def fresh_audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_audit, "DB_PATH", str(tmp_path / "users.db"))
    admin_audit.init_db()
    yield


def test_log_and_recent():
    admin_audit.log_action("admin", "delete_user", target="bob", detail="id=3")
    admin_audit.log_action("admin", "set_role", target="alice", detail="viewer->admin")
    rows = admin_audit.recent(10)
    assert rows[0]["action"] == "set_role" and rows[0]["actor"] == "admin"
    assert any(r["action"] == "delete_user" and r["target"] == "bob" for r in rows)


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def test_migration_adds_columns_and_is_idempotent(tmp_path, monkeypatch):
    db_path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(admin_audit, "DB_PATH", db_path)

    # Hand-create the legacy 5-column table (pre-migration shape).
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE admin_audit (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL DEFAULT (datetime('now')),
        actor      TEXT,
        action     TEXT NOT NULL,
        target     TEXT,
        detail     TEXT
    )''')
    conn.commit()
    conn.close()

    admin_audit.init_db()
    admin_audit.init_db()  # idempotent — must not raise or duplicate columns

    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(admin_audit)").fetchall()}
    conn.close()
    for c in ('path', 'method', 'category', 'status', 'ip'):
        assert c in cols

    admin_audit.log_request(actor="admin", action="view_home", target=None, detail={"a": 1},
                            category="navigation", path="/home", method="GET", status=200, ip="1.2.3.4")
    rows = admin_audit.recent(10)
    assert rows[0]["path"] == "/home"
    assert rows[0]["method"] == "GET"
    assert rows[0]["category"] == "navigation"
    assert rows[0]["status"] == 200
    assert rows[0]["ip"] == "1.2.3.4"


def test_log_action_backcompat():
    admin_audit.log_action("Admin", "delete_user", target="bob", detail="id=3")
    rows, total = admin_audit.query(limit=10)
    assert total == 1
    assert rows[0]["actor"] == "Admin"
    assert rows[0]["action"] == "delete_user"
    assert rows[0]["target"] == "bob"
    assert rows[0]["detail"] == "id=3"
    # log_action never populated the new columns
    assert rows[0]["path"] is None
    assert rows[0]["category"] is None


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact():
    payload = {
        "password": "hunter2",
        "csrf_token": "abc",
        "api_key": "sk-xxx",
        "client_secret": "shh",
        "token": "tok-value",
        "current": "oldpw",
        "confirm": "newpw",
        "nested": {"password": "inner-secret", "ok": True},
        "items": [{"password": "list-secret"}, {"fine": "value"}],
        "input_tokens": 123,
        "output_tokens": 45,
        "in_tok": 7,
        "out_tok": 8,
        "row_count": 42,
        # the ubiquitous change-tracking shape — 'new' must NOT be treated as
        # sensitive here, or every audited old->new value would come back
        # '[redacted]' (see admin_audit.SENSITIVE_KEY_EXACT's note on 'new').
        "changes": {"role": {"old": "user", "new": "admin"}},
    }
    out = admin_audit.redact(payload)
    for k in ("password", "csrf_token", "api_key", "client_secret", "token", "current", "confirm"):
        assert out[k] == admin_audit.REDACTED
    assert out["nested"]["password"] == admin_audit.REDACTED
    assert out["nested"]["ok"] is True
    assert out["items"][0]["password"] == admin_audit.REDACTED
    assert out["items"][1]["fine"] == "value"
    # token-count fields must survive untouched
    assert out["input_tokens"] == 123
    assert out["output_tokens"] == 45
    assert out["in_tok"] == 7
    assert out["out_tok"] == 8
    assert out["row_count"] == 42
    assert out["changes"]["role"] == {"old": "user", "new": "admin"}


def test_redact_caps_long_strings():
    long_str = "x" * 3000
    out = admin_audit.redact({"question": long_str})
    assert len(out["question"]) <= len(admin_audit._cap_str(long_str))
    assert out["question"].endswith("...")
    assert len(out["question"]) < 3000


def test_redact_never_raises_on_weird_input():
    assert admin_audit.redact("plain string") == "plain string"
    assert admin_audit.redact(123) == 123
    assert admin_audit.redact(None) is None
    admin_audit.redact(object())  # non-container, non-scalar — must not raise

    # deep recursion — must stop at max depth, never blow the stack / raise
    deep = {}
    cur = deep
    for i in range(50):
        cur['password'] = {}
        cur = cur['password']
    cur['leaf'] = 'value'
    out = admin_audit.redact(deep)  # no exception
    assert out is not None


def test_redact_raw_scrubs_new_and_old_plus_existing_sensitive_keys():
    # redact_raw is the stricter variant used ONLY for the audit hook's generic
    # raw request-param capture (app.py's _audit_log), where 'new'/'old' can
    # never legitimately be a changes={'f': {'old','new'}} diff key.
    payload = {
        "new": "brand-new-secret",
        "old": "prior-secret",
        "current": "current-secret",
        "confirm": "confirm-secret",
        "password": "hunter2",
        "fine": "value",
    }
    out = admin_audit.redact_raw(payload)
    for k in ("new", "old", "current", "confirm", "password"):
        assert out[k] == admin_audit.REDACTED
    assert out["fine"] == "value"


def test_redact_raw_never_raises():
    assert admin_audit.redact_raw(object()) is not None
    assert admin_audit.redact_raw(None) is None
    assert admin_audit.redact_raw("plain string") == "plain string"


def test_redact_still_preserves_changes_diff_new_old_unredacted():
    # Regression guard, mirrors the 'changes' assertion inside test_redact()
    # above: the DEFAULT redact() (used for stashed `changes={...}` diffs) must
    # never treat 'new'/'old' as sensitive — only redact_raw() does that.
    out = admin_audit.redact({"changes": {"role": {"old": "user", "new": "admin"}}})
    assert out["changes"]["role"] == {"old": "user", "new": "admin"}


# ---------------------------------------------------------------------------
# stash() outside a request context
# ---------------------------------------------------------------------------

def test_stash_outside_request_context_is_noop():
    # No Flask app/request context is active here — must not raise.
    admin_audit.stash(action='whatever', target='x', extra=1)


# ---------------------------------------------------------------------------
# query() filters + pagination
# ---------------------------------------------------------------------------

def _seed_rows():
    admin_audit.log_request(actor="alice", action="login", target="alice", detail=None,
                            category="auth", path="/", method="POST", status=200, ip="1.1.1.1")
    admin_audit.log_request(actor="bob", action="view_home", target=None, detail=None,
                            category="navigation", path="/home", method="GET", status=200, ip="1.1.1.2")
    admin_audit.log_request(actor="alice", action="delete_user", target="carol", detail=None,
                            category="action", path="/admin/users/delete", method="POST",
                            status=200, ip="1.1.1.1")
    admin_audit.log_request(actor="bob", action="view_home", target=None, detail=None,
                            category="navigation", path="/home", method="GET", status=200, ip="1.1.1.2")
    # backdate created_at for date-filter assertions
    conn = admin_audit._conn()
    conn.execute("UPDATE admin_audit SET created_at = '2026-01-01 10:00:00' WHERE id = 1")
    conn.execute("UPDATE admin_audit SET created_at = '2026-01-15 10:00:00' WHERE id = 2")
    conn.execute("UPDATE admin_audit SET created_at = '2026-02-01 10:00:00' WHERE id = 3")
    conn.execute("UPDATE admin_audit SET created_at = '2026-02-15 10:00:00' WHERE id = 4")
    conn.commit()
    conn.close()


def test_query_filters_and_pagination():
    _seed_rows()

    rows, total = admin_audit.query(limit=50)
    assert total == 4
    # id-DESC ordering
    assert [r['id'] for r in rows] == [4, 3, 2, 1]

    rows, total = admin_audit.query(from_date='2026-01-10', to_date='2026-01-31', limit=50)
    assert total == 1 and rows[0]['id'] == 2

    rows, total = admin_audit.query(action='view_home', limit=50)
    assert total == 2
    assert all(r['action'] == 'view_home' for r in rows)

    rows, total = admin_audit.query(actor='alice', limit=50)
    assert total == 2
    assert all(r['actor'] == 'alice' for r in rows)

    rows, total = admin_audit.query(actor='alice', action='delete_user', limit=50)
    assert total == 1 and rows[0]['id'] == 3

    # limit/offset paging; total stays independent of limit
    rows, total = admin_audit.query(limit=2, offset=0)
    assert total == 4 and len(rows) == 2 and [r['id'] for r in rows] == [4, 3]
    rows2, total2 = admin_audit.query(limit=2, offset=2)
    assert total2 == 4 and len(rows2) == 2 and [r['id'] for r in rows2] == [2, 1]


def test_distinct_actions_and_actors():
    _seed_rows()
    actions = admin_audit.distinct_actions()
    assert actions == ['delete_user', 'login', 'view_home']  # sorted, de-duped

    actors = admin_audit.distinct_actors()
    assert actors == ['alice', 'bob']  # sorted, de-duped, no None/empty
    assert None not in actors and '' not in actors
