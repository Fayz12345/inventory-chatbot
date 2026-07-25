"""Unit tests for the dashboard scrape-scope impact preview
(ecommerce.pricing.categorize.preview_breakdown).

These lock the aggregation the /ecommerce/scrape-preview endpoint returns: per
(Manufacturer, Model) unit/group rollups, per-category detail rows, the
units-desc top_models list with its cap/truncation flag, and the empty-scope
zero case. Pure (no I/O), mirroring tests/test_categorize.py.
"""
from ecommerce.pricing import categorize as cz


def _p(mfr, model, qty=1, colour="Blk", grade="A"):
    return {"Manufacturer": mfr, "Model": model, "Colour": colour, "Grade": grade, "Quantity": qty}


def test_units_and_groups_aggregate_per_model():
    # iPhone spans two rows (colour/grade variants): 12 + 30 = 42 units, 2 groups.
    prods = [
        _p("Apple", "iPhone 15", qty=12, grade="A"),
        _p("Apple", "iPhone 15", qty=30, grade="B"),
        _p("Samsung", "Galaxy Watch 7", qty=8),
    ]
    out = cz.preview_breakdown(prods, ["phone", "wearable"], "all", None)

    assert out["total"] == 2          # two distinct models
    assert out["groups"] == 3         # three inventory rows
    assert out["units"] == 50         # 42 + 8
    assert out["by_category"] == {"phone": 1, "wearable": 1}

    iphone = next(m for m in out["top_models"] if m["model"] == "iPhone 15")
    assert iphone["units"] == 42 and iphone["groups"] == 2
    assert iphone["manufacturer"] == "Apple" and iphone["category"] == "phone"


def test_detail_rows_carry_labels_units_and_groups():
    prods = [
        _p("Apple", "iPhone 15", qty=10),
        _p("Apple", "iPhone 15", qty=5, grade="B"),
        _p("Apple", "iPad Air", qty=4),
        _p("Samsung", "Galaxy Watch 7", qty=8),
    ]
    out = cz.preview_breakdown(prods, ["phone", "wearable", "tablet"], "all", None)

    detail = {d["key"]: d for d in out["detail"]}
    assert detail["phone"] == {"key": "phone", "label": "Phones",
                               "models": 1, "units": 15, "groups": 2}
    assert detail["tablet"] == {"key": "tablet", "label": "Tablets",
                                "models": 1, "units": 4, "groups": 1}
    assert detail["wearable"] == {"key": "wearable", "label": "Wearables",
                                  "models": 1, "units": 8, "groups": 1}
    # Only categories present in scope appear (no accessory row here).
    assert "accessory" not in detail


def test_detail_ordered_by_canonical_categories():
    # Input order is wearable, tablet, phone; detail must follow CATEGORIES order.
    prods = [
        _p("Samsung", "Galaxy Watch 7", qty=1),
        _p("Apple", "iPad Air", qty=1),
        _p("Apple", "iPhone 15", qty=1),
    ]
    out = cz.preview_breakdown(prods, ["phone", "wearable", "tablet"], "all", None)
    assert [d["key"] for d in out["detail"]] == ["phone", "wearable", "tablet"]


def test_top_models_sorted_by_units_desc_with_name_tiebreak():
    prods = [
        _p("Apple", "iPhone 15", qty=5),
        _p("Apple", "iPhone 14", qty=5),   # ties on units -> name breaks tie
        _p("Samsung", "Galaxy S24", qty=20),
    ]
    out = cz.preview_breakdown(prods, ["phone"], "all", None)
    ordered = [(m["manufacturer"], m["model"]) for m in out["top_models"]]
    # Galaxy S24 (20) first; then the two 5-unit Apple models by (mfr, model).
    assert ordered == [("Samsung", "Galaxy S24"),
                       ("Apple", "iPhone 14"),
                       ("Apple", "iPhone 15")]


def test_top_models_cap_and_truncation_flag():
    prods = [_p("Apple", f"iPhone {i}", qty=i) for i in range(1, 6)]  # 5 models
    out = cz.preview_breakdown(prods, ["phone"], "all", None, top_models_cap=3)
    assert len(out["top_models"]) == 3
    assert out["top_models_truncated"] is True
    # total still reflects ALL scoped models, not just the capped list.
    assert out["total"] == 5
    # Highest-units models survive the cap (5,4,3).
    assert [m["units"] for m in out["top_models"]] == [5, 4, 3]


def test_top_models_not_truncated_when_within_cap():
    prods = [_p("Apple", f"iPhone {i}", qty=i) for i in range(1, 4)]  # 3 models
    out = cz.preview_breakdown(prods, ["phone"], "all", None, top_models_cap=50)
    assert len(out["top_models"]) == 3
    assert out["top_models_truncated"] is False


def test_empty_category_selection_yields_zeros():
    out = cz.preview_breakdown([_p("Apple", "iPhone 15", qty=9)], [], "all", None)
    assert out["total"] == 0
    assert out["groups"] == 0
    assert out["units"] == 0
    assert out["by_category"] == {}
    assert out["detail"] == []
    assert out["top_models"] == []
    assert out["top_models_truncated"] is False


def test_empty_products_yields_zeros():
    out = cz.preview_breakdown([], ["phone", "wearable"], "all", None)
    assert out["total"] == 0 and out["groups"] == 0 and out["units"] == 0
    assert out["detail"] == [] and out["top_models"] == []


def test_top_scope_mode_limits_models_before_breakdown():
    # top_n=1 keeps only the highest-volume model (iPhone 15 = 42 units).
    prods = [
        _p("Apple", "iPhone 15", qty=12),
        _p("Apple", "iPhone 15", qty=30, grade="B"),
        _p("Samsung", "Galaxy Watch 7", qty=8),
        _p("Apple", "iPad Air", qty=4),
    ]
    out = cz.preview_breakdown(prods, ["phone", "wearable", "tablet"], "top", 1)
    assert out["total"] == 1
    assert out["groups"] == 2           # both iPhone rows kept
    assert out["units"] == 42
    assert out["by_category"] == {"phone": 1}
    assert [m["model"] for m in out["top_models"]] == ["iPhone 15"]


def test_by_category_matches_detail_model_counts():
    prods = [
        _p("Apple", "iPhone 15", qty=1),
        _p("Apple", "iPhone 14", qty=1),
        _p("Samsung", "Galaxy Watch 7", qty=1),
    ]
    out = cz.preview_breakdown(prods, ["phone", "wearable"], "all", None)
    from_detail = {d["key"]: d["models"] for d in out["detail"]}
    assert from_detail == out["by_category"] == {"phone": 2, "wearable": 1}
