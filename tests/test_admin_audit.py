import pytest
import admin_audit


@pytest.fixture(autouse=True)
def fresh_audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(admin_audit, "DB_PATH", str(tmp_path / "users.db"))
    admin_audit.init_db()
    yield


def test_log_and_recent():
    admin_audit.log_action("admin", "delete_user", target="bob", detail="id=3")
    admin_audit.log_action("admin", "set_role", target="alice", detail="viewer->admin")
    rows = admin_audit.recent(10)
    assert rows[0]["action"] == "set_role" and rows[0]["actor"] == "admin"
    assert any(r["action"] == "delete_user" and r["target"] == "bob" for r in rows)
