import pytest
import users_db
import app as app_module


@pytest.fixture(autouse=True)
def fresh_users_db(tmp_path, monkeypatch):
    monkeypatch.setattr(users_db, "DB_PATH", str(tmp_path / "users.db"))
    users_db.init_db()
    yield


def _set_admin_session(client):
    with client.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'Admin'
        s['is_admin'] = True
        s['role'] = 'admin'


def _make_user(name):
    users_db.create_user(name, name + "@x.com", created_by="t")
    return users_db._row_by_username(name)["id"]


def _make_admin_user():
    row = users_db._row_by_username("Admin")
    if not row:
        users_db.create_user("Admin", "admin@x.com", is_admin=True, created_by="t")
        row = users_db._row_by_username("Admin")
    return row["id"]


def test_set_active_deactivates_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    uid = _make_user("deact")
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": False})
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("deact")["is_active"] == 0


def test_set_active_reactivates_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    uid = _make_user("react")
    # deactivate first
    c.post("/admin/users/set-active", json={"id": uid, "active": False})
    assert users_db._row_by_username("react")["is_active"] == 0
    # reactivate
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": True})
    assert resp.get_json()["ok"] is True
    assert users_db._row_by_username("react")["is_active"] == 1


def test_set_active_self_guard():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    admin_id = _make_admin_user()
    resp = c.post("/admin/users/set-active", json={"id": admin_id, "active": False})
    data = resp.get_json()
    assert data["ok"] is False


def test_set_active_requires_admin():
    c = app_module.chatbot_app.test_client()
    with c.session_transaction() as s:
        s['logged_in'] = True
        s['username'] = 'normaluser'
        s['is_admin'] = False
    uid = _make_user("target")
    resp = c.post("/admin/users/set-active", json={"id": uid, "active": False})
    assert resp.status_code == 403


def test_set_active_unknown_user():
    c = app_module.chatbot_app.test_client()
    _set_admin_session(c)
    resp = c.post("/admin/users/set-active", json={"id": 99999, "active": False})
    assert resp.get_json()["ok"] is False
