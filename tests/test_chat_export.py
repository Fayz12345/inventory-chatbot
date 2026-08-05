"""Tests for the chat results export endpoint (/ask/export): SELECT-only
re-validation, and CSV / XLSX output."""
import os
os.environ.setdefault("USERS_DB_PATH", "/tmp/test_users_chat.db")
os.environ.setdefault("CHAT_LOG_DB_PATH", "/tmp/test_chat_log.db")

import app

_CSRF = 'TESTTOKEN'
_CH = {'X-CSRF-Token': _CSRF}
SEL = "SELECT Manufacturer, ESN FROM ReportingInventoryFlat"


def _login(client):
    with client.session_transaction() as s:
        s['logged_in'] = True; s['username'] = 'tester'; s['is_admin'] = False
        s['csrf_token'] = _CSRF


class _FakeCursor:
    def __init__(self, cols, rows):
        self._rows = rows
        self.description = [(c,) for c in cols]
    def execute(self, sql): pass
    def fetchmany(self, n): return self._rows[:n]
    def close(self): pass


class _FakeConn:
    def __init__(self, cur): self._cur = cur
    def cursor(self): return self._cur
    def close(self): pass


def _patch_db(monkeypatch, cols, rows):
    monkeypatch.setattr(app, "get_db_connection", lambda: _FakeConn(_FakeCursor(cols, rows)))


def test_export_rejects_non_select(monkeypatch):
    _patch_db(monkeypatch, ['x'], [])
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask/export", json={"sql": "DROP TABLE ReportingInventoryFlat", "format": "csv"}, headers=_CH)
    assert r.status_code == 400 and 'not allowed' in r.get_json()['error'].lower()


def test_export_csv(monkeypatch):
    _patch_db(monkeypatch, ['Manufacturer', 'ESN'], [['Apple', '111'], ['Samsung', '222']])
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask/export", json={"sql": SEL, "format": "csv"}, headers=_CH)
    assert r.status_code == 200 and 'text/csv' in r.headers['Content-Type']
    body = r.data.decode('utf-8-sig')
    assert 'Manufacturer,ESN' in body and 'Apple,111' in body and 'Samsung,222' in body


def test_export_xlsx(monkeypatch):
    _patch_db(monkeypatch, ['Manufacturer', 'ESN'], [['Apple', '111']])
    client = app.chatbot_app.test_client(); _login(client)
    r = client.post("/ask/export", json={"sql": SEL, "format": "xlsx"}, headers=_CH)
    assert r.status_code == 200
    assert 'spreadsheetml' in r.headers['Content-Type']
    assert r.data[:2] == b'PK' and len(r.data) > 100     # .xlsx is a zip archive


def test_export_requires_auth():
    client = app.chatbot_app.test_client()
    r = client.post("/ask/export", json={"sql": SEL, "format": "csv"})
    assert r.status_code in (401, 403)                    # CSRF guard (403) or not-logged-in (401)
