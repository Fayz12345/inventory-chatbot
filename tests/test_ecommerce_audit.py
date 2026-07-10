"""Tests that approve/reject write to the admin audit trail.

Mirrors the harness in test_approval_dispatch.py (same client fixture, same
_rec/_copy helpers). Patches admin_audit.log_action directly to capture calls
without touching the real DB. Also tests that an audit failure never breaks the
approval response.
"""
from unittest.mock import MagicMock, patch

import pytest

import admin_audit
import app  # ensure dotenv + blueprints are loaded


@pytest.fixture
def client():
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "tester"
            sess["role"] = "admin"
        yield c


def _rec(marketplace="Amazon CA", decision=None):
    return {
        "ID": 1, "Decision": decision,
        "Manufacturer": "Samsung", "Model": "S25 Ultra", "Colour": "Black",
        "Grade": "A", "Quantity": 3,
        "RecommendedMarketplace": marketplace, "RecommendedPrice": 829.99,
        "AmazonFloor": 850.0, "EbayFloor": 780.0,
        "BestBuyFloor": 900.0, "ReebeloFloor": 760.0,
    }


def _copy():
    return {"title": "T", "description": "D", "bullets": ["b1"], "condition_note": "C"}


# ---------------------------------------------------------------------------
# Approve — audit log
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.log_action")
@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.db.create_listing_record", return_value=42)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": "B0XXXX", "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SAMSUNG-S25-A-BLACK", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_approve_logs_to_audit(
        _get, _copy_, _amazon, _catalog, _claim, _decision, _log_record, _devcat, mock_audit, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args
    actor, action = call_kwargs.args[0], call_kwargs.args[1]
    assert actor == "tester"
    assert action == "ecommerce_approve"
    assert "Samsung" in call_kwargs.kwargs["target"]
    assert "S25 Ultra" in call_kwargs.kwargs["target"]
    assert "Grade A" in call_kwargs.kwargs["target"]
    assert "829.99" in call_kwargs.kwargs["detail"]


# ---------------------------------------------------------------------------
# Reject — audit log
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.log_action")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_reject_logs_to_audit(_get, _claim, mock_audit, client):
    resp = client.post("/ecommerce/reject?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args
    actor, action = call_kwargs.args[0], call_kwargs.args[1]
    assert actor == "tester"
    assert action == "ecommerce_reject"
    assert "Samsung" in call_kwargs.kwargs["target"]
    assert "S25 Ultra" in call_kwargs.kwargs["target"]
    assert "Grade A" in call_kwargs.kwargs["target"]
    assert "829.99" in call_kwargs.kwargs["detail"]


# ---------------------------------------------------------------------------
# Audit failure must NOT break approval
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.log_action", side_effect=Exception("DB exploded"))
@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.db.create_listing_record", return_value=42)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": "B0XXXX", "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SAMSUNG-S25-A-BLACK", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_audit_failure_does_not_break_approve(
        _get, _copy_, _amazon, _catalog, _claim, _decision, _log_record, _devcat, mock_audit, client):
    """If admin_audit.log_action raises, approve() must still return ok=True."""
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
