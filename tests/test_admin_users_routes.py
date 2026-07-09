import pytest
import users_db
import admin_audit
import app as app_module


@pytest.fixture(autouse=True)
def fresh_users_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "users.db")
    monkeypatch.setattr(users_db, "DB_PATH", db_path)
    monkeypatch.setattr(admin_audit, "DB_PATH", db_path)
    users_db.init_db()
    admin_audit.init_db()
    yield


_CSRF = 'TESTTOKEN'


def _set_admin_session(client):
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'Admin'
        s['is_admin'] = True
        s['role'] = 'admin'
        s['csrf_token'] = _CSRF


def _make_user(name):
    users_db.create_user(name, name + "@x.com", created_by="t")
    return users_db._row_by_username(name)["id"]


def _make_admin_user():
    row = users_db._row_by_username("Admin")
    if not row:
        users_db.create_user("Admin", "admin@x.com", is_admin=True, created_by="t")
        row = users_db._row_by_username("Admin")
    return row["id"]


def _ch():
    """Return CSRF headers dict for POST requests to protected admin routes."""
    return {'X-CSRF-Token': _CSRF}


def test_set_active_deactivates_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    uid = _make_user("deact")
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": False}, headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("deact")["is_active"] == 0


def test_set_active_reactivates_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    uid = _make_user("react")
    # deactivate first
    c.post("/admin/users/set-active", json={"id": uid, "active": False}, headers=_ch())
    assert users_db._row_by_username("react")["is_active"] == 0
    # reactivate
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": True}, headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("react")["is_active"] == 1


def test_set_active_self_guard():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    admin_id = _make_admin_user()
    resp = c.post("/admin/users/set-active", json={"id": admin_id, "active": False}, headers=_ch())
    data = resp.get_json()
    assert data["ok"] is False


def test_set_active_requires_admin():
    c = app_module.chatbot_app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'normaluser'
        s['is_admin'] = False
        s['csrf_token'] = _CSRF
    uid = _make_user("target")
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": False}, headers=_ch())
    assert resp.status_code == 403


def test_set_active_unknown_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/set-active", json={"id": 99999, "active": False}, headers=_ch())
    assert resp.get_json()["ok"] is False


def test_edit_user_updates_and_rejects_dupe_username():
    a = _make_user("edit_a"); _make_user("edit_b")
    c = app_module.chatbot_app.test_client(); _set_admin_session(c)
    ok = c.post("/admin/users/edit", json={"id": a, "username": "edit_a2", "email": "a2@x.com"}, headers=_ch()).get_json()
    assert ok["ok"] is True and users_db._row_by_username("edit_a2")["email"] == "a2@x.com"
    dupe = c.post("/admin/users/edit", json={"id": a, "username": "edit_b", "email": "a2@x.com"}, headers=_ch()).get_json()
    assert dupe["ok"] is False


def test_admin_users_page_tojson_escapes_single_quote_in_username():
    """Regression: username with a single quote must not break out of onclick JS string literals.

    Jinja tojson in an HTML context emits \\u0027 for the single quote, producing
    onclick='deleteUser(1, "o\\u0027brien")'.  The dangerous raw breakout pattern
    'o'brien' (raw unescaped single quote inside a single-quoted attribute) must be absent.
    """
    users_db.create_user("o'brien", "obrien@x.com", created_by="t")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.get("/admin/users")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # tojson escapes the single quote as ' in an HTML context → safe unicode-escaped form present
    assert "\\u0027brien" in body
    # The dangerous raw breakout pattern must NOT appear in any onclick attribute
    assert "'o'brien'" not in body


def test_delete_writes_audit_row():
    uid = _make_user("audituser")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    c.post("/admin/users/delete", json={"id": uid}, headers=_ch())
    assert any(r["action"] == "delete_user" and r["target"] == "audituser"
               for r in admin_audit.recent(50))


# --- Edit modal consolidation: role + active via /admin/users/edit ---

def test_edit_sets_role():
    uid = _make_user("roleuser")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "roleuser", "email": "roleuser@x.com", "role": "manager"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    row = users_db._row_by_username("roleuser")
    assert row["role"] == "manager"
    assert row["is_admin"] == 0


def test_edit_sets_role_admin_syncs_is_admin():
    uid = _make_user("roleadmin")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "roleadmin", "email": "roleadmin@x.com", "role": "admin"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    row = users_db._row_by_username("roleadmin")
    assert row["role"] == "admin"
    assert row["is_admin"] == 1


def test_edit_sets_active_false_string():
    uid = _make_user("actfalse")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "actfalse", "email": "actfalse@x.com", "active": "false"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("actfalse")["is_active"] == 0


def test_edit_sets_active_true_string():
    uid = _make_user("acttrue")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    # deactivate first via standalone endpoint
    c.post("/admin/users/set-active", json={"id": uid, "active": False}, headers=_ch())
    assert users_db._row_by_username("acttrue")["is_active"] == 0
    # reactivate via edit endpoint
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "acttrue", "email": "acttrue@x.com", "active": "true"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("acttrue")["is_active"] == 1


def test_edit_sets_active_zero_string():
    uid = _make_user("actzero")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "actzero", "email": "actzero@x.com", "active": "0"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("actzero")["is_active"] == 0


def test_edit_sets_active_one_string():
    uid = _make_user("actone")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    c.post("/admin/users/set-active", json={"id": uid, "active": False}, headers=_ch())
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "actone", "email": "actone@x.com", "active": "1"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("actone")["is_active"] == 1


def test_edit_self_guard_does_not_change_role():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    admin_id = _make_admin_user()
    # Attempt to change own role to 'viewer' — should be silently ignored
    resp = c.post("/admin/users/edit",
                  json={"id": admin_id, "username": "Admin", "email": "admin@x.com", "role": "viewer"},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    row = users_db._row_by_username("Admin")
    assert row["role"] != "viewer"


def test_edit_self_guard_does_not_change_active():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    admin_id = _make_admin_user()
    # Attempt to deactivate own account — should be silently ignored
    resp = c.post("/admin/users/edit",
                  json={"id": admin_id, "username": "Admin", "email": "admin@x.com", "active": False},
                  headers=_ch())
    assert resp.get_json()["ok"] is True
    row = users_db._row_by_username("Admin")
    assert row["is_active"] == 1


def test_edit_invalid_role_returns_error():
    uid = _make_user("badrole")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/edit",
                  json={"id": uid, "username": "badrole", "email": "badrole@x.com", "role": "superuser"},
                  headers=_ch())
    assert resp.get_json()["ok"] is False


def test_edit_role_writes_audit_row():
    uid = _make_user("auditrole")
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    c.post("/admin/users/edit",
           json={"id": uid, "username": "auditrole", "email": "auditrole@x.com", "role": "viewer"},
           headers=_ch())
    assert any(r["action"] == "set_role" and r["target"] == "auditrole" and r["detail"] == "viewer"
               for r in admin_audit.recent(50))
