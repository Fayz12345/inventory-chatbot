"""Unit tests for the Reebelo pricing module (reebelo.ca catalog search API).

The read path (endpoint/JSON shape) is verified live; these lock the title-matching,
lowest-price selection, accessory/min-price filtering, and block handling with the
network mocked. Proxy is disabled in tests (config flag) so requests go 'direct'.
"""
from unittest.mock import MagicMock, patch

from ecommerce.pricing import reebelo
from ecommerce import config


def _resp(status, payload=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload or {}
    m.text = str(payload or "")
    return m


def _items(*title_cents):
    return {"items": [{"title": t, "price": c} for (t, c) in title_cents],
            "total": len(title_cents)}


def _direct(monkeypatch):
    monkeypatch.setattr(config, "REEBELO_USE_APIFY_PROXY", False)


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_lowest_matching_price(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        ("iPhone 13 - 128GB - Blue - Unlocked", 35498),
        ("iPhone 13 - 128GB - Midnight - Unlocked", 33999),
    ))
    out = reebelo.scrape_prices(["Apple iPhone 13 128GB"])
    assert out == {"Apple iPhone 13 128GB": 339.99}
    params = mock_requests.get.call_args.kwargs["params"]
    assert params == {"q": "Apple iPhone 13 128GB"}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_title_match_excludes_other_models(mock_requests, monkeypatch):
    _direct(monkeypatch)
    # A cheaper NON-matching model must NOT set the floor for a Pro Max query.
    mock_requests.get.return_value = _resp(200, _items(
        ("iPhone 13 - 128GB - Blue - Unlocked", 30000),                 # excluded (no pro/max/256gb)
        ("iPhone 13 Pro Max - 256GB - Silver - Unlocked", 82999),       # match
    ))
    out = reebelo.scrape_prices(["Apple iPhone 13 Pro Max 256GB"])
    assert out == {"Apple iPhone 13 Pro Max 256GB": 829.99}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_qualifier_excludes_mini_and_pro(mock_requests, monkeypatch):
    _direct(monkeypatch)
    # "iPhone 13 128GB" must NOT match the cheaper 'mini' or the 'Pro' variant.
    mock_requests.get.return_value = _resp(200, _items(
        ("iPhone 13 mini - 128GB - Pink - Unlocked", 33999),   # excluded: 'mini' qualifier
        ("iPhone 13 Pro - 128GB - Graphite - Unlocked", 62999), # excluded: 'pro' qualifier
        ("iPhone 13 - 128GB - Blue - Unlocked", 35498),         # the real match
    ))
    out = reebelo.scrape_prices(["Apple iPhone 13 128GB"])
    assert out == {"Apple iPhone 13 128GB": 354.98}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_accessory_and_min_price_filtered(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        ("iPhone 13 Phone Case - 128GB look - Blue", 1999),   # accessory -> skipped
        ("iPhone 13 - 128GB - screen protector", 899),         # accessory -> skipped
        ("iPhone 13 - 128GB - Blue - Unlocked", 35500),        # real device -> floor
    ))
    out = reebelo.scrape_prices(["Apple iPhone 13 128GB"], min_price=30.0)
    assert out == {"Apple iPhone 13 128GB": 355.00}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_block_retries_then_none(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(403, {"message": "forbidden"})
    out = reebelo.scrape_prices(["Apple iPhone 13 128GB"])
    assert out == {"Apple iPhone 13 128GB": None}
    assert mock_requests.get.call_count == reebelo.RETRIES + 1   # retried on block


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_no_match_returns_none(mock_requests, monkeypatch):
    _direct(monkeypatch)
    mock_requests.get.return_value = _resp(200, _items(
        ("Samsung Galaxy S21 - 128GB - Black", 40000),
    ))
    out = reebelo.scrape_prices(["Apple iPhone 13 128GB"])
    assert out == {"Apple iPhone 13 128GB": None}


@patch("ecommerce.pricing.reebelo.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.reebelo.requests")
def test_non_json_returns_none(mock_requests, monkeypatch):
    _direct(monkeypatch)
    bad = MagicMock(); bad.status_code = 200; bad.json.side_effect = ValueError("nope"); bad.text = "<html>"
    mock_requests.get.return_value = bad
    assert reebelo.scrape_prices(["Apple iPhone 13 128GB"]) == {"Apple iPhone 13 128GB": None}


def test_empty_keywords():
    assert reebelo.scrape_prices([]) == {}
