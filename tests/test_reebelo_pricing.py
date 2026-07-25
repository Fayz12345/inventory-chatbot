"""Unit tests for the Reebelo pricing module (reebelo.ca catalog search API, grade-aware).

The read path (endpoint/JSON shape) is verified live; these lock title-matching, accessory/min-price
filtering, the grade->condition floor with off-grade fallback, and block handling with the network
mocked. Proxy is disabled in tests (config flag) so requests go 'direct'.
"""
from unittest.mock import MagicMock, patch

from ecommerce.pricing import reebelo
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload if payload is not None else {}
    m.text = str(payload or "")
    return m


def _item(title, cents, condition=None):
    it = {"title": title, "price": cents}
    if condition is not None:
        it["variants"] = [{"name": "Color", "value": "x"}, {"name": "Condition", "value": condition}]
    return it


def _items(*items):
    return {"items": list(items), "total": len(items)}


def _direct(monkeypatch):
    monkeypatch.setattr(config, "REEBELO_USE_APIFY_PROXY", False)


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_grade_condition_floor(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("iPhone 13 - 128GB - Midnight - Unlocked", 55199, "Like New"),   # A+/A
        _item("iPhone 13 - 128GB - Blue - Unlocked", 45000, "Very Good"),       # A/B
        _item("iPhone 13 - 128GB - Pink - Unlocked", 35498, "Good"),            # B/C
    ))
    kw = "Apple iPhone 13 128GB"
    res = reebelo.scrape_and_return_all([kw])
    assert len(res[kw]) == 3
    g = lambda gr: reebelo.get_floor_price_for_grade(res, kw, gr)
    assert g("A+") == 551.99           # only Like New matches A+
    assert g("A") == 450.00            # min(Like New, Very Good)
    assert g("B") == 354.98            # min(Very Good, Good)
    assert g("C") == 354.98            # Good
    assert g("A+") > g("A") > g("B")
    assert mock_requests.get.call_args.kwargs["params"] == {"q": kw}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_condition_match_is_exact_not_substring(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("iPhone 13 - 128GB - Blue - Unlocked", 20000, "Very Good"),   # cheaper, better condition
        _item("iPhone 13 - 128GB - Pink - Unlocked", 40000, "Good"),         # pricier, lower condition
    ))
    kw = "Apple iPhone 13 128GB"
    res = reebelo.scrape_and_return_all([kw])
    # grade C (good/fair) must NOT match 'Very Good' via a 'good' substring
    assert reebelo.get_floor_price_for_grade(res, kw, "C") == 400.00   # the Good, not the $200 Very Good
    assert reebelo.get_floor_price_for_grade(res, kw, "A") == 200.00   # A matches Very Good


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_off_grade_fallback(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("iPhone 13 - 128GB - Blue - Unlocked", 30000, "Fair"),   # only Fair available
    ))
    kw = "Apple iPhone 13 128GB"
    res = reebelo.scrape_and_return_all([kw])
    # A+ has no Fair match -> falls back to the overall floor ($300)
    assert reebelo.get_floor_price_for_grade(res, kw, "A+") == 300.00


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_title_and_qualifier_filtering(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("iPhone 13 mini - 128GB - Pink - Unlocked", 33999, "Good"),    # 'mini' -> excluded
        _item("iPhone 13 Pro - 128GB - Graphite - Unlocked", 62999, "Good"), # 'pro' -> excluded
        _item("iPhone 13 - 128GB - Blue - Unlocked", 35498, "Good"),         # match
    ))
    items = reebelo.scrape_and_return_all(["Apple iPhone 13 128GB"])["Apple iPhone 13 128GB"]
    assert len(items) == 1 and "mini" not in items[0]["title"].lower()


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_accessory_and_min_price_filtered(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("iPhone 13 Phone Case - 128GB look - Blue", 1999, "Good"),     # accessory
        _item("iPhone 13 - 128GB - Blue - screen protector", 899, "Good"),   # accessory
        _item("iPhone 13 - 128GB - Blue - Unlocked", 35500, "Good"),         # real device
    ))
    items = reebelo.scrape_and_return_all(["Apple iPhone 13 128GB"], min_price=30.0)["Apple iPhone 13 128GB"]
    assert len(items) == 1 and items[0]["price"] == 355.00


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_block_retries_then_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(403, {"message": "forbidden"})
    res = reebelo.scrape_and_return_all(["Apple iPhone 13 128GB"])
    assert res == {"Apple iPhone 13 128GB": []}
    assert mock_requests.get.call_count == reebelo.RETRIES + 1
    assert reebelo.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", "A") is None


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_no_match_returns_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        _item("Samsung Galaxy S21 - 128GB - Black", 40000, "Good"),
    ))
    assert reebelo.scrape_and_return_all(["Apple iPhone 13 128GB"])["Apple iPhone 13 128GB"] == []


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_non_json_returns_empty(mock_requests, monkeypatch):
    _direct(monkeypatch)
    bad = MagicMock(); bad.status_code = 200; bad.json.side_effect = ValueError("nope"); bad.text = "<html>"
    mock_requests.get.return_value = bad
    assert reebelo.scrape_and_return_all(["Apple iPhone 13 128GB"]) == {"Apple iPhone 13 128GB": []}


def test_empty_keywords():
    assert reebelo.scrape_and_return_all([]) == {}


def test_condition_helper():
    assert reebelo._condition({"variants": [{"name": "Condition", "value": "Very Good"}]}) == "very good"
    assert reebelo._condition({"variants": [{"name": "Storage", "value": "128GB"}]}) == ""
    assert reebelo._condition({}) == ""
