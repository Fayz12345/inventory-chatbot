"""Tests for the central @chatbot_app.after_request audit hook in app.py: one
row per request, the skip list, the endpoint->(action,category) map, the
edit_user duplicate-row fix, auth stashes, CSRF-rejected logging, and the
best-effort guarantee (a broken admin_audit.log_request must never break the
underlying request).

Fixture mirrors test_admin_users_routes.py:7-14 — monkeypatch users_db.DB_PATH
and admin_audit.DB_PATH to a shared tmp SQLite file, init both.
"""
import json
import os

from werkzeug.security import generate_password_hash as _gen_hash

import pytest
import users_db
import admin_audit
import app as app_module


@pytest.fixture(autouse=True)
def fresh_dbs(tmp_path, monkeypatch):
    db_path = str(tmp_path / "users.db")
    monkeypatch.setattr(users_db, "DB_PATH", db_path)
    monkeypatch.setattr(admin_audit, "DB_PATH", db_path)
    # Python 3.9 on macOS lacks hashlib.scrypt (werkzeug's default) — force pbkdf2.
    monkeypatch.setattr(users_db, "generate_password_hash",
                        lambda pw, **kw: _gen_hash(pw, method="pbkdf2:sha256"))
    users_db.init_db()
    admin_audit.init_db()
    yield


_CSRF = 'TESTTOKEN'


def _ch():
    return {'X-CSRF-Token': _CSRF}


def _admin(c, username='Admin'):
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = username
        s['is_admin'] = True
        s['role'] = 'admin'
        s['csrf_token'] = _CSRF


def _make_user(name, role='user'):
    users_db.create_user(name, name + "@x.com", created_by="t", role=role)
    return users_db._row_by_username(name)["id"]


def _all_rows():
    return admin_audit.query(limit=1000)[0]


# ---------------------------------------------------------------------------

def test_navigation_get_logs_one_row():
    c = app_module.chatbot_app.test_client()
    _admin(c)
    r = c.get('/home')
    assert r.status_code == 200
    rows = _all_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row['action'] == 'view_home'
    assert row['category'] == 'navigation'
    assert row['method'] == 'GET'
    assert row['path'] == '/home'
    assert row['status'] == 200
    assert row['actor'] == 'Admin'
    assert row['ip']


def test_skip_list():
    c = app_module.chatbot_app.test_client()
    _admin(c)
    c.get('/favicon.ico')
    c.get('/static/css/app.css')
    c.get('/admin/audit')
    c.get('/privacy')
    c_anon = app_module.chatbot_app.test_client()
    c_anon.get('/')
    assert _all_rows() == []


def test_anonymous_not_logged():
    c = app_module.chatbot_app.test_client()
    r = c.get('/home')          # not logged in -> redirected to login
    assert r.status_code == 302
    assert _all_rows() == []


def test_mutation_logs_single_row_with_detail(monkeypatch):
    monkeypatch.setattr(app_module, 'send_invite_email', lambda *a, **k: None)
    c = app_module.chatbot_app.test_client()
    _admin(c)
    r = c.post('/admin/users/create',
               json={'username': 'newbie', 'email': 'newbie@x.com', 'is_admin': False},
               headers=_ch())
    assert r.get_json()['ok'] is True
    rows = _all_rows()
    assert len(rows) == 1                      # exactly ONE row
    row = rows[0]
    assert row['action'] == 'create_user'
    assert row['target'] == 'newbie'
    detail_raw = row['detail'] or ''
    assert 'password' not in detail_raw.lower()
    assert 'csrf' not in detail_raw.lower()
    detail = json.loads(detail_raw)
    assert detail.get('email') == 'newbie@x.com'
    assert detail.get('ok') is True


def test_edit_user_one_row_with_merged_changes():
    c = app_module.chatbot_app.test_client()
    _admin(c)
    uid = _make_user('mergeme')
    r = c.post('/admin/users/edit',
               json={'id': uid, 'username': 'merged2', 'email': 'merged2@x.com',
                     'role': 'manager', 'active': False},
               headers=_ch())
    assert r.get_json()['ok'] is True
    rows = _all_rows()
    assert len(rows) == 1                       # ONE row, not 3 (no stray set_role/set_active rows)
    assert rows[0]['action'] == 'edit_user'
    changes = json.loads(rows[0]['detail'])['changes']
    assert changes['username'] == {'old': 'mergeme', 'new': 'merged2'}
    assert changes['email'] == {'old': 'mergeme@x.com', 'new': 'merged2@x.com'}
    assert changes['role'] == {'old': 'user', 'new': 'manager'}
    assert changes['active'] == {'old': True, 'new': False}


def test_login_success_failure_logout():
    users_db.create_user('loginuser', 'loginuser@x.com', created_by='t')
    uid = users_db._row_by_username('loginuser')['id']
    users_db.update_password(uid, 'Secret123')

    c = app_module.chatbot_app.test_client()
    r = c.post('/', data={'username': 'loginuser', 'password': 'Secret123'})
    assert r.status_code == 302
    login_row = next(x for x in _all_rows() if x['action'] == 'login')
    assert login_row['actor'] == 'loginuser'
    assert login_row['category'] == 'auth'

    c2 = app_module.chatbot_app.test_client()
    c2.post('/', data={'username': 'loginuser', 'password': 'wrongpw'})
    fail_row = next(x for x in _all_rows() if x['action'] == 'login_failed')
    assert fail_row['actor'] == 'loginuser'
    fail_detail = json.loads(fail_row['detail'])
    assert fail_detail.get('reason') == 'bad_credentials'

    c.get('/logout')            # same client/session as the successful login above
    logout_row = next(x for x in _all_rows() if x['action'] == 'logout')
    assert logout_row['actor'] == 'loginuser'
    # the login POST's raw form body ('password' key) must never end up
    # readable in the stored detail — login() only stashes action/actor/target
    # (no detail kwargs), so this exercises the hook's generic body-capture
    # fallback + the final admin_audit.redact() safety net.
    assert 'Secret123' not in (login_row['detail'] or '')


def test_csrf_reject_logged_with_403():
    c = app_module.chatbot_app.test_client()
    _admin(c)
    uid = _make_user('csrfvictim')
    r = c.post('/admin/users/delete', json={'id': uid})   # no X-CSRF-Token header
    assert r.status_code == 403
    row = next(x for x in _all_rows() if x['status'] == 403)
    assert row['actor'] == 'Admin'


def test_profile_password_csrf_reject_scrubs_raw_password_fields():
    """The confirmed bug: a CSRF-rejected POST /profile/password never reaches
    the handler, so its `stash(..., note='password_change')` marker never runs
    and the hook falls through to its generic raw-body capture. Before the fix,
    the raw {'current', 'new'} body was stored with 'new' left in cleartext
    (admin_audit.SENSITIVE_KEY_EXACT deliberately excludes 'new' to preserve
    changes={'field': {'old','new'}} diffs elsewhere). admin_audit.redact_raw()
    closes that gap for this generic-capture path specifically."""
    c = app_module.chatbot_app.test_client()
    _admin(c, username='pwvictim')
    r = c.post('/profile/password',
               json={'current': 'OldPass1', 'new': 'BrandNewSecret1'})   # no X-CSRF-Token header
    assert r.status_code == 403

    rows = _all_rows()
    assert len(rows) == 1                       # exactly one audit row
    row = rows[0]
    assert row['status'] == 403
    assert row['action'] == 'change_password'

    detail_raw = row['detail'] or ''
    assert 'BrandNewSecret1' not in detail_raw   # the new password is nowhere in the stored row
    assert 'OldPass1' not in detail_raw

    detail = json.loads(detail_raw)
    assert detail['body']['new'] == admin_audit.REDACTED
    assert detail['body']['current'] == admin_audit.REDACTED


def test_hook_failure_never_breaks_request(monkeypatch):
    monkeypatch.setattr(admin_audit, 'log_request', lambda **kw: (_ for _ in ()).throw(RuntimeError('boom')))
    c = app_module.chatbot_app.test_client()
    _admin(c)
    r = c.get('/home')
    assert r.status_code == 200   # the hook swallowed the exception


def test_no_direct_log_action_calls_left():
    """Duplicate-row guard: nothing in app.py or the three Dev-B-owned
    blueprints should call admin_audit.log_action(...) anymore — everything
    goes through stash()/the central hook. Expected to fail until Developer B
    converts ecommerce/approval.py's remaining sites."""
    root = os.path.dirname(os.path.abspath(app_module.__file__))
    paths = [
        os.path.join(root, 'app.py'),
        os.path.join(root, 'ecommerce', 'approval.py'),
        os.path.join(root, 'analytics', 'routes.py'),
        os.path.join(root, 'billing', 'routes.py'),
    ]
    offenders = []
    for p in paths:
        with open(p) as f:
            src = f.read()
        if 'admin_audit.log_action(' in src:
            offenders.append(p)
    assert offenders == [], f"admin_audit.log_action( still present in: {offenders}"
