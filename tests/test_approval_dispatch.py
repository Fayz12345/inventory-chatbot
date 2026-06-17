"""Unit tests for the approve/reject route dispatch (ADO #138 / 1D.6 + #198 / 1D.10).

Covers:
  - Amazon CA / eBay CA: dispatch to the listing module; success logs to
    EcommerceListingsLog and finalizes the claim to 'approved'; failure releases
    the claim and returns 502 (NOT approved).
  - Best Buy CA / Reebelo CA: preview-only — no API call, claimed straight to
    'approved'.
  - #198 hardening: 401 when unauthenticated; atomic claim prevents double-post
    (lost race -> 409); reject also claims atomically.
"""
from unittest.mock import patch

import pytest

import app  # ensure dotenv + blueprints are loaded


@pytest.fixture
def client():
    """Authenticated client — mirrors a logged-in operator."""
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "tester"
        yield c


@pytest.fixture
def anon_client():
    """Unauthenticated client — no session."""
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
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
# Auto-post success / failure
# ---------------------------------------------------------------------------

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
def test_amazon_success_claims_posts_logs_and_approves(
        _get, _copy_, mock_amazon, _catalog, mock_claim, mock_decision, mock_log, _devcat, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["posted"] is True
    assert body["listing_id"] == "SAMSUNG-S25-A-BLACK"
    assert body["env"] == "sandbox"
    mock_amazon.assert_called_once()
    # device category is resolved and passed to the Amazon listing call (#3).
    assert mock_amazon.call_args.kwargs["device_category"] == "Handset"
    mock_claim.assert_called_once_with(1, "processing")   # claimed before posting
    mock_log.assert_called_once()
    mock_decision.assert_called_once_with(1, "approved")  # finalized after log
    assert mock_log.call_args.kwargs["floor_price"] == 850.0


@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": None, "upc": None, "epid": None})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": False, "error": "Amazon SP-API: bad seller_id"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_amazon_failure_releases_claim_and_returns_502(
        _get, _copy_, mock_amazon, _catalog, mock_claim, mock_release, mock_decision, mock_log, _devcat, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["ok"] is False and "bad seller_id" in body["error"]
    mock_amazon.assert_called_once()
    mock_release.assert_called_once_with(1)   # claim released on failure
    mock_log.assert_not_called()
    mock_decision.assert_not_called()         # NOT approved on failure


@patch("ecommerce.approval.db.create_listing_record", return_value=43)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": None, "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.ebay_listings.create_listing",
       return_value={"ok": True, "listing_id": "12345", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_ebay_success_claims_posts_logs_and_approves(
        _get, _copy_, mock_ebay, _catalog, mock_claim, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["posted"] is True
    assert body["listing_id"] == "12345"
    mock_ebay.assert_called_once()
    mock_claim.assert_called_once_with(1, "processing")
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["floor_price"] == 780.0


# ---------------------------------------------------------------------------
# Atomicity: post succeeds but logging fails -> rollback (delist) + release
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.lookup_device_category", return_value="Tablet")
@patch("ecommerce.approval.amazon_listings.delist", return_value=True)
@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.create_listing_record", side_effect=Exception("DB down"))
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SKU-1", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_log_failure_rolls_back_post_and_releases(
        _get, _copy_, _amazon, _catalog, _claim, mock_create, mock_decision,
        mock_release, mock_delist, _devcat, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 500
    assert resp.get_json()["ok"] is False
    # rolled back with the resolved device category for the productType (#3).
    mock_delist.assert_called_once_with("SKU-1", device_category="Tablet")
    mock_release.assert_called_once_with(1)
    mock_decision.assert_not_called()              # never finalized to approved


# ---------------------------------------------------------------------------
# Preview-only marketplaces
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.ebay_listings.create_listing")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_best_buy_is_preview_only_claims_approved(
        _get, _copy_, mock_ebay, mock_amazon, mock_log, mock_claim, mock_decision, client):
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    assert body["posted"] is False and body["listing_id"] is None
    mock_amazon.assert_not_called()
    mock_ebay.assert_not_called()
    mock_log.assert_not_called()                       # preview-only -> no log row
    mock_claim.assert_called_once_with(1, "approved")  # claimed straight to approved
    mock_decision.assert_not_called()


@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.ebay_listings.create_listing")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Reebelo CA"))
def test_reebelo_is_preview_only_per_138_ac(
        _get, _copy_, mock_ebay, mock_amazon, _log, mock_claim, _decision, client):
    """ADO #138 explicitly says Reebelo CA stays preview-only — locked here."""
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.get_json()["posted"] is False
    mock_amazon.assert_not_called()
    mock_ebay.assert_not_called()
    mock_claim.assert_called_once_with(1, "approved")


# ---------------------------------------------------------------------------
# Auth + race guards (#198)
# ---------------------------------------------------------------------------

def test_unauthenticated_approve_returns_401(anon_client):
    resp = anon_client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 401
    assert resp.get_json()["ok"] is False


def test_unauthenticated_reject_returns_401(anon_client):
    resp = anon_client.post("/ecommerce/reject?id=1")
    assert resp.status_code == 401


@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.db.claim_recommendation", return_value=False)
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_lost_race_returns_409_without_posting(_get, _copy_, mock_claim, mock_amazon, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 409
    assert "processed" in resp.get_json()["error"].lower()
    mock_amazon.assert_not_called()   # never posted — lost the claim


@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_reject_claims_atomically(_get, mock_claim, client):
    resp = client.post("/ecommerce/reject?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    mock_claim.assert_called_once_with(1, "rejected")


@patch("ecommerce.approval.db.get_recommendation_by_id",
       return_value=_rec("Amazon CA", decision="approved"))
def test_already_decided_returns_409(_get, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 409
    assert "Already" in resp.get_json()["error"]


def test_missing_id_returns_400(client):
    resp = client.post("/ecommerce/approve")
    assert resp.status_code == 400
