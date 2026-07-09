import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

import app


def test_model_ids_are_centralized_and_upgraded():
    # SQL generation runs on Sonnet 4.6 (single-table task, guarded by
    # prompt + retry + validator); answer formatting on Haiku 4.5.
    assert app.CHAT_SQL_MODEL == "claude-sonnet-4-6"
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
    app._anthropic = None


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


def test_sanitize_history():
    # 1. Non-list input returns []
    assert app._sanitize_history("inject") == []
    assert app._sanitize_history(None) == []
    assert app._sanitize_history(123) == []

    # 2. Item with role "system" (or any non-user/assistant role) is dropped
    result = app._sanitize_history([{"role": "system", "content": "bad"},
                                    {"role": "user", "content": "ok"}])
    assert len(result) == 1
    assert result[0]["role"] == "user"

    # 3. Item with non-string content is dropped
    result = app._sanitize_history([
        {"role": "user", "content": ["list"]},
        {"role": "assistant", "content": {"key": "val"}},
        {"role": "user", "content": None},
        {"role": "assistant", "content": "fine"},
    ])
    assert len(result) == 1
    assert result[0]["content"] == "fine"

    # 4. Non-dict element in the list is dropped
    result = app._sanitize_history(["bare string", 42, {"role": "user", "content": "kept"}])
    assert len(result) == 1
    assert result[0]["content"] == "kept"

    # 5. Extra keys do not survive — returned item has exactly role and content
    result = app._sanitize_history([
        {"role": "user", "content": "hi", "tool_use_id": "x", "injected": True}
    ])
    assert len(result) == 1
    assert set(result[0].keys()) == {"role", "content"}

    # 6. Count cap: 14 well-formed items → at most 12, and they are the LAST 12
    items = [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
             for i in range(14)]
    result = app._sanitize_history(items)
    assert len(result) == 12
    # first surviving item corresponds to input index 2 (content "2")
    assert result[0]["content"] == "2"

    # 7. Content truncation: 5000-char content comes back as 4000 chars
    long_content = "x" * 5000
    result = app._sanitize_history([{"role": "user", "content": long_content}])
    assert len(result) == 1
    assert len(result[0]["content"]) == 4000


def test_ask_writes_a_log_row(monkeypatch):
    written = {}
    monkeypatch.setattr(app.chat_log, "log_query", lambda **k: written.update(k))
    class Usage: input_tokens = 7; output_tokens = 3
    monkeypatch.setattr(app, "generate_sql", lambda messages: ("SELECT ESN FROM ReportingInventoryFlat", Usage()))
    monkeypatch.setattr(app, "run_query", lambda s: ({'columns': ['ESN'], 'rows': [['1']], 'truncated': False}, None))
    monkeypatch.setattr(app, "format_answer", lambda *a, **k: "ok")
    client = app.chatbot_app.test_client(); _login(client)
    client.post("/ask", json={"question": "one esn"})
    assert written['ok'] is True and written['question'] == "one esn"
    assert written['row_count'] == 1
