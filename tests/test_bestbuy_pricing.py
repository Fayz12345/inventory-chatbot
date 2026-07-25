"""Unit tests for the Best Buy pricing module (bestbuy.ca search API).

The read path (endpoint/JSON shape) is verified live; these lock the refurb-only
filter, carrier-financing + accessory exclusion, title matching, grade->condition
floor, and block handling with the network mocked. Proxy is disabled in tests (config
flag) so requests go 'direct'.
"""
from unittest.mock import MagicMock, patch

from ecommerce.pricing import bestbuy
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload if payload is not None else {}
    m.text = str(payload or "")
    return m


def _prod(name, sale=None, reg=None, mkt=True, sku="1"):
    return {"name": name, "salePrice": sale, "regularPrice": reg,
            "isMarketplace": mkt, "sku": sku}


def _search(*prods):
    return {"products": list(prods), "total": len(prods)}


def _direct(monkeypatch):
    monkeypatch.setattr(config, "BESTBUY_USE_APIFY_PROXY", False)


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_keeps_refurb_only_and_grade_floor(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _search(
        _prod("Refurbished (Excellent) - Apple iPhone 13 128GB - Midnight - Unlocked", 429.99, 659.99),
        _prod("Refurbished (Good) - Apple iPhone 13 128GB - Midnight", 380.0, 669.0),
        _prod("Rogers Apple iPhone 13 128GB - Midnight - Monthly Financing", 29.97, 29.97, mkt=False),
        _prod("Open Box - Phone Case for Apple iPhone 13 128GB", 55.0),            # accessory
        _prod("Apple iPhone 13 128GB - Blue - Unlocked", 699.0, 699.0),            # new, not refurb
    ))
    res = bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"])
    items = res["Apple iPhone 13 128GB"]
    assert len(items) == 2 and all("Refurbished" in i["title"] for i in items)
    # grade A -> excellent floor; grade B -> good
    assert bestbuy.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", "A") == 429.99
    assert bestbuy.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", "B") == 380.0
    params = mock_requests.get.call_args.kwargs["params"]
    assert params["query"] == "Apple iPhone 13 128GB" and params["lang"] == "en-CA"


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_title_match_rejects_wrong_variants(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _search(
        _prod("Refurbished (Good) - Samsung Galaxy Watch5 Pro 45mm - Black", 250.0),   # Pro/45mm -> reject
        _prod("Refurbished (Good) - Samsung Galaxy Watch5 44mm - Blue", 132.0),         # match
    ))
    res = bestbuy.scrape_and_return_all(["Samsung Galaxy Watch5 44mm"])
    items = res["Samsung Galaxy Watch5 44mm"]
    assert len(items) == 1 and "44mm" in items[0]["title"]


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_carrier_financing_and_min_price_excluded(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _search(
        _prod("Open Box - Fido Apple iPhone 13 128GB Monthly Financing", 55.0),  # refurb+carrier -> drop
        _prod("Refurbished (Good) - Apple iPhone 13 128GB", 25.0),               # refurb but < min_price
    ))
    res = bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"], min_price=50.0)
    assert res["Apple iPhone 13 128GB"] == []


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_off_grade_fallback_to_overall_floor(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _search(
        _prod("Refurbished (Fair) - Apple iPhone 13 128GB", 300.0),   # only Fair available
    ))
    res = bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"])
    # grade A prefers excellent/open box (none) -> falls back to the overall refurb floor
    assert bestbuy.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", "A") == 300.0


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_block_retries_then_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(403, {"error": "blocked"})
    res = bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"])
    assert res == {"Apple iPhone 13 128GB": []}
    assert mock_requests.get.call_count == bestbuy.RETRIES + 1   # retried on block


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_non_json_returns_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    bad = MagicMock(); bad.status_code = 200; bad.json.side_effect = ValueError("nope"); bad.text = "<html>"
    mock_requests.get.return_value = bad
    assert bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"]) == {"Apple iPhone 13 128GB": []}


@patch("ecommerce.pricing.bestbuy.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.bestbuy.requests")
def test_new_only_returns_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _search(
        _prod("Apple iPhone 13 128GB - Blue - Unlocked", 699.0),   # new, no refurb marker
    ))
    assert bestbuy.scrape_and_return_all(["Apple iPhone 13 128GB"])["Apple iPhone 13 128GB"] == []


def test_empty_keywords():
    assert bestbuy.scrape_and_return_all([]) == {}


def test_floor_no_items_returns_none():
    assert bestbuy.get_floor_price_for_grade({"kw": []}, "kw", "A") is None


def test_condition_extraction():
    assert bestbuy._condition("Refurbished (Excellent) - iPhone") == "excellent"
    assert bestbuy._condition("Refurbished (Good) - x") == "good"
    assert bestbuy._condition("Open Box - x") == "open box"
    assert bestbuy._condition("Pre-Owned x") == "pre-owned"


def test_price_prefers_saleprice():
    assert bestbuy._price({"salePrice": 100.0, "regularPrice": 200.0}) == 100.0
    assert bestbuy._price({"salePrice": None, "regularPrice": 200.0}) == 200.0
    assert bestbuy._price({"salePrice": 0, "regularPrice": 0}) is None
