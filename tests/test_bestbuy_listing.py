"""Unit tests for the Best Buy (Mirakl) listing module (ticket 1D.11).

The read path (auth/base URL) is verified live; these lock the create-offer
payload + the submit/poll flow with the network mocked.
"""
import re
from unittest.mock import MagicMock, patch

from ecommerce.listings import bestbuy
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = str(payload or "")
    return m


def _product():
    return {"Manufacturer": "Samsung", "Model": "Galaxy S21",
            "Colour": "Black", "Grade": "A", "Quantity": 2}


def _copy():
    return {"condition_note": "Fully tested, minimal wear."}


def _creds(monkeypatch):
    monkeypatch.setattr(config, "BESTBUY_API_KEY", "test-key")
    monkeypatch.setattr(config, "BESTBUY_API_BASE", "https://marketplace.bestbuy.ca/api")
    monkeypatch.setattr(config, "BESTBUY_STATE_CODE", "11")
    monkeypatch.setattr(config, "BESTBUY_LOGISTIC_CLASS", "SMALL")
    monkeypatch.setattr(config, "BESTBUY_PRODUCT_ID_TYPE", "UPC-A")
    monkeypatch.setattr(config, "BESTBUY_LEADTIME_TO_SHIP", 4)
    monkeypatch.setattr(config, "BESTBUY_MANUFACTURER_WARRANTY", "365")
    # Keep the demo-only quantity override out of the unit tests.
    monkeypatch.setattr(config, "BESTBUY_FORCE_QUANTITY", "")


def test_no_creds_returns_error(monkeypatch):
    monkeypatch.setattr(config, "BESTBUY_API_KEY", "")
    out = bestbuy.create_listing(_product(), 299.99, _copy(), catalog_info={"upc": "123"})
    assert out["ok"] is False and "not configured" in out["error"]


def test_no_product_ref_returns_error(monkeypatch):
    # Neither a product SKU nor a UPC -> can't reference a Best Buy catalog product.
    _creds(monkeypatch)
    out = bestbuy.create_listing(_product(), 299.99, _copy(), catalog_info={})
    assert out["ok"] is False and "SKU" in out["error"] and "UPC" in out["error"]


def test_description_carries_grade_since_only_new_state(monkeypatch):
    # State is always "New" on this marketplace, so grade must be in the text.
    assert bestbuy._description(_product(), _copy()).startswith("Grade A")


def test_shop_sku_short_model_unchanged():
    # Short identities are used as-is (no truncation), uppercase, hyphen-joined.
    assert bestbuy._shop_sku(_product()) == "SAMSUNG-GALAXY-S21-A-BLACK"


def test_shop_sku_long_model_fits_40_and_is_clean_and_stable():
    # A raw inventory Model with a SKU code + parentheses blows past Mirakl's 40-char
    # limit; it must be truncated (with a stable hash) and stripped to [A-Z0-9-].
    p = {"Manufacturer": "Motorola", "Model": "XT2615-1 (Moto G Play (2026)-64GB)",
         "Colour": "Pantone Tapestry", "Grade": "C", "Quantity": 1}
    sku = bestbuy._shop_sku(p)
    assert len(sku) <= 40
    assert re.fullmatch(r"[A-Z0-9-]+", sku)           # no spaces / parens / slashes
    assert bestbuy._shop_sku(p) == sku                # deterministic & stable
    # a different colour -> a different sku (uniqueness preserved via the hash)
    p2 = {**p, "Colour": "Sage Green"}
    assert bestbuy._shop_sku(p2) != sku


@patch("ecommerce.listings.bestbuy.requests")
def test_create_listing_happy_path_builds_offer_and_confirms(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.post.return_value = _resp(201, {"import_id": 7777})
    mock_requests.get.return_value = _resp(200, {"status": "COMPLETE", "lines_in_error": 0})

    out = bestbuy.create_listing(_product(), 299.99, _copy(),
                                 catalog_info={"upc": "999002534166"})
    assert out["ok"] is True
    assert out["listing_id"] == "SAMSUNG-GALAXY-S21-A-BLACK"
    assert out["env"] == "production"

    offer = mock_requests.post.call_args.kwargs["json"]["offers"][0]
    assert offer["shop_sku"] == "SAMSUNG-GALAXY-S21-A-BLACK"
    assert offer["product_id"] == "999002534166"
    assert offer["product_id_type"] == "UPC-A"
    assert offer["state_code"] == "11"
    assert offer["quantity"] == 2
    assert offer["price"] == 299.99
    assert offer["logistic_class"] == "SMALL"
    # Mirakl-required additional field (live-verified rejection without it).
    assert offer["offer_additional_fields"] == [
        {"code": "manufacturer-warranty", "value": "365"}]


@patch("ecommerce.listings.bestbuy.requests")
def test_create_listing_with_product_sku_references_by_sku(mock_requests, monkeypatch):
    # On-the-fly path: a resolved Best Buy product SKU -> product-id-type=SKU (no UPC).
    _creds(monkeypatch)
    mock_requests.post.return_value = _resp(201, {"import_id": 8888})
    mock_requests.get.return_value = _resp(200, {"status": "COMPLETE", "lines_in_error": 0})

    out = bestbuy.create_listing(_product(), 299.99, _copy(),
                                 catalog_info={"product_sku": "15997245"})
    assert out["ok"] is True
    offer = mock_requests.post.call_args.kwargs["json"]["offers"][0]
    assert offer["product_id"] == "15997245"
    assert offer["product_id_type"] == "SKU"


@patch("ecommerce.listings.bestbuy.requests")
def test_product_sku_preferred_over_upc(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.post.return_value = _resp(201, {"import_id": 8889})
    mock_requests.get.return_value = _resp(200, {"status": "COMPLETE", "lines_in_error": 0})
    out = bestbuy.create_listing(_product(), 299.99, _copy(),
                                 catalog_info={"product_sku": "SKU123", "upc": "999002534166"})
    assert out["ok"] is True
    offer = mock_requests.post.call_args.kwargs["json"]["offers"][0]
    assert offer["product_id"] == "SKU123" and offer["product_id_type"] == "SKU"


@patch("ecommerce.listings.bestbuy.requests")
def test_create_listing_rejected_offer_returns_error(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.post.return_value = _resp(201, {"import_id": 8888})
    mock_requests.get.return_value = _resp(200, {"status": "COMPLETE", "lines_in_error": 1})

    out = bestbuy.create_listing(_product(), 299.99, _copy(),
                                 catalog_info={"upc": "999002534166"})
    assert out["ok"] is False and "not accepted" in out["error"]


@patch("ecommerce.listings.bestbuy.requests")
def test_delist_sets_quantity_zero(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.post.return_value = _resp(200, {"import_id": 9999})
    assert bestbuy.delist("SAMSUNG-GALAXY-S21-A-BLACK") is True
    offer = mock_requests.post.call_args.kwargs["json"]["offers"][0]
    assert offer["quantity"] == 0
    assert offer["shop_sku"] == "SAMSUNG-GALAXY-S21-A-BLACK"
