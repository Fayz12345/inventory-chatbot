"""Unit tests for the approve route's marketplace dispatch (ADO #138 / 1D.6).

Covers all four #138 AC branches:
  - Amazon CA: dispatches to amazon_listings.create_listing; success path logs
    to EcommerceListingsLog and marks approved; failure path returns 502 and
    does NOT mark approved.
  - eBay CA: same shape, via ebay_listings.
  - Best Buy CA / Reebelo CA: preview-only — no API call, no log row, marks
    approved.
  - Missing creds: marketplace module returns ok:False — approve returns 502.
"""
from unittest.mock import patch

import pytest

import app  # ensure dotenv + blueprints are loaded


@pytest.fixture
def client():
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


@patch("ecommerce.approval.db.create_listing_record", return_value=42)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": "B0XXXX", "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SAMSUNG-S25-A-BLACK", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_amazon_success_posts_logs_and_approves(_, __, mock_amazon, mock_catalog, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["posted"] is True
    assert body["listing_id"] == "SAMSUNG-S25-A-BLACK"
    assert body["env"] == "sandbox"
    mock_amazon.assert_called_once()
    mock_log.assert_called_once()
    mock_decision.assert_called_once_with(1, "approved")
    # AmazonFloor was the right floor column.
    assert mock_log.call_args.kwargs["floor_price"] == 850.0


@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": None, "upc": None, "epid": None})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": False, "error": "Amazon SP-API: bad seller_id"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_amazon_failure_returns_502_and_does_not_approve(_, __, mock_amazon, mock_catalog, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 502
    body = resp.get_json()
    assert body["ok"] is False
    assert "bad seller_id" in body["error"]
    mock_amazon.assert_called_once()
    mock_log.assert_not_called()
    mock_decision.assert_not_called()


@patch("ecommerce.approval.db.create_listing_record", return_value=43)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": None, "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.ebay_listings.create_listing",
       return_value={"ok": True, "listing_id": "12345", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_ebay_success_posts_logs_and_approves(_, __, mock_ebay, mock_catalog, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["posted"] is True
    assert body["listing_id"] == "12345"
    mock_ebay.assert_called_once()
    mock_log.assert_called_once()
    # EbayFloor was the right floor column.
    assert mock_log.call_args.kwargs["floor_price"] == 780.0


@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.ebay_listings.create_listing")
@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_best_buy_is_preview_only_no_api_call(_, __, mock_decision, mock_log, mock_ebay, mock_amazon, client):
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    assert body["posted"] is False
    assert body["listing_id"] is None
    mock_amazon.assert_not_called()
    mock_ebay.assert_not_called()
    mock_log.assert_not_called()              # preview-only -> no listings log row
    mock_decision.assert_called_once_with(1, "approved")


@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.ebay_listings.create_listing")
@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Reebelo CA"))
def test_reebelo_is_preview_only_per_138_ac(_, __, mock_decision, mock_log, mock_ebay, mock_amazon, client):
    """ADO #138 explicitly says Reebelo CA stays preview-only — locked here."""
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert body["posted"] is False
    mock_amazon.assert_not_called()
    mock_ebay.assert_not_called()
    mock_log.assert_not_called()


@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA", decision="approved"))
def test_already_decided_returns_409(_, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 409
    assert "Already" in resp.get_json()["error"]


def test_missing_id_returns_400(client):
    resp = client.post("/ecommerce/approve")
    assert resp.status_code == 400
