"""
Device categorisation + scrape-scope filtering for the weekly pricing pipeline.

The storefront inventory has NO category column (see `ReportingInventoryFlat`), so
each product's category is inferred from its `Model` string. This reuses the same
keyword logic already proven in `ecommerce/listings/ebay.py::_device_type` and the
accessory vocabulary in `ecommerce/pricing/filters.py`.

Used by `ecommerce/main.py` to honour the dashboard "Scrape scope" control
(categories to scrape + all-vs-top-N-by-model), and by the dashboard's
"Preview impact" endpoint. Kept pure (no I/O) so it's cheap to unit-test.
"""

import logging

from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

# Canonical category keys. `phone` is the catch-all default so an unclassifiable
# device (laptop, modem, or a model string we don't recognise) is never silently
# dropped as long as Phones is enabled.
PHONE = "phone"
WEARABLE = "wearable"
TABLET = "tablet"
ACCESSORY = "accessory"
CATEGORIES = (PHONE, WEARABLE, TABLET, ACCESSORY)

# Human-readable labels for the dashboard "Preview impact" breakdown (Task 2).
CATEGORY_LABELS = {
    PHONE: "Phones",
    WEARABLE: "Wearables",
    TABLET: "Tablets",
    ACCESSORY: "Accessories",
}

# Default scope when no settings row exists yet: scrape phones + wearables +
# tablets (skip accessories), all products (no top-N cap).
DEFAULT_CATEGORIES = [PHONE, WEARABLE, TABLET]

_AUDIO_ACCESSORY_KEYS = ("airpod", "buds", "earbud", "earphone", "headphone")
# Item/Bluetooth trackers (Apple AirTag, Samsung Galaxy SmartTag, Motorola Moto
# Tag) are accessories, not phones — otherwise they fall through to the `phone`
# default and inflate the phone scope.
_TRACKER_ACCESSORY_KEYS = ("airtag", "smarttag", "smart tag", "moto tag", "mototag")
_TABLET_KEYS = ("ipad", "tablet", "galaxy tab", "tab s", "tab a")


def categorize(manufacturer, model):
    """Classify a storefront product into one of CATEGORIES from its Model string.

    Order matters: accessory is checked FIRST so a "watch band" / "watch case" is
    an accessory, not a wearable. Everything unrecognised falls through to `phone`.
    """
    m = (model or "").lower()
    if (is_accessory(m) or any(k in m for k in _AUDIO_ACCESSORY_KEYS)
            or any(k in m for k in _TRACKER_ACCESSORY_KEYS)):
        return ACCESSORY
    if "watch" in m:
        return WEARABLE
    if any(k in m for k in _TABLET_KEYS):
        return TABLET
    return PHONE


def _model_key(product):
    """Grouping key for 'top-N by model' — colours/grades of the same device
    collapse to one model (which is one search keyword, i.e. one scrape)."""
    return (product.get("Manufacturer") or "", product.get("Model") or "")


def apply_scope(products, categories, scope_mode="all", top_n=None):
    """Filter `products` down to the chosen scrape scope.

    Args:
        products:   list of dicts with Manufacturer/Model/Colour/Grade/Quantity
                    (as returned by db.fetch_all_pending_products).
        categories: iterable of category keys to KEEP (e.g. ['phone','wearable']).
        scope_mode: 'all' keeps every product in the selected categories;
                    'top' keeps only the highest-volume `top_n` distinct models.
        top_n:      model cap when scope_mode == 'top'.

    Returns:
        (filtered_products, summary) where summary is a dict with
        groups_before / groups_after (row counts), models (distinct kept models),
        and by_category (distinct-model count per kept category).
    """
    products = list(products or [])
    groups_before = len(products)
    allowed = set(categories or [])

    # 1) Category filter.
    kept = [p for p in products if categorize(p.get("Manufacturer"), p.get("Model")) in allowed]

    # 2) Top-N by model (only when asked). Roll up quantity per (Mfr, Model),
    #    rank desc, keep all rows of the top `top_n` models.
    if scope_mode == "top" and top_n and top_n > 0:
        totals = {}
        for p in kept:
            key = _model_key(p)
            totals[key] = totals.get(key, 0) + (p.get("Quantity") or 0)
        # Deterministic ranking: highest quantity first, then by name.
        ranked = sorted(totals, key=lambda k: (-totals[k], k[0], k[1]))
        top_keys = set(ranked[:top_n])
        kept = [p for p in kept if _model_key(p) in top_keys]

    # 3) Summary (distinct-model counts, since scraping is per model/keyword).
    by_category = {}
    seen_models = set()
    for p in kept:
        key = _model_key(p)
        if key in seen_models:
            continue
        seen_models.add(key)
        cat = categorize(p.get("Manufacturer"), p.get("Model"))
        by_category[cat] = by_category.get(cat, 0) + 1

    summary = {
        "groups_before": groups_before,
        "groups_after": len(kept),
        "models": len(seen_models),
        "by_category": by_category,
    }
    return kept, summary


def preview_breakdown(products, categories, scope_mode="all", top_n=None,
                      top_models_cap=50):
    """Rich impact preview for the dashboard's expandable "Scrape scope" card.

    Reuses `apply_scope` for the scoping, then aggregates the kept rows into
    per-category and per-model detail. Scraping is per model/keyword, so a
    "model" here is a distinct (Manufacturer, Model) — colours/grades of the
    same device collapse into one model but each remains a separate inventory
    row ("group").

    Args:
        products:       list of dicts (Manufacturer/Model/Colour/Grade/Quantity).
        categories:     iterable of category keys to KEEP.
        scope_mode:     'all' or 'top' (see apply_scope).
        top_n:          model cap when scope_mode == 'top'.
        top_models_cap: max models returned in `top_models`.

    Returns:
        dict shaped exactly like the /scrape-preview response body minus `ok`:
        total, groups, units, by_category, detail, top_models,
        top_models_truncated.
    """
    kept, summary = apply_scope(products, categories, scope_mode, top_n)

    # Aggregate per distinct (Manufacturer, Model): unit total + row count.
    per_model = {}
    for p in kept:
        key = _model_key(p)
        agg = per_model.get(key)
        if agg is None:
            agg = {
                "manufacturer": p.get("Manufacturer") or "",
                "model": p.get("Model") or "",
                "category": categorize(p.get("Manufacturer"), p.get("Model")),
                "units": 0,
                "groups": 0,
            }
            per_model[key] = agg
        agg["units"] += (p.get("Quantity") or 0)
        agg["groups"] += 1

    # Roll models up into per-category totals.
    cat_totals = {}
    for agg in per_model.values():
        c = cat_totals.setdefault(agg["category"],
                                  {"models": 0, "units": 0, "groups": 0})
        c["models"] += 1
        c["units"] += agg["units"]
        c["groups"] += agg["groups"]

    # detail: one row per category PRESENT in scope, in canonical order.
    detail = [
        {
            "key": cat,
            "label": CATEGORY_LABELS[cat],
            "models": cat_totals[cat]["models"],
            "units": cat_totals[cat]["units"],
            "groups": cat_totals[cat]["groups"],
        }
        for cat in CATEGORIES if cat in cat_totals
    ]

    # top_models: units desc, deterministic tie-break by (manufacturer, model).
    ranked = sorted(per_model.values(),
                    key=lambda a: (-a["units"], a["manufacturer"], a["model"]))
    top_models = [
        {
            "manufacturer": a["manufacturer"],
            "model": a["model"],
            "category": a["category"],
            "units": a["units"],
            "groups": a["groups"],
        }
        for a in ranked[:top_models_cap]
    ]

    return {
        "total": summary["models"],
        "groups": summary["groups_after"],
        "units": sum(a["units"] for a in per_model.values()),
        "by_category": summary["by_category"],
        "detail": detail,
        "top_models": top_models,
        "top_models_truncated": len(per_model) > top_models_cap,
    }
