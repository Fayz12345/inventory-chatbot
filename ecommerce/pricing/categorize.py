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

# Default scope when no settings row exists yet: scrape phones + wearables +
# tablets (skip accessories), all products (no top-N cap).
DEFAULT_CATEGORIES = [PHONE, WEARABLE, TABLET]

_AUDIO_ACCESSORY_KEYS = ("airpod", "buds", "earbud", "earphone", "headphone")
_TABLET_KEYS = ("ipad", "tablet", "galaxy tab", "tab s", "tab a")


def categorize(manufacturer, model):
    """Classify a storefront product into one of CATEGORIES from its Model string.

    Order matters: accessory is checked FIRST so a "watch band" / "watch case" is
    an accessory, not a wearable. Everything unrecognised falls through to `phone`.
    """
    m = (model or "").lower()
    if is_accessory(m) or any(k in m for k in _AUDIO_ACCESSORY_KEYS):
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
