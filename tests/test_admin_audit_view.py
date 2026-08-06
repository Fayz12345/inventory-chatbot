"""Tests for the rewritten /admin/audit UI: auth gating, filters, pagination,
the distinct-value dropdowns, and the XSS-safe detail rendering."""
import pytest
import admin_audit
import app as app_module


@pytest.fixture(autouse=True)
def fresh_audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_audit, "DB_PATH", str(tmp_path / "audit.db"))
    admin_audit.init_db()
    yield


def _admin(c):
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'Admin'
        s['is_admin'] = True
        s['role'] = 'admin'


def _seed_mixed(n=60):
    for i in range(n):
        actor = 'alice' if i % 2 == 0 else 'bob'
        action = 'view_home' if i % 3 == 0 else 'login'
        category = 'navigation' if action == 'view_home' else 'auth'
        admin_audit.log_request(actor=actor, action=action, target=None, detail={'i': i},
                                category=category, path='/home', method='GET', status=200, ip='1.1.1.1')


def test_anonymous_redirects():
    c = app_module.chatbot_app.test_client()
    r = c.get('/admin/audit')
    assert r.status_code == 302


def test_non_admin_redirects():
    c = app_module.chatbot_app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'x'
        s['is_admin'] = False
    r = c.get('/admin/audit')
    assert r.status_code == 302


def test_default_page_and_second_page():
    _seed_mixed(60)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit').get_data(as_text=True)
    assert '(60)' in html
    assert 'Page 1 of 2' in html
    html2 = c.get('/admin/audit?page=2').get_data(as_text=True)
    assert 'Page 2 of 2' in html2


def test_action_and_actor_filters_narrow_results():
    _seed_mixed(60)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    _, total_login = admin_audit.query(action='login', limit=1000)
    html = c.get('/admin/audit?action=login').get_data(as_text=True)
    assert f'({total_login})' in html

    _, total_alice = admin_audit.query(actor='alice', limit=1000)
    html2 = c.get('/admin/audit?actor=alice').get_data(as_text=True)
    assert f'({total_alice})' in html2


def test_combined_from_to_filters():
    admin_audit.log_request(actor='alice', action='login', target=None, detail=None,
                            category='auth', path='/', method='POST', status=200, ip='1.1.1.1')
    conn = admin_audit._conn()
    conn.execute("UPDATE admin_audit SET created_at='2026-03-05 12:00:00'")
    conn.commit()
    conn.close()
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit?from=2026-03-01&to=2026-03-10').get_data(as_text=True)
    assert '(1)' in html
    html_out = c.get('/admin/audit?from=2026-04-01&to=2026-04-10').get_data(as_text=True)
    assert '(0)' in html_out


def test_invalid_date_is_ignored():
    _seed_mixed(5)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit?from=not-a-date').get_data(as_text=True)
    assert '(5)' in html   # invalid 'from' silently dropped -> unfiltered


def test_invalid_page_defaults_to_1():
    _seed_mixed(5)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit?page=abc').get_data(as_text=True)
    assert 'Page 1 of 1' in html


def test_out_of_range_page_clamps_to_last_page():
    # 60 rows / AUDIT_PAGE_SIZE=50 -> 2 pages. page=999's offset would be far
    # past the last row (the first query returns empty) — the view must clamp
    # to the last real page and re-query with the corrected offset, not render
    # "Page 999 of 2" with an empty table.
    _seed_mixed(60)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit?page=999').get_data(as_text=True)
    assert 'Page 2 of 2' in html
    assert 'Page 999' not in html


def test_dropdowns_contain_seeded_distinct_values():
    _seed_mixed(6)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit').get_data(as_text=True)
    assert 'value="login"' in html
    assert 'value="view_home"' in html
    assert 'value="alice"' in html
    assert 'value="bob"' in html


def test_detail_data_attribute_present():
    _seed_mixed(3)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit').get_data(as_text=True)
    assert 'data-detail=' in html
    assert 'js-view' in html


def test_pagination_href_preserves_active_action_filter():
    for i in range(60):
        admin_audit.log_request(actor='alice', action='login', target=None, detail=None,
                                category='auth', path='/', method='POST', status=200, ip='1.1.1.1')
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit?action=login').get_data(as_text=True)
    assert 'Page 1 of 2' in html
    assert 'action=login&amp;page=2' in html


def test_xss_in_detail_is_entity_escaped():
    admin_audit.log_request(actor='eve', action='chat_ask', target=None,
                            detail={'question': '<script>alert(1)</script>'},
                            category='chat', path='/ask', method='POST', status=200, ip='9.9.9.9')
    c = app_module.chatbot_app.test_client()
    _admin(c)
    html = c.get('/admin/audit').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in html
    assert '&lt;script&gt;' in html
