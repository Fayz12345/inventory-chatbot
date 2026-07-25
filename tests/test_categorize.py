"""Unit tests for device categorisation + scrape-scope filtering (ecommerce.pricing.categorize).

Category is inferred from the Model string (inventory has no category column). These lock
the classifier's precedence rules and the top-N-by-model aggregation used by the pipeline.
"""
from ecommerce.pricing import categorize as cz


def _p(mfr, model, qty=1, colour="Blk", grade="A"):
    return {"Manufacturer": mfr, "Model": model, "Colour": colour, "Grade": grade, "Quantity": qty}


def test_categorize_basic():
    assert cz.categorize("Apple", "iPhone 15 128GB") == "phone"
    assert cz.categorize("Samsung", "L315F (Galaxy watch 7 44 MM) LTE") == "wearable"
    assert cz.categorize("Apple", "iPad Air 64GB") == "tablet"
    assert cz.categorize("Samsung", "Galaxy Tab S9") == "tablet"
    assert cz.categorize("Samsung", "Galaxy Buds2 Pro") == "accessory"
    assert cz.categorize("Apple", "AirPods Pro") == "accessory"


def test_categorize_accessory_beats_wearable():
    # "watch band"/"watch case" contain 'watch' but are accessories, not wearables.
    assert cz.categorize("Samsung", "Galaxy Watch band silicone") == "accessory"
    assert cz.categorize("Apple", "Watch case bumper") == "accessory"


def test_categorize_unknown_defaults_to_phone():
    assert cz.categorize("Dell", "XPS 13 Laptop") == "phone"   # documented catch-all default
    assert cz.categorize(None, None) == "phone"


def test_scope_all_keeps_only_selected_categories():
    prods = [_p("Apple", "iPhone 15"), _p("Samsung", "Galaxy Watch 7"), _p("Samsung", "Galaxy Buds2")]
    kept, s = cz.apply_scope(prods, ["phone", "wearable"], "all", None)
    assert "Galaxy Buds2" not in {p["Model"] for p in kept}
    assert s["groups_after"] == 2 and s["models"] == 2
    assert s["by_category"] == {"phone": 1, "wearable": 1}


def test_scope_accessories_excluded_by_default_set():
    prods = [_p("Samsung", "Galaxy Buds2", qty=99), _p("Apple", "iPhone 15", qty=1)]
    kept, _ = cz.apply_scope(prods, ["phone", "wearable", "tablet"], "all", None)
    assert [p["Model"] for p in kept] == ["iPhone 15"]


def test_scope_top_n_by_model_aggregates_variants():
    # iPhone spans two rows (12 + 30 = 42 units) -> outranks watch (8) and tablet (4).
    prods = [
        _p("Apple", "iPhone 15", qty=12, grade="A"),
        _p("Apple", "iPhone 15", qty=30, grade="B"),
        _p("Samsung", "Galaxy Watch 7", qty=8),
        _p("Apple", "iPad Air", qty=4),
    ]
    kept, s = cz.apply_scope(prods, ["phone", "wearable", "tablet"], "top", 1)
    assert s["models"] == 1
    # BOTH iPhone variant rows are kept (one model = one search keyword = one scrape).
    assert len(kept) == 2 and all(p["Model"] == "iPhone 15" for p in kept)


def test_scope_top_n_larger_than_available():
    prods = [_p("Apple", "iPhone 15", qty=5)]
    kept, s = cz.apply_scope(prods, ["phone"], "top", 30)
    assert s["models"] == 1 and len(kept) == 1


def test_scope_empty_categories_keeps_nothing():
    kept, s = cz.apply_scope([_p("Apple", "iPhone 15")], [], "all", None)
    assert kept == [] and s["models"] == 0


def test_scope_empty_products():
    kept, s = cz.apply_scope([], ["phone"], "all", None)
    assert kept == []
    assert s == {"groups_before": 0, "groups_after": 0, "models": 0, "by_category": {}}
