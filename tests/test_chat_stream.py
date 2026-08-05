"""Tests for the streaming chat endpoint (/ask/stream): the NDJSON event order
(stage -> meta -> delta -> done) and the friendly-error mapping (raw DB error is
logged, never sent to the client)."""
import json
import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

import app

_CSRF = 'TESTTOKEN'
_CH = {'X-CSRF-Token': _CSRF}


class _Usage:
    input_tokens = 1
    output_tokens = 1


def _login(client):
    with client.session_transaction() as s:
        s['logged_in'] = True; s['username'] = 'tester'; s['is_admin'] = False
        s['csrf_token'] = _CSRF


def _events(resp):
    return [json.loads(l) for l in resp.data.decode().splitlines() if l.strip()]


def test_stream_emits_stage_meta_delta_done(monkeypatch):
    monkeypatch.setattr(app, "generate_sql", lambda m: ("SELECT ESN FROM ReportingInventoryFlat", _Usage()))
    monkeypatch.setattr(app, "run_query",
                        lambda s: ({'columns': ['ESN'], 'rows': [['1'], ['2']], 'truncated': False}, None))
    monkeypatch.setattr(app, "format_answer_stream", lambda *a, **k: (t for t in ["Hel", "lo"]))
    monkeypatch.setattr(app.chat_log, "log_query", lambda **k: None)

    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask/stream", json={"question": "two esns"}, headers=_CH)
    assert r.status_code == 200
    events = _events(r)
    types = [e['type'] for e in events]
    assert 'stage' in types and 'meta' in types and 'delta' in types and types[-1] == 'done'

    meta = next(e for e in events if e['type'] == 'meta')
    assert meta['columns'] == ['ESN'] and len(meta['rows']) == 2
    answer = ''.join(e['text'] for e in events if e['type'] == 'delta')
    assert answer == 'Hello'


def test_stream_db_error_is_friendly_and_logged(monkeypatch):
    monkeypatch.setattr(app, "generate_sql", lambda m: ("SELECT bad", _Usage()))
    monkeypatch.setattr(app, "run_query", lambda s: (None, "Invalid column name 'bad'."))
    logged = {}
    monkeypatch.setattr(app.chat_log, "log_query", lambda **k: logged.update(k))

    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask/stream", json={"question": "bad q"}, headers=_CH)
    events = _events(r)
    final = next(e for e in events if e['type'] == 'final')
    assert final['answer'] == app.FRIENDLY_ERROR                 # friendly, not the raw error
    assert 'Invalid column name' not in r.data.decode()          # raw error never leaves the server
    assert logged.get('error') == "Invalid column name 'bad'."   # ...but it IS logged
    assert logged.get('ok') is False


def test_stream_requires_auth():
    client = app.chatbot_app.test_client()
    r = client.post("/ask/stream", json={"question": "x"})
    assert r.status_code in (401, 403)
