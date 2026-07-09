import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_csrf.db")
import app


def _admin(c):
    with c.session_transaction() as s:
        s['logged_in'] = True; s['username'] = 'Admin'; s['is_admin'] = True; s['role'] = 'admin'
        s['csrf_token'] = 'TESTTOKEN'


def test_post_without_token_is_403():
    c = app.chatbot_app.test_client(); _admin(c)
    r = c.post("/admin/users/set-role", json={"id": 1, "role": "viewer"})
    assert r.status_code == 403


def test_post_with_token_passes_csrf():
    c = app.chatbot_app.test_client(); _admin(c)
    r = c.post("/admin/users/set-role", json={"id": 999999, "role": "viewer"},
               headers={"X-CSRF-Token": "TESTTOKEN"})
    assert r.status_code != 403     # passes CSRF (may be ok:false for missing user)


def test_login_post_is_excluded():
    """Login POST (/) must not be CSRF-protected — no session token yet."""
    c = app.chatbot_app.test_client()
    r = c.post("/", data={"username": "noone", "password": "bad"})
    # Should NOT 403 — any other response (200 login page with error, redirect) is fine
    assert r.status_code != 403


def test_ask_without_token_is_403():
    c = app.chatbot_app.test_client(); _admin(c)
    r = c.post("/ask", json={"question": "how many devices?"})
    assert r.status_code == 403


def test_ask_with_token_passes_csrf(monkeypatch):
    import app as app_module

    class _Usage:
        input_tokens = 1
        output_tokens = 1

    monkeypatch.setattr(app_module, "generate_sql",
                        lambda msgs: ("SELECT ESN FROM ReportingInventoryFlat", _Usage()))
    monkeypatch.setattr(app_module, "run_query",
                        lambda sql: ({"columns": ["ESN"], "rows": [["X"]], "truncated": False}, None))
    monkeypatch.setattr(app_module, "format_answer", lambda *a, **k: "one device")

    c = app_module.chatbot_app.test_client(); _admin(c)
    r = c.post("/ask", json={"question": "how many?"},
               headers={"X-CSRF-Token": "TESTTOKEN"})
    assert r.status_code != 403
