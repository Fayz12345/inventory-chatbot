"""
Amazon Canada price fetching via Apify cloud scraping.

Uses the 'automation-lab/amazon-scraper' actor to search Amazon.ca by keyword.
The actor's input schema takes `searchQueries` + `marketplace:"CA"` (NOT `asins`
or `country`), and returns products with a numeric `price` in CAD plus `name`.
It does not echo the source query in its output, so we call it once per keyword.

Results are filtered to the SAME device variant we're pricing before the floor is
taken: accessory/part listings are dropped (is_accessory) and every result must
pass `_title_matches` — the same title-token + qualifier-parity gate eBay/Best Buy/
Reebelo use (every model/storage/year token present; plus/pro/max on both sides or
neither). Without it the floor was just the cheapest Amazon result for the keyword
regardless of variant (e.g. a 2022 128GB phone priced as a 2023 512GB one). If
nothing matches the variant we return no price rather than a wrong one.
"""

import logging
import re

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/amazon-scraper'

# Backstop for accessories that slip past the keyword filter (a $9 screen
# protector should never become a phone's floor price). Tunable per call.
DEFAULT_MIN_PRICE = 40.0

# --- Variant matching (copied from ecommerce/pricing/ebay.py; that module's
# _normalize is the canonical one — it maps "+"->"plus" so an "Edge+" keyword
# matches an "Edge Plus" title). Only the variant matcher is copied, NOT eBay's
# carrier/exclude gate: Amazon writes unlocked phones as "AT&T Unlocked", which a
# carrier-name filter would wrongly drop. ---
_BRANDS = {"apple", "samsung", "google", "motorola", "moto", "sonim", "tcl", "huawei",
           "alcatel", "lg", "oneplus", "nokia"}
_MODEL_QUALIFIERS = {"mini", "pro", "max", "plus", "ultra", "se", "fe", "air",
                     "classic", "lite", "neo", "active"}


def _normalize(s):
    # Adapted from eBay's _normalize with an Amazon-specific twist: Amazon writes
    # RAM+storage as "8GB+256GB" / "512GB+12GB" / "128GB + 4GB RAM". That join "+"
    # must become a SPACE, not "plus" — otherwise it injects a spurious "plus" token
    # that breaks the qualifier-parity check (a non-plus phone would look like a
    # "Plus" model, and a plain keyword would wrongly drop the real "…GB + …GB RAM"
    # listing). Only a "+" that is NOT between two GB numbers is the model "+".
    s = (s or "").lower()
    s = re.sub(r"(\d+\s*gb)\s*\+\s*(\d+\s*gb)", r"\1 \2", s)
    # A remaining "+" is a model qualifier ("Edge+"/"S24+") -> keep a "plus" token so
    # it matches "Edge Plus"/"S24 Plus" titles while parity rejects the non-plus model.
    s = s.replace("+", " plus ")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _match_tokens(keyword):
    return [t for t in _normalize(keyword).split() if t not in _BRANDS and len(t) >= 2]


def _title_matches(title, tokens):
    """True if the Amazon title is the same device variant as the keyword: every
    significant keyword token is a substring of the title, and each model qualifier
    (mini/pro/max/plus/...) is present on BOTH sides or NEITHER."""
    if not tokens:
        return False
    norm = _normalize(title)
    if not all(t in norm for t in tokens):
        return False
    kw = set(tokens)
    title_words = set(norm.split())
    for q in _MODEL_QUALIFIERS:
        if (q in kw) != (q in title_words):
            return False
    return True


def _extract_price(row):
    """Amazon Scraper returns a numeric `price` field (CAD for marketplace CA)."""
    val = row.get('price')
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    return None


def scrape_prices_by_keyword(keywords, min_price=DEFAULT_MIN_PRICE, max_products=16):
    """
    Scrape the lowest whole-device Amazon.ca price for each keyword.

    Args:
        keywords: iterable of shopper-style search strings.
        min_price: drop results below this (accessory backstop). None disables.
        max_products: results to request per keyword (16 gives the variant matcher
            enough candidates; the actor is free-tier and Amazon pages hold ~16-48).

    Returns:
        dict mapping keyword -> lowest price (float) or None.
    """
    prices = {}
    for keyword in keywords:
        prices[keyword] = _scrape_one(keyword, min_price, max_products)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Amazon CA: %d/%d keywords with a price.", found, len(prices))
    return prices


def _scrape_one(keyword, min_price, max_products):
    run_input = {
        'searchQueries': [keyword],
        'marketplace': 'CA',
        'maxProductsPerSearch': max_products,
        'maxSearchPages': 1,
        'sort': 'relevance',
        'maxRequestRetries': 3,
    }
    rows = apify_client.run_actor(ACTOR_ID, run_input)

    tokens = _match_tokens(keyword)
    n_matched = 0
    floor = None
    for row in rows:
        title = row.get('name') or row.get('title') or ''
        if is_accessory(title):
            continue
        # Variant gate: only the same device (model + storage + year, with
        # plus/pro/max parity) can set the floor. Drops the wrong-year/-storage/
        # -model results Amazon's relevance search mixes in.
        if not _title_matches(title, tokens):
            continue
        n_matched += 1
        price = _extract_price(row)
        if not price:
            continue
        if min_price is not None and price < min_price:
            continue
        if floor is None or price < floor:
            floor = price

    if floor is not None:
        log.info("Amazon CA price for '%s': $%.2f (%d variant match%s of %d results)",
                 keyword, floor, n_matched, "" if n_matched == 1 else "es", len(rows))
    elif not rows:
        log.info("Amazon CA: no results for '%s'.", keyword)
    elif n_matched == 0:
        log.info("Amazon CA: %d results but none matched the variant '%s' — no price.",
                 len(rows), keyword)
    else:
        log.info("Amazon CA: %d variant match(es) for '%s' but none above $%.0f — no price.",
                 n_matched, keyword, min_price or 0)
    return floor
