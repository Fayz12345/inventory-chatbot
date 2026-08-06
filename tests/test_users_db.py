from datetime import datetime, timedelta
import pytest
import users_db


@pytest.fixture(autouse=True)
def fresh_users_db(tmp_path, monkeypatch):
    """Fresh, isolated users.db per test. Overrides users_db.DB_PATH directly
    (monkeypatch, auto-restored) rather than the env var — other test files
    import users_db first (via app), so the import-time env path is already
    cached; setting DB_PATH on the module is what _get_conn actually reads."""
    monkeypatch.setattr(users_db, "DB_PATH", str(tmp_path / "users.db"))
    users_db.init_db()
    yield


def _mk(username="u1", is_admin=False):
    users_db.init_db()
    users_db.create_user(username, username + "@x.com", is_admin=is_admin, created_by="test")
    return next(u for u in users_db.get_all_users() if u["username"] == username)["id"]


def test_new_columns_present_with_defaults():
    uid = _mk("cols")
    u = next(u for u in users_db.get_all_users() if u["id"] == uid)
    assert u["is_active"] == 1 and u["last_login"] is None and u["role"] in ("user", "admin")


def test_set_active_and_set_email():
    uid = _mk("act")
    users_db.set_active(uid, False)
    assert next(u for u in users_db.get_all_users() if u["id"] == uid)["is_active"] == 0
    users_db.set_email(uid, "new@x.com")
    assert next(u for u in users_db.get_all_users() if u["id"] == uid)["email"] == "new@x.com"


def test_set_role_syncs_is_admin():
    uid = _mk("role")
    users_db.set_role(uid, "admin")
    u = next(u for u in users_db.get_all_users() if u["id"] == uid)
    assert u["role"] == "admin" and u["is_admin"] == 1
    users_db.set_role(uid, "viewer")
    u = next(u for u in users_db.get_all_users() if u["id"] == uid)
    assert u["role"] == "viewer" and u["is_admin"] == 0


def test_create_user_invite_persists_role_in_sync_with_is_admin():
    # Regression: an "Admin privileges" invite must persist role='admin' at creation
    # (was falling through to DEFAULT 'user' -> badge showed User + restricted modules
    # until the next init_db backfill on restart).
    users_db.create_user("adm", "adm@x.com", is_admin=True, created_by="t")
    u = users_db._row_by_username("adm")
    assert u["role"] == "admin" and u["is_admin"] == 1

    users_db.create_user("usr", "usr@x.com", is_admin=False, created_by="t")
    u = users_db._row_by_username("usr")
    assert u["role"] == "user" and u["is_admin"] == 0

    # an explicit non-admin role is honored and never flips is_admin on
    users_db.create_user("mgr", "mgr@x.com", role="manager", created_by="t")
    u = users_db._row_by_username("mgr")
    assert u["role"] == "manager" and u["is_admin"] == 0


def test_failed_login_counter_and_reset():
    _mk("lock")
    users_db.record_failed_login("lock")
    users_db.record_failed_login("lock")
    row = users_db._row_by_username("lock")
    assert row["failed_logins"] == 2
    users_db.reset_failed_logins(row["id"])
    assert users_db._row_by_username("lock")["failed_logins"] == 0


def _set_pw(uid, pw):
    # Set a password hash directly with pbkdf2 (available on every platform;
    # the local LibreSSL build lacks hashlib.scrypt, Werkzeug's default).
    from werkzeug.security import generate_password_hash
    conn = users_db._get_conn()
    conn.execute("UPDATE users SET password_hash = ?, password_set = 1 WHERE id = ?",
                 (generate_password_hash(pw, method="pbkdf2:sha256"), uid))
    conn.commit(); conn.close()


def test_authenticate_by_username_or_email():
    # People sign in with the email their invite was sent to, not just the
    # username — authenticate must accept either (email match case-insensitive).
    users_db.create_user("alice", "Alice@Example.com", created_by="t")
    uid = next(u for u in users_db.get_all_users() if u["username"] == "alice")["id"]
    _set_pw(uid, "Secret123!")

    assert users_db.authenticate("alice", "Secret123!")                 # by username
    assert users_db.authenticate("Alice@Example.com", "Secret123!")     # by email (exact)
    assert users_db.authenticate("alice@example.com", "Secret123!")     # by email (diff case)
    assert users_db.authenticate("alice", "nope") is None              # wrong password
    assert users_db.authenticate("ghost@example.com", "Secret123!") is None  # unknown

    assert users_db.get_by_identifier("alice")["id"] == uid
    assert users_db.get_by_identifier("ALICE@example.com")["id"] == uid
    assert users_db.get_by_identifier("nobody") is None


def test_email_login_failure_counts_against_username():
    # A wrong-password attempt made via EMAIL must still record against the real
    # username so the lockout counter works no matter which identifier was used.
    users_db.create_user("bob", "bob@x.com", created_by="t")
    uid = next(u for u in users_db.get_all_users() if u["username"] == "bob")["id"]
    _set_pw(uid, "Right123!")
    assert users_db.authenticate("bob@x.com", "WRONG") is None
    assert users_db._row_by_username("bob")["failed_logins"] == 1


def test_is_locked_boundaries():
    # missing key or None -> not locked
    assert users_db.is_locked({}) is False
    assert users_db.is_locked({'locked_until': None}) is False

    # past timestamp -> not locked
    past = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
    assert users_db.is_locked({'locked_until': past}) is False

    # future timestamp -> locked
    future = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    assert users_db.is_locked({'locked_until': future}) is True
