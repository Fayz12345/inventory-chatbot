"""Unit tests for the Reebelo (Cobalt) listing module (ticket 1D.12).

Built from the docs; no live key yet, so these lock the payload + the
updated/skipped/failed response handling with the network mocked.
"""
from unittest.mock import MagicMock, patch

from ecommerce.listings import reebelo
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = str(payload or "")
    return m


def _product():
    return {"Manufacturer": "Samsung", "Model": "Galaxy S21",
            "Colour": "Black", "Grade": "A", "Quantity": 3}


def _creds(monkeypatch):
    monkeypatch.setattr(config, "REEBELO_API_KEY", "test-key")
    monkeypatch.setattr(config, "REEBELO_API_BASE", "https://a.reebelo.blue")
    monkeypatch.setattr(config, "REEBELO_SANDBOX", True)


def test_no_creds_returns_error(monkeypatch):
    monkeypatch.setattr(config, "REEBELO_API_KEY", "")
    out = reebelo.create_listing(_product(), 299.99, {})
    assert out["ok"] is False and "not configured" in out["error"]


def test_name_encodes_grade():
    # Cobalt has no condition field, so grade must be in the name.
    assert reebelo._name(_product()) == "Samsung Galaxy S21 Black - Grade A"


@patch("ecommerce.listings.reebelo.requests")
def test_create_listing_updated_offer_succeeds(mock_requests, monkeypatch):
    _creds(monkeypatch)
    sku = "SAMSUNG-GALAXY-S21-A-BLACK"
    mock_requests.post.return_value = _resp(200, {"updatedOffers": [{"sku": sku}],
                                                  "skippedOffers": [], "failedOffers": []})
    out = reebelo.create_listing(_product(), 299.99, {})
    assert out == {"ok": True, "listing_id": sku, "env": "sandbox"}

    args = mock_requests.post.call_args
    assert args.args[0].endswith("/sockets/offers/update")
    assert args.kwargs["headers"]["x-api-key"] == "test-key"
    offer = args.kwargs["json"]["data"][0]
    assert offer == {"sku": sku, "name": "Samsung Galaxy S21 Black - Grade A",
                     "price": 299.99, "stock": 3}


@patch("ecommerce.listings.reebelo.requests")
def test_create_listing_unchanged_is_success(mock_requests, monkeypatch):
    _creds(monkeypatch)
    sku = "SAMSUNG-GALAXY-S21-A-BLACK"
    mock_requests.post.return_value = _resp(200, {"updatedOffers": [],
        "skippedOffers": [{"sku": sku, "reason": "unchanged"}], "failedOffers": []})
    assert reebelo.create_listing(_product(), 299.99, {})["ok"] is True


@patch("ecommerce.listings.reebelo.requests")
def test_create_listing_vendor_deactivated_fails(mock_requests, monkeypatch):
    _creds(monkeypatch)
    sku = "SAMSUNG-GALAXY-S21-A-BLACK"
    mock_requests.post.return_value = _resp(200, {"updatedOffers": [],
        "skippedOffers": [{"sku": sku, "reason": "vendor_deactivated"}], "failedOffers": []})
    out = reebelo.create_listing(_product(), 299.99, {})
    assert out["ok"] is False and "vendor_deactivated" in out["error"]


@patch("ecommerce.listings.reebelo.requests")
def test_create_listing_failed_offer_fails(mock_requests, monkeypatch):
    _creds(monkeypatch)
    sku = "SAMSUNG-GALAXY-S21-A-BLACK"
    mock_requests.post.return_value = _resp(200, {"updatedOffers": [], "skippedOffers": [],
        "failedOffers": [{"sku": sku, "reason": "internal_error"}], "requestId": "req-1"})
    assert reebelo.create_listing(_product(), 299.99, {})["ok"] is False


@patch("ecommerce.listings.reebelo.requests")
def test_delist_sets_stock_zero(mock_requests, monkeypatch):
    _creds(monkeypatch)
    sku = "SAMSUNG-GALAXY-S21-A-BLACK"
    mock_requests.post.return_value = _resp(200, {"updatedOffers": [{"sku": sku}]})
    assert reebelo.delist(sku) is True
    offer = mock_requests.post.call_args.kwargs["json"]["data"][0]
    assert offer == {"sku": sku, "stock": 0}
