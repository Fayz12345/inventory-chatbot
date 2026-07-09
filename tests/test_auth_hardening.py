import pytest
from werkzeug.security import generate_password_hash as _gen_hash
import users_db


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


def _user(name="alice", pw="Secret123"):
    users_db.create_user(name, name + "@x.com", created_by="t")
    uid = users_db._row_by_username(name)["id"]
    users_db.update_password(uid, pw)   # sets password_set=1
    return uid


def test_inactive_user_cannot_authenticate():
    uid = _user("inact")
    users_db.set_active(uid, False)
    assert users_db.authenticate("inact", "Secret123") is None


def test_lockout_after_five_failures():
    _user("brute")
    for _ in range(5):
        assert users_db.authenticate("brute", "wrong") is None
    # even the correct password is rejected while locked
    assert users_db.authenticate("brute", "Secret123") is None
    assert users_db.is_locked(users_db._row_by_username("brute")) is True


def test_success_updates_last_login_and_clears_counter():
    _user("good")
    users_db.record_failed_login("good")
    u = users_db.authenticate("good", "Secret123")
    assert u is not None
    row = users_db._row_by_username("good")
    assert row["failed_logins"] == 0 and row["last_login"] is not None


def test_login_route_shows_disabled_message():
    import app as _app
    uid = _user("disabled_user", "Secret123")
    users_db.set_active(uid, False)
    c = _app.chatbot_app.test_client()
    resp = c.post("/", data={"username": "disabled_user", "password": "Secret123"})
    assert "disabled" in resp.get_data(as_text=True)


def test_login_route_shows_locked_message():
    import app as _app
    _user("locked_user", "Secret123")
    for _ in range(5):
        users_db.record_failed_login("locked_user")
    c = _app.chatbot_app.test_client()
    resp = c.post("/", data={"username": "locked_user", "password": "Secret123"})
    assert "Too many failed attempts" in resp.get_data(as_text=True)
