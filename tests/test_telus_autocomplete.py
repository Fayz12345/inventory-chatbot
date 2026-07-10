"""Tests for Telus Weekly ProjectTag and Client Name custom autocomplete combobox."""
import app as app_module
from analytics import db as analytics_db, templates as analytics_templates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_client():
    app_module.chatbot_app.config['TESTING'] = True
    app_module.chatbot_app.config['WTF_CSRF_ENABLED'] = False
    return app_module.chatbot_app.test_client()


def _login(c):
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['is_admin'] = True
        s['role'] = 'admin'


# ---------------------------------------------------------------------------
# Template unit tests — no DB, no route layer
# ---------------------------------------------------------------------------

def test_template_renders_combobox_container():
    """render_telus_weekly_form must include combobox wrapper and listbox panel."""
    tags = ['TW1626', 'TW1725', 'TW1825']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=tags)
    assert 'role="combobox"' in html
    assert 'role="listbox"' in html
    # Both combobox wrap containers present
    assert 'id="pt-wrap"' in html
    assert 'id="cn-wrap"' in html


def test_option_values_are_script_safe():
    """DB-sourced option values are embedded in an inline <script>; a value
    containing </script> must not break out of the script block (stored-XSS)."""
    payload = '</script><script>alert(1)</script>'
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(
            project_tags=[payload], client_names=['A & B'])
    # No live breakout — the raw injected script tag must not appear.
    assert '<script>alert(1)' not in html
    # The value is still embedded, just unicode-escaped.
    assert 'alert(1)' in html
    assert '\\u003c' in html


def test_template_no_datalist():
    """Custom combobox must NOT use native <datalist> elements."""
    tags = ['TW1626', 'TW1725', 'TW1825']
    names = ['Telus', 'OSL']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(
            project_tags=tags, client_names=names
        )
    assert '<datalist' not in html


def test_template_project_tag_options_in_js():
    """ProjectTag option values must appear in the embedded JS options array."""
    tags = ['TW1626', 'TW1725', 'TW1825']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=tags)
    # Values are JSON-serialised into PROJECTTAG_OPTIONS = [...]
    assert 'PROJECTTAG_OPTIONS' in html
    for tag in tags:
        assert tag in html


def test_template_client_name_options_in_js():
    """Client name option values must appear in the embedded JS options array."""
    names = ['Telus', 'Bridge Wireless', 'OSL']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(client_names=names)
    assert 'CLIENTNAME_OPTIONS' in html
    for name in names:
        assert name in html


def test_template_aria_attributes_present():
    """Combobox inputs must carry ARIA attributes for accessibility."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(
            project_tags=['TW1626'], client_names=['Telus']
        )
    assert 'aria-autocomplete="list"' in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="pt-panel"' in html
    assert 'aria-controls="cn-panel"' in html


def test_template_listbox_panels_present():
    """Both listbox panels must be rendered in the HTML."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(
            project_tags=['TW1626'], client_names=['Telus']
        )
    assert 'id="pt-panel"' in html
    assert 'id="cn-panel"' in html


def test_template_empty_lists_still_renders():
    """Form renders without error when both lists are empty."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=[], client_names=[])
    assert 'name="project_tag"' in html
    assert 'name="client_name"' in html
    assert 'role="combobox"' in html
    assert '<datalist' not in html


def test_template_defaults_to_empty_lists():
    """render_telus_weekly_form() with no args must not raise."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form()
    assert 'name="project_tag"' in html
    assert 'name="client_name"' in html


# ---------------------------------------------------------------------------
# Route tests — monkeypatched DB, no live DB hit
# ---------------------------------------------------------------------------

def test_route_get_returns_200(monkeypatch):
    """GET /analytics/telus-weekly returns 200 when DB functions are monkeypatched."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: ['TW1626', 'TW1725'])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: ['Telus', 'OSL'])

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    assert resp.status_code == 200


def test_route_get_contains_combobox(monkeypatch):
    """GET /analytics/telus-weekly response HTML contains combobox markup."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: ['TW1626', 'TW1725'])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: ['Telus', 'OSL'])

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    body = resp.data.decode('utf-8')

    assert 'role="combobox"' in body
    assert 'role="listbox"' in body
    assert 'id="pt-panel"' in body
    assert 'id="cn-panel"' in body
    assert '<datalist' not in body


def test_route_get_contains_option_values(monkeypatch):
    """GET /analytics/telus-weekly response contains the monkeypatched option values."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: ['TW1626', 'TW1725'])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: ['Telus', 'OSL'])

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    body = resp.data.decode('utf-8')

    # Values appear inside the embedded JS arrays
    assert 'TW1626' in body
    assert 'TW1725' in body
    assert 'Telus' in body
    assert 'OSL' in body


def test_route_get_requires_login(monkeypatch):
    """GET /analytics/telus-weekly without login redirects."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: [])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: [])

    client = _make_client()
    resp = client.get('/analytics/telus-weekly')
    assert resp.status_code in (301, 302)


def test_route_get_db_error_degrades_gracefully(monkeypatch):
    """GET /analytics/telus-weekly still returns 200 when DB functions raise."""
    def _raise():
        raise RuntimeError('DB offline')

    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', _raise)
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', _raise)

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    assert resp.status_code == 200
    body = resp.data.decode('utf-8')
    # Form must still be present
    assert 'name="project_tag"' in body
