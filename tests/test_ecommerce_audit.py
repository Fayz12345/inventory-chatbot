"""Tests that approve/post/mark-listed/reject/scrape-settings enrich the admin
audit trail via admin_audit.stash(...) (the central app.py hook writes the row;
these tests only verify the blueprint's stash calls, per the Phase 1B audit
design). Mirrors the harness in test_approval_dispatch.py (same client fixture,
same _rec/_copy helpers). Patches ecommerce.approval.admin_audit.stash directly
to capture calls without touching the real DB. Also tests that an audit failure
never breaks the approval response.
"""
from unittest.mock import patch

import pytest

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


def _merged_stash_kwargs(mock_stash):
    """Merge every stash(...) call's kwargs (later calls overwrite scalars,
    like the real g.audit accumulator) so tests can assert on the net result
    regardless of how many times the handler called stash()."""
    merged = {}
    for call in mock_stash.call_args_list:
        merged.update(call.kwargs)
    return merged


# ---------------------------------------------------------------------------
# Approve — audit stash (preview only, no marketplace call)
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash")
@patch("ecommerce.approval.listing_availability",
       return_value={"available": True, "reason": "", "env": "sandbox"})
@patch("ecommerce.approval.db.claim_recommendation")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_approve_stashes_action_target_marketplace_price(
        _get, _copy_, _claim, _avail, mock_stash, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "ecommerce_preview"
    assert "Samsung" in detail["target"] and "S25 Ultra" in detail["target"]
    assert "Grade A" in detail["target"]
    assert detail["marketplace"] == "eBay CA"
    assert detail["price"] == 829.99
    assert detail["can_post"] is True


# ---------------------------------------------------------------------------
# Post — audit stash
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash")
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
def test_post_stashes_action_target_marketplace_price_and_listing_id(
        _get, _copy_, _amazon, _catalog, _claim, _decision, _log_record, _devcat, mock_stash, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "ecommerce_post"
    assert "Samsung" in detail["target"] and "S25 Ultra" in detail["target"]
    assert "Grade A" in detail["target"]
    assert detail["marketplace"] == "Amazon CA"
    assert detail["price"] == 829.99
    assert detail["rec_id"] == 1
    assert detail["listing_id"] == "SAMSUNG-S25-A-BLACK"
    assert detail["env"] == "sandbox"


# ---------------------------------------------------------------------------
# Mark-listed — audit stash
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash")
@patch("ecommerce.approval.db.create_listing_record", return_value=60)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_mark_listed_stashes_action_target_marketplace_price(
        _get, _claim, _decision, _log_record, mock_stash, client):
    resp = client.post("/ecommerce/mark-listed?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "ecommerce_mark_listed"
    assert "Samsung" in detail["target"] and "S25 Ultra" in detail["target"]
    assert detail["marketplace"] == "Best Buy CA"
    assert detail["price"] == 829.99
    assert detail["rec_id"] == 1
    assert detail["manual"] is True


# ---------------------------------------------------------------------------
# Reject — audit stash
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_reject_stashes_action_target_marketplace_price(_get, _claim, mock_stash, client):
    resp = client.post("/ecommerce/reject?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "ecommerce_reject"
    assert "Samsung" in detail["target"] and "S25 Ultra" in detail["target"]
    assert detail["marketplace"] == "Amazon CA"
    assert detail["price"] == 829.99
    assert detail["rec_id"] == 1


# ---------------------------------------------------------------------------
# Scrape-settings — audit stash
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash")
@patch("ecommerce.approval.db.save_scrape_settings",
       return_value={"categories": ["phones"], "scope_mode": "top", "top_n": 25})
def test_scrape_settings_save_stashes_scope(mock_save, mock_stash, client):
    resp = client.post("/ecommerce/scrape-settings",
                        json={"categories": ["phones"], "scope_mode": "top", "top_n": 25})
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    detail = _merged_stash_kwargs(mock_stash)
    assert detail["action"] == "ecommerce_scrape_settings"
    assert detail["categories"] == ["phones"]
    assert detail["scope_mode"] == "top"
    assert detail["top_n"] == 25


# ---------------------------------------------------------------------------
# Audit failure must NOT break the response (real stash() never raises, but
# this belt-and-braces test guards against a future regression that makes it
# raise, or a caller that forgets stash's own try/except).
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.admin_audit.stash", side_effect=Exception("DB exploded"))
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
def test_audit_failure_does_not_break_post(
        _get, _copy_, _amazon, _catalog, _claim, _decision, _log_record, _devcat, mock_stash, client):
    """If admin_audit.stash raises, /post must still return ok=True."""
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
