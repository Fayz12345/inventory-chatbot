"""Tests for Telus Weekly ProjectTag and Client Name autocomplete (dropdown datalist)."""
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

def test_template_renders_project_tag_datalist():
    """render_telus_weekly_form with project_tags list must include datalist element."""
    tags = ['TW1626', 'TW1725', 'TW1825']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=tags)
    assert '<datalist id="projecttag-options">' in html


def test_template_renders_project_tag_options():
    """Each ProjectTag value must appear as a datalist option."""
    tags = ['TW1626', 'TW1725', 'TW1825']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=tags)
    for tag in tags:
        assert f'value="{tag}"' in html


def test_template_project_tag_input_has_list_attribute():
    """ProjectTag input must carry list="projecttag-options"."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=['TW1626'])
    assert 'list="projecttag-options"' in html


def test_template_renders_client_name_datalist():
    """render_telus_weekly_form with client_names list must include datalist element."""
    names = ['Telus', 'Bridge Wireless', 'OSL']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(client_names=names)
    assert '<datalist id="clientname-options">' in html


def test_template_renders_client_name_options():
    """Each client name must appear as a datalist option."""
    names = ['Telus', 'Bridge Wireless', 'OSL']
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(client_names=names)
    for name in names:
        assert f'value="{name}"' in html


def test_template_client_name_input_has_list_attribute():
    """Client Name input must carry list="clientname-options"."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(client_names=['Telus'])
    assert 'list="clientname-options"' in html


def test_template_empty_lists_still_renders():
    """Form renders without error when both lists are empty (plain inputs)."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form(project_tags=[], client_names=[])
    # datalist elements still present (empty), form submittable
    assert 'id="projecttag-options"' in html
    assert 'id="clientname-options"' in html
    assert 'name="project_tag"' in html
    assert 'name="client_name"' in html


def test_template_defaults_to_empty_lists():
    """render_telus_weekly_form() with no args must not raise."""
    with app_module.chatbot_app.test_request_context('/analytics/telus-weekly'):
        html = analytics_templates.render_telus_weekly_form()
    assert 'id="projecttag-options"' in html
    assert 'id="clientname-options"' in html


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


def test_route_get_contains_datalist(monkeypatch):
    """GET /analytics/telus-weekly response HTML contains datalist for both fields."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: ['TW1626', 'TW1725'])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: ['Telus', 'OSL'])

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    body = resp.data.decode('utf-8')

    assert '<datalist' in body
    assert 'id="projecttag-options"' in body
    assert 'id="clientname-options"' in body


def test_route_get_contains_option_values(monkeypatch):
    """GET /analytics/telus-weekly response contains the monkeypatched option values."""
    monkeypatch.setattr(analytics_db, 'get_telus_project_tags', lambda: ['TW1626', 'TW1725'])
    monkeypatch.setattr(analytics_db, 'get_telus_client_names', lambda: ['Telus', 'OSL'])

    client = _make_client()
    _login(client)
    resp = client.get('/analytics/telus-weekly')
    body = resp.data.decode('utf-8')

    assert 'value="TW1626"' in body
    assert 'value="TW1725"' in body
    assert 'value="Telus"' in body
    assert 'value="OSL"' in body


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
