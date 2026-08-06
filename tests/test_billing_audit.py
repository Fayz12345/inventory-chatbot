"""Tests that the TMS/OSL generate + raw-download + flat routes enrich the
admin audit trail via admin_audit.stash(...) (the central app.py hook writes
the actual row; these tests verify the blueprint's stash calls, per the
Phase 1B audit design). Patches billing.routes.admin_audit.stash directly so
no real DB/audit write is needed. Mirrors the client/login fixture in
test_billing_flat.py.
"""
from unittest.mock import patch

import pytest

import app as app_module
from billing import routes as billing_routes, tms, osl


@pytest.fixture
def client():
    app_module.chatbot_app.config['TESTING'] = True
    app_module.chatbot_app.config['WTF_CSRF_ENABLED'] = False
    return app_module.chatbot_app.test_client()


def _login(c):
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['is_admin'] = True
        s['role'] = 'admin'


def _merged_stash_kwargs(mock_stash):
    merged = {}
    for call in mock_stash.call_args_list:
        merged.update(call.kwargs)
    return merged


# ---------------------------------------------------------------------------
# tms_generate / osl_generate
# ---------------------------------------------------------------------------

@patch("billing.routes.admin_audit.stash")
@patch("billing.routes.tms.generate_report", return_value={'rows': []})
def test_tms_generate_stashes_year_month_target(mock_gen, mock_stash, client):
    _login(client)
    r = client.post('/billing/tms/generate', json={'year': 2026, 'month': 3})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "tms_report"
    assert detail["target"] == "2026-03"


@patch("billing.routes.admin_audit.stash")
@patch("billing.routes.osl.generate", return_value={'report': {}, 'models': []})
def test_osl_generate_stashes_year_month_target_and_overrides(mock_gen, mock_stash, client):
    _login(client)
    overrides = [{'model': 'iPhone 14', 'grade': 'A'}, {'model': 'iPhone 15', 'grade': 'B'}]
    r = client.post('/billing/osl/generate',
                    json={'year': 2026, 'month': 4, 'overrides': overrides})
    assert r.status_code == 200 and r.get_json()['ok'] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "osl_report"
    assert detail["target"] == "2026-04"
    assert detail["overrides"] == 2


# ---------------------------------------------------------------------------
# raw downloads
# ---------------------------------------------------------------------------

@patch("billing.routes.admin_audit.stash")
@patch("billing.routes.export.rows_to_xlsx", return_value=b"xlsx-bytes")
@patch("billing.routes.tms.get_raw_rows", return_value=(['ESN'], [['1']]))
def test_tms_raw_download_stashes_action_and_target(mock_rows, mock_xlsx, mock_stash, client):
    _login(client)
    r = client.get('/billing/tms/raw?year=2026&month=5')
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "tms_raw_download"
    assert detail["category"] == "action"
    assert detail["target"] == "2026-05"


@patch("billing.routes.admin_audit.stash")
@patch("billing.routes.export.rows_to_xlsx", return_value=b"xlsx-bytes")
@patch("billing.routes.osl.get_raw_rows", return_value=(['ESN'], [['1']]))
def test_osl_raw_download_stashes_action_and_target(mock_rows, mock_xlsx, mock_stash, client):
    _login(client)
    r = client.get('/billing/osl/raw?year=2026&month=6')
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "osl_raw_download"
    assert detail["category"] == "action"
    assert detail["target"] == "2026-06"


# ---------------------------------------------------------------------------
# tms_flat
# ---------------------------------------------------------------------------

@patch("billing.routes.admin_audit.stash")
def test_tms_flat_stashes_target(mock_stash, client, monkeypatch):
    monkeypatch.setattr(tms, 'get_raw_rows', lambda y, m: (['ESN'], [['1']]))
    _login(client)
    r = client.get('/billing/tms/flat?year=2026&month=7')
    assert r.status_code == 200
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["target"] == "2026-07"
