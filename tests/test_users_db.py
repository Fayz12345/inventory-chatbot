import os
from datetime import datetime, timedelta
os.environ["USERS_DB_PATH"] = "/tmp/test_users_db_enh.db"
if os.path.exists("/tmp/test_users_db_enh.db"):
    os.remove("/tmp/test_users_db_enh.db")
import users_db


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


def test_failed_login_counter_and_reset():
    _mk("lock")
    users_db.record_failed_login("lock")
    users_db.record_failed_login("lock")
    row = users_db._row_by_username("lock")
    assert row["failed_logins"] == 2
    users_db.reset_failed_logins(row["id"])
    assert users_db._row_by_username("lock")["failed_logins"] == 0


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
