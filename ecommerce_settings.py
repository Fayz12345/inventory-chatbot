"""Pure helpers (defaults + validation) for the ecommerce scrape-scope settings.

Persistence lives in `ecommerce/db.py` (the `EcommerceScrapeSettings` table on the
bridge SQL Server, alongside the other `Ecommerce*` tables) — the app connects to
that DB everywhere, so there's no local store. Defaults/sanitisation are kept here,
DB-free, so they're trivially unit-testable and shared by the read + write paths.
"""
from ecommerce.pricing.categorize import CATEGORIES, DEFAULT_CATEGORIES

# Used when the settings row doesn't exist yet: scrape phones + wearables + tablets
# (accessories OFF), all products, top_n pre-filled at 30 for when the user picks 'top'.
DEFAULTS = {
    "categories": list(DEFAULT_CATEGORIES),
    "scope_mode": "all",   # 'all' | 'top'
    "top_n": 30,
}


def sanitize(categories, scope_mode, top_n):
    """Coerce raw client input into safe stored values. Returns (categories, scope_mode, top_n)."""
    cats = [c for c in (categories or []) if c in CATEGORIES]
    if not cats:
        cats = list(DEFAULT_CATEGORIES)   # never store an empty selection (would scrape nothing)
    mode = scope_mode if scope_mode in ("all", "top") else "all"
    try:
        n = int(top_n)
    except (ValueError, TypeError):
        n = 30
    n = max(1, min(n, 10000))
    return cats, mode, n
