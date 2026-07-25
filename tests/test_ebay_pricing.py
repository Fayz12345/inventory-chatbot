"""Unit tests for eBay pricing (caffein.dev sold-comps).

The read path (actor/field shape) is verified live; these lock the noise filtering
(carrier-locked, parts, accessory, off-model, sub-min, non-CAD) and the median, with
the actor mocked.
"""
from unittest.mock import patch

from ecommerce.pricing import ebay


def _row(title, sold, cur="CAD"):
    return {"title": title, "soldPrice": str(sold), "soldCurrency": cur,
            "condition": "Pre-Owned", "conditionId": 3000, "url": "u", "endedAt": "2026-07-01"}


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_filters_noise_and_takes_median(mock_ac):
    mock_ac.run_actor.return_value = [
        _row("Motorola Moto G Stylus 5G 2024 128GB Unlocked", 120.0),          # keep
        _row("Motorola Moto G Stylus 5G 2024 Unlocked", 150.0),               # keep
        _row("Motorola Moto G Stylus 5G 2024 128GB Unlocked good", 135.0),    # keep
        _row("Motorola Moto G Stylus 5G 2024 128GB DISH", 40.0),              # carrier-locked -> drop
        _row("Motorola Moto G Stylus 5G 2024 for parts only", 210.0),         # parts -> drop
        _row("Case for Motorola Moto G Stylus 5G 2024", 60.0),                # accessory -> drop
        _row("Motorola Moto G Play 2024 128GB Unlocked", 90.0),               # wrong model -> drop
        _row("Motorola Moto G Stylus 5G 2024 Unlocked", 300.0, cur="USD"),    # non-CAD -> drop
    ]
    kw = "Motorola Moto G Stylus 5G 2024"
    res = ebay.scrape_and_return_all([kw])
    assert len(res[kw]) == 3                                    # only the 3 clean unlocked comps
    a = ebay.get_floor_price_for_grade(res, kw, "A")
    c = ebay.get_floor_price_for_grade(res, kw, "C")
    assert (a, c) == (138.6, 129.0) and a > c                  # grade -> percentile of sold [120,135,150]


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_min_price_excludes_cheap(mock_ac):
    mock_ac.run_actor.return_value = [
        _row("Apple iPhone 13 128GB Unlocked", 40.0),          # < min_price 50 -> drop
        _row("Apple iPhone 13 128GB Unlocked", 300.0),
    ]
    res = ebay.scrape_and_return_all(["Apple iPhone 13 128GB"], min_price=50.0)
    assert [i["price"] for i in res["Apple iPhone 13 128GB"]] == [300.0]


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_title_match_rejects_wrong_variant(mock_ac):
    mock_ac.run_actor.return_value = [
        _row("Apple iPhone 13 Pro 128GB Unlocked", 500.0),     # 'pro' qualifier -> drop
        _row("Apple iPhone 13 128GB Unlocked", 350.0),         # match
    ]
    items = ebay.scrape_and_return_all(["Apple iPhone 13 128GB"])["Apple iPhone 13 128GB"]
    assert len(items) == 1 and "Pro" not in items[0]["title"]


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_no_comparable_returns_none(mock_ac):
    mock_ac.run_actor.return_value = [_row("Samsung Galaxy S21 128GB Unlocked", 400.0)]
    res = ebay.scrape_and_return_all(["Apple iPhone 13 128GB"])
    assert ebay.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", "A") is None


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_grades_ordered_and_single_comp(mock_ac):
    mock_ac.run_actor.return_value = [_row("Apple iPhone 13 128GB Unlocked", p)
                                      for p in (100, 150, 200, 250, 300)]
    res = ebay.scrape_and_return_all(["Apple iPhone 13 128GB"])
    g = lambda gr: ebay.get_floor_price_for_grade(res, "Apple iPhone 13 128GB", gr)
    assert g("A+") >= g("A") >= g("B") >= g("C")            # better grade -> higher percentile

    mock_ac.run_actor.return_value = [_row("Apple iPhone 13 128GB Unlocked", 300.0)]
    res1 = ebay.scrape_and_return_all(["Apple iPhone 13 128GB"])
    single = lambda gr: ebay.get_floor_price_for_grade(res1, "Apple iPhone 13 128GB", gr)
    assert single("A+") == single("C") == 300.0            # single comp -> same for all grades


@patch("ecommerce.pricing.ebay.time.sleep", lambda *a: None)
@patch("ecommerce.pricing.ebay.apify_client")
def test_plus_keyword_matches_plus_titles(mock_ac):
    # Regression (Batch #20): "Edge+" lost its "+" in _normalize, so every genuine
    # "Edge Plus" sold comp was over-filtered by the qualifier-parity gate -> 0 comps.
    mock_ac.run_actor.return_value = [
        _row("Motorola Moto Edge Plus 2023 XT2301-1 512GB Unlocked", 375.0),   # keep (Edge Plus)
        _row("Motorola Moto Edge Plus 5G (2023) 512GB Unlocked", 563.83),      # keep (Edge Plus)
        _row("Motorola Moto Edge 5G 2023 512GB Unlocked", 300.0),              # drop (non-plus Edge)
    ]
    kw = "Motorola Moto Edge+ 2023 512GB"
    items = ebay.scrape_and_return_all([kw])[kw]
    assert {i["price"] for i in items} == {375.0, 563.83}      # both Plus comps, non-plus dropped
    assert all("Plus" in i["title"] for i in items)


def test_empty_keywords():
    assert ebay.scrape_and_return_all([]) == {}


def test_excluded_helper():
    assert ebay._excluded("Motorola Moto G Stylus 2024 Rogers")        # carrier
    assert ebay._excluded("iPhone 13 for parts only")                  # parts
    assert not ebay._excluded("Apple iPhone 13 128GB Unlocked")        # clean unlocked
