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


class _Usage:
    input_tokens = 1
    output_tokens = 1


def test_ask_reports_truncation(monkeypatch):
    def fake_generate(messages):
        return ("SELECT ESN FROM ReportingInventoryFlat", _Usage())
    monkeypatch.setattr(app, "generate_sql", fake_generate)
    big = {'columns': ['ESN'], 'rows': [[i] for i in range(50)], 'truncated': True}
    monkeypatch.setattr(app, "run_query", lambda sql: (big, None))
    monkeypatch.setattr(app, "run_query_raw", lambda sql: ({'columns': ['n'], 'rows': [[1234]]}, None))
    monkeypatch.setattr(app, "format_answer", lambda *a, **k: "sample answer")
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask", json={"question": "list devices"})
    body = r.get_json()
    assert body['truncated'] is True and body['total_rows'] == 1234


def test_ask_retries_on_bad_sql_then_succeeds(monkeypatch):
    calls = {"n": 0}
    class Usage:  # minimal stand-in for anthropic usage object
        input_tokens = 10; output_tokens = 5
    def fake_generate(messages):
        calls["n"] += 1
        return ("SELECT bad" if calls["n"] == 1 else "SELECT ESN FROM ReportingInventoryFlat", Usage())
    def fake_run(sql):
        if sql == "SELECT bad":
            return (None, "Invalid column name 'bad'.")
        return ({'columns': ['ESN'], 'rows': [['123']], 'truncated': False}, None)
    monkeypatch.setattr(app, "generate_sql", fake_generate)
    monkeypatch.setattr(app, "run_query", fake_run)
    monkeypatch.setattr(app, "format_answer", lambda *a, **k: "ok")
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask", json={"question": "list an esn"})
    assert r.get_json()['answer'] == "ok"
    assert calls["n"] == 2   # retried exactly once after the failure


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


def test_ask_threads_history_into_generation(monkeypatch):
    seen = {}
    class Usage: input_tokens = 1; output_tokens = 1
    def fake_generate(messages):
        seen['messages'] = messages
        return ("SELECT ESN FROM ReportingInventoryFlat", Usage())
    monkeypatch.setattr(app, "generate_sql", fake_generate)
    monkeypatch.setattr(app, "run_query", lambda s: ({'columns': ['ESN'], 'rows': [['1']], 'truncated': False}, None))
    monkeypatch.setattr(app, "format_answer", lambda *a, **k: "ok")
    client = app.chatbot_app.test_client(); _login(client)
    history = [{"role": "user", "content": "how many Apple?"},
               {"role": "assistant", "content": "1,240."}]
    client.post("/ask", json={"question": "what about Samsung?", "history": history})
    roles = [m['role'] for m in seen['messages']]
    # history (user, assistant) then the current user question
    assert roles == ["user", "assistant", "user"]
    assert seen['messages'][-1]['content'] == "what about Samsung?"
