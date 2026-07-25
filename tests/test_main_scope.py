"""Integration test: run_pipeline applies the scrape-scope settings at the single
choke point (right after fetch) so only the scoped products reach scraping/recommend.

Every network/DB touchpoint is mocked — this never scrapes or hits a database.
"""
from unittest.mock import patch

from ecommerce import main as ecom_main


def _p(mfr, model, qty, colour="Blk", grade="A"):
    return {"Manufacturer": mfr, "Model": model, "Colour": colour, "Grade": grade, "Quantity": qty}


@patch("ecommerce.main.db.save_pricing_batch")
@patch("ecommerce.main.db.fetch_device_cost", return_value=100.0)
@patch("ecommerce.main.db.lookup_product_catalog", return_value=None)
@patch("ecommerce.main.reebelo_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.reebelo_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.bestbuy_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.bestbuy_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.ebay_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.ebay_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.amazon_pricing.scrape_prices_by_keyword", return_value={})
@patch("ecommerce.main.recommend")
@patch("ecommerce.main.db.get_scrape_settings")
@patch("ecommerce.main.db.fetch_all_pending_products")
def test_scope_excludes_categories_and_caps_top_n(mock_fetch, mock_settings, mock_recommend, *_):
    mock_fetch.return_value = [
        _p("Apple", "iPhone 15", 12, grade="A"),
        _p("Apple", "iPhone 15", 30, grade="B"),    # same model -> 42 total units
        _p("Samsung", "Galaxy Watch 7", 8),
        _p("Samsung", "Galaxy Buds2 Pro", 99),       # accessory -> excluded by category
        _p("Apple", "iPad Air", 4),                   # tablet -> excluded by category
    ]
    mock_settings.return_value = {"categories": ["phone", "wearable"], "scope_mode": "top", "top_n": 1}
    mock_recommend.return_value = {"margin_ok": False, "skip_reason": "test", "marketplace": "x", "price": 0.0}

    recs = ecom_main.run_pipeline(dry_run=True)

    # categories=[phone,wearable] drops the buds (accessory) and iPad (tablet);
    # top_n=1 by model keeps only iPhone 15 (42 units) — BOTH its colour/grade rows.
    processed = [c.args[0]["Model"] for c in mock_recommend.call_args_list]
    assert set(processed) == {"iPhone 15"}
    assert len(processed) == 2
    assert len(recs) == 2


@patch("ecommerce.main.db.save_pricing_batch")
@patch("ecommerce.main.db.fetch_device_cost", return_value=100.0)
@patch("ecommerce.main.db.lookup_product_catalog", return_value=None)
@patch("ecommerce.main.reebelo_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.reebelo_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.bestbuy_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.bestbuy_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.ebay_pricing.get_floor_price_for_grade", return_value=None)
@patch("ecommerce.main.ebay_pricing.scrape_and_return_all", return_value={})
@patch("ecommerce.main.amazon_pricing.scrape_prices_by_keyword", return_value={})
@patch("ecommerce.main.recommend")
@patch("ecommerce.main.db.get_scrape_settings")
@patch("ecommerce.main.db.fetch_all_pending_products")
def test_cli_limit_overrides_settings_top_n(mock_fetch, mock_settings, mock_recommend, *_):
    mock_fetch.return_value = [
        _p("Apple", "iPhone 15", 12),
        _p("Samsung", "Galaxy S24", 8),
        _p("Google", "Pixel 8", 4),
    ]
    # settings say 'all', but an explicit --limit forces top-N by model.
    mock_settings.return_value = {"categories": ["phone", "wearable", "tablet"], "scope_mode": "all", "top_n": 30}
    mock_recommend.return_value = {"margin_ok": False, "skip_reason": "t", "marketplace": "x", "price": 0.0}

    ecom_main.run_pipeline(limit=2, dry_run=True)

    processed = [c.args[0]["Model"] for c in mock_recommend.call_args_list]
    assert set(processed) == {"iPhone 15", "Galaxy S24"}   # top 2 by count; Pixel dropped
