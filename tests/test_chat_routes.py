import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

import app


def test_model_ids_are_centralized_and_upgraded():
    assert app.CHAT_SQL_MODEL == "claude-opus-4-8"
    assert app.CHAT_ANSWER_MODEL == "claude-haiku-4-5-20251001"
    # no legacy id left hardcoded in the module source
    import inspect
    src = inspect.getsource(app)
    assert "claude-opus-4-6" not in src


def _login(client):
    with client.session_transaction() as s:
        s['logged_in'] = True; s['username'] = 'tester'; s['is_admin'] = False


def test_ask_reports_truncation(monkeypatch):
    monkeypatch.setattr(app, "generate_sql", lambda q: "SELECT ESN FROM ReportingInventoryFlat")
    big = {'columns': ['ESN'], 'rows': [[i] for i in range(50)], 'truncated': True}
    monkeypatch.setattr(app, "run_query", lambda sql: (big, None))
    monkeypatch.setattr(app, "run_query_raw", lambda sql: ({'columns': ['n'], 'rows': [[1234]]}, None))
    monkeypatch.setattr(app, "format_answer", lambda *a, **k: "sample answer")
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask", json={"question": "list devices"})
    body = r.get_json()
    assert body['truncated'] is True and body['total_rows'] == 1234


def test_anthropic_client_is_shared_singleton(monkeypatch):
    made = []
    class Fake:
        def __init__(self, **kw): made.append(kw)
    monkeypatch.setattr(app.anthropic, "Anthropic", Fake)
    app._anthropic = None  # reset memo
    c1 = app._anthropic_client()
    c2 = app._anthropic_client()
    assert c1 is c2
    assert len(made) == 1
    assert made[0].get("timeout") == 30 and made[0].get("max_retries") == 2
