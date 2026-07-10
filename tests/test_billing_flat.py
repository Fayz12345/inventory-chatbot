import datetime
import decimal
import json

import pytest

import app as app_module
from billing import routes as billing_routes, templates, schedule, tms


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


def test_flat_route_requires_login(client):
    resp = client.get('/billing/tms/flat?year=2026&month=3')
    assert resp.status_code == 401


def test_flat_route_bad_params(client):
    _login(client)
    resp = client.get('/billing/tms/flat?year=abc&month=3')
    assert resp.status_code == 400


def test_flat_route_serializes_datetime_and_decimal(client, monkeypatch):
    cols = ['ESN', 'ReceiveDate', 'Repair_Fee']
    rows = [
        ['355', datetime.datetime(2026, 3, 5, 9, 30), decimal.Decimal('12.50')],
        ['356', None, None],
    ]
    monkeypatch.setattr(tms, 'get_raw_rows', lambda y, m: (cols, rows))
    _login(client)
    resp = client.get('/billing/tms/flat?year=2026&month=3')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['ok'] is True
    assert data['columns'] == cols
    assert data['total'] == 2
    assert data['truncated'] is False
    assert data['rows'][0][1] == '2026-03-05 09:30:00'
    assert data['rows'][0][2] == 12.5
    assert data['rows'][1][1] is None


def test_flat_route_caps_rows(client, monkeypatch):
    cols = ['ESN']
    rows = [[str(i)] for i in range(billing_routes.FLAT_ROW_CAP + 50)]
    monkeypatch.setattr(tms, 'get_raw_rows', lambda y, m: (cols, rows))
    _login(client)
    resp = client.get('/billing/tms/flat?year=2026&month=3')
    data = resp.get_json()
    assert data['total'] == billing_routes.FLAT_ROW_CAP + 50
    assert len(data['rows']) == billing_routes.FLAT_ROW_CAP
    assert data['truncated'] is True


def test_tms_template_formats_without_brace_errors():
    # Guards against unescaped { } in the added JS breaking str.format().
    body = templates._BILLING_PAGE_TEMPLATE.format(
        title="TMS Billing Report",
        endpoint="/billing/tms/generate",
        raw_endpoint="/billing/tms/raw",
        csv_prefix="TMS_Billing_",
        schedule_json=json.dumps(schedule.TMS_FEE_SCHEDULE),
    )
    assert 'Flat Table Data' in body
    assert 'id="tab-flat"' in body
    assert '/billing/tms/flat' in body
