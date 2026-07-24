"""Unit tests for the Best Buy (Mirakl P11) pricing module.

The read path (auth/base URL) is verified live against the production account;
these lock the UPC validation, the active->all_offers fallback, the floor
computation, and the auth-abort behaviour with the network mocked.
"""
from unittest.mock import MagicMock, patch

from ecommerce.pricing import bestbuy
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = str(payload or "")
    return m


def _offer(price, shipping=0.0, total=None, currency="CAD", active=True):
    o = {"shop_name": "Reseller", "price": price, "min_shipping_price": shipping,
         "currency_iso_code": currency, "active": active, "state_code": "11"}
    if total is not None:
        o["total_price"] = total
    return o


def _p11(offers):
    return {"products": [{"product_sku": "SKU", "product_title": "T",
                          "total_count": len(offers), "offers": offers}]}


def _creds(monkeypatch):
    monkeypatch.setattr(config, "BESTBUY_API_KEY", "test-key")
    monkeypatch.setattr(config, "BESTBUY_API_BASE", "https://marketplace.bestbuy.ca/api")
    monkeypatch.setattr(config, "BESTBUY_PRODUCT_ID_TYPE", "UPC-A")


# --- valid_upc ---------------------------------------------------------------

def test_valid_upc_accepts_real_gtin():
    assert bestbuy.valid_upc("0887276667041")


def test_valid_upc_rejects_placeholder_and_junk():
    for bad in ("999004088797", "", None, "abc", "12345", "88727666704123456"):
        assert not bestbuy.valid_upc(bad), bad


# --- credential / filtering guards ------------------------------------------

def test_no_creds_returns_all_none(monkeypatch):
    monkeypatch.setattr(config, "BESTBUY_API_KEY", "")
    assert bestbuy.fetch_prices(["0887276667041"]) == {"0887276667041": None}


@patch("ecommerce.pricing.bestbuy.requests")
def test_invalid_upcs_skipped_without_network(mock_requests, monkeypatch):
    _creds(monkeypatch)
    assert bestbuy.fetch_prices(["999004088797", "", None, "abc"]) == {}
    mock_requests.get.assert_not_called()


# --- fetch_prices happy paths -----------------------------------------------

@patch("ecommerce.pricing.bestbuy.requests")
def test_active_offers_floor_no_fallback(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.get.return_value = _resp(
        200, _p11([_offer(200.0, total=200.0), _offer(150.0, total=150.0)]))
    out = bestbuy.fetch_prices(["0887276667041"])
    assert out == {"0887276667041": 150.0}
    assert mock_requests.get.call_count == 1        # active had offers, no fallback
    params = mock_requests.get.call_args.kwargs["params"]
    assert params["product_references"] == "UPC-A|0887276667041"
    assert params["all_offers"] == "false"          # string, not a bool


@patch("ecommerce.pricing.bestbuy.requests")
def test_falls_back_to_all_offers_when_no_active(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.get.side_effect = [
        _resp(200, _p11([])),                                    # active: none in stock
        _resp(200, _p11([_offer(129.96, total=129.96, active=False)])),  # all_offers
    ]
    out = bestbuy.fetch_prices(["0887276667041"])
    assert out == {"0887276667041": 129.96}
    assert mock_requests.get.call_count == 2
    assert mock_requests.get.call_args.kwargs["params"]["all_offers"] == "true"


@patch("ecommerce.pricing.bestbuy.requests")
def test_not_in_catalog_returns_none(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.get.return_value = _resp(200, {"products": []})
    assert bestbuy.fetch_prices(["0887276667041"]) == {"0887276667041": None}


@patch("ecommerce.pricing.bestbuy.requests")
def test_dedupes_repeated_upcs(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.get.return_value = _resp(200, _p11([_offer(100.0, total=100.0)]))
    out = bestbuy.fetch_prices(["0887276667041", "0887276667041"])
    assert out == {"0887276667041": 100.0}
    assert mock_requests.get.call_count == 1


@patch("ecommerce.pricing.bestbuy.requests")
def test_auth_error_aborts_run(mock_requests, monkeypatch):
    _creds(monkeypatch)
    mock_requests.get.return_value = _resp(403, {"message": "forbidden"})
    out = bestbuy.fetch_prices(["0887276667041", "0887276667042"])
    assert out == {"0887276667041": None, "0887276667042": None}
    assert mock_requests.get.call_count == 1        # stops after the first 403


# --- floor / price helpers ---------------------------------------------------

def test_offer_price_precedence():
    assert bestbuy._offer_price({"total_price": 100.0, "price": 90.0}) == 100.0
    assert bestbuy._offer_price({"price": 90.0, "min_shipping_price": 5.0}) == 95.0
    assert bestbuy._offer_price({"applicable_pricing": {"price": 80.0}}) == 80.0
    assert bestbuy._offer_price({}) is None


def test_floor_skips_non_cad_and_nonpositive():
    offers = [
        {"total_price": 50.0, "currency_iso_code": "USD"},    # skipped (not CAD)
        {"total_price": 0.0, "currency_iso_code": "CAD"},     # skipped (<= 0)
        {"total_price": 120.0, "currency_iso_code": "CAD"},   # kept
    ]
    assert bestbuy._floor_from_offers(offers) == 120.0
