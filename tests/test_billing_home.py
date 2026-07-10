"""Tests for the Billing home page (GET /billing/)."""
import app as app_module
from billing.templates import render_billing_home_page
from ui.shell import page_shell


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_client():
    app_module.chatbot_app.config['TESTING'] = True
    app_module.chatbot_app.config['WTF_CSRF_ENABLED'] = False
    return app_module.chatbot_app.test_client()


def _login(c):
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['is_admin']  = True
        s['role']      = 'admin'


# ---------------------------------------------------------------------------
# Route tests
# ---------------------------------------------------------------------------

def test_billing_home_returns_200():
    client = _make_client()
    _login(client)
    resp = client.get('/billing/')
    assert resp.status_code == 200


def test_billing_home_requires_login():
    client = _make_client()
    resp = client.get('/billing/')
    # should redirect to login
    assert resp.status_code in (302, 301)


def test_billing_home_content():
    """Page must contain heading, all three style names, report slots, endpoints."""
    client = _make_client()
    _login(client)
    resp = client.get('/billing/')
    body = resp.data.decode('utf-8')

    # Page heading
    assert 'Billing' in body

    # Three selector style names
    assert 'Stepper' in body
    assert 'Quick Months' in body
    assert 'Calendar' in body

    # Report slot IDs
    assert 'id="tms-report"' in body
    assert 'id="osl-report"' in body

    # Generate endpoints referenced in JS
    assert '/billing/tms/generate' in body
    assert '/billing/osl/generate' in body

    # Checkbox markup
    assert 'id="bh-chk-tms"' in body
    assert 'id="bh-chk-osl"' in body


# ---------------------------------------------------------------------------
# Nav / page_shell test
# ---------------------------------------------------------------------------

def test_page_shell_includes_billing_nav_link():
    """page_shell(active='billing') must include href="/billing/"."""
    with app_module.chatbot_app.test_request_context('/billing/'):
        html = page_shell('<div></div>', active='billing')
    assert 'href="/billing/"' in html


# ---------------------------------------------------------------------------
# Template render smoke-test (no .format() brace guard)
# ---------------------------------------------------------------------------

def test_render_billing_home_page_does_not_raise():
    """render_billing_home_page() must return without raising (guards brace issues)."""
    with app_module.chatbot_app.test_request_context('/billing/'):
        result = render_billing_home_page()
    assert isinstance(result, str)
    assert len(result) > 500
