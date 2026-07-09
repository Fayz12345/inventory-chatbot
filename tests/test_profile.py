import pytest
from werkzeug.security import generate_password_hash as _gen_hash
import users_db
import app as _app


@pytest.fixture(autouse=True)
def fresh_users_db(tmp_path, monkeypatch):
    monkeypatch.setattr(users_db, "DB_PATH", str(tmp_path / "users.db"))
    # Python 3.9 on macOS lacks hashlib.scrypt; force pbkdf2 in tests.
    monkeypatch.setattr(
        users_db,
        "generate_password_hash",
        lambda pw, **kw: _gen_hash(pw, method="pbkdf2:sha256"),
    )
    users_db.init_db()
    yield


def _login(client, name="pu"):
    users_db.create_user(name, name + "@x.com", created_by="t")
    uid = users_db._row_by_username(name)["id"]
    users_db.update_password(uid, "OldPass1")
    with client.session_transaction() as s:
        s["logged_in"] = True
        s["username"] = name
        s["is_admin"] = False
        s["role"] = "user"
        s["csrf_token"] = "TESTTOKEN"
    return uid


# --- GET /profile ---

def test_profile_redirects_when_not_logged_in():
    c = _app.chatbot_app.test_client()
    resp = c.get("/profile")
    assert resp.status_code in (301, 302)
    assert "/login" in resp.headers.get("Location", "") or "/" in resp.headers.get("Location", "")


def test_profile_renders_for_logged_in_user():
    c = _app.chatbot_app.test_client()
    _login(c, "profuser")
    resp = c.get("/profile")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "profuser" in body


# --- POST /profile/password ---

def test_change_password_requires_correct_current():
    c = _app.chatbot_app.test_client()
    _login(c)
    h = {"X-CSRF-Token": "TESTTOKEN"}
    bad = c.post("/profile/password", json={"current": "WRONG", "new": "NewPass2"}, headers=h).get_json()
    assert bad["ok"] is False
    ok = c.post("/profile/password", json={"current": "OldPass1", "new": "NewPass2"}, headers=h).get_json()
    assert ok["ok"] is True
    # verify new password works via authenticate
    assert users_db.authenticate("pu", "NewPass2") is not None


def test_change_password_rejects_short_new_password():
    c = _app.chatbot_app.test_client()
    _login(c)
    h = {"X-CSRF-Token": "TESTTOKEN"}
    resp = c.post("/profile/password", json={"current": "OldPass1", "new": "abc"}, headers=h).get_json()
    assert resp["ok"] is False
    assert "6" in resp.get("error", "")


def test_change_password_requires_login():
    c = _app.chatbot_app.test_client()
    h = {"X-CSRF-Token": "TESTTOKEN"}
    resp = c.post("/profile/password", json={"current": "OldPass1", "new": "NewPass2"}, headers=h)
    # unauthenticated: CSRF guard may fire first (403) or route returns 401
    assert resp.status_code in (401, 403)


def test_wrong_current_password_does_not_lock_account():
    """Mistyping current password 5 times must NOT lock the account."""
    c = _app.chatbot_app.test_client()
    _login(c)
    h = {"X-CSRF-Token": "TESTTOKEN"}
    for _ in range(5):
        bad = c.post("/profile/password", json={"current": "WRONG", "new": "NewPass2"}, headers=h).get_json()
        assert bad["ok"] is False
    row = users_db._row_by_username("pu")
    # failed_logins counter must remain 0 (no side-effects from verify_password)
    assert not users_db.is_locked(row), "Account must not be locked after repeated wrong current-password entries"
    assert row["failed_logins"] == 0


# --- POST /profile/email ---

def test_update_email_success():
    c = _app.chatbot_app.test_client()
    _login(c)
    h = {"X-CSRF-Token": "TESTTOKEN"}
    resp = c.post("/profile/email", json={"email": "new@example.com"}, headers=h).get_json()
    assert resp["ok"] is True
    row = users_db._row_by_username("pu")
    assert row["email"] == "new@example.com"


def test_update_email_requires_login():
    c = _app.chatbot_app.test_client()
    h = {"X-CSRF-Token": "TESTTOKEN"}
    resp = c.post("/profile/email", json={"email": "new@example.com"}, headers=h)
    assert resp.status_code in (401, 403)


def test_csrf_blocks_profile_password_post():
    c = _app.chatbot_app.test_client()
    _login(c)
    # No X-CSRF-Token header — should get 403
    resp = c.post("/profile/password", json={"current": "OldPass1", "new": "NewPass2"})
    assert resp.status_code == 403


def test_csrf_blocks_profile_email_post():
    c = _app.chatbot_app.test_client()
    _login(c)
    resp = c.post("/profile/email", json={"email": "x@x.com"})
    assert resp.status_code == 403
