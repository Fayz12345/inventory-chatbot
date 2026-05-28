"""
Amazon Canada price fetching via Apify cloud scraping.

Uses the 'automation-lab/amazon-scraper' actor to search Amazon.ca by keyword.
The actor's input schema takes `searchQueries` + `marketplace:"CA"` (NOT `asins`
or `country`), and returns products with a numeric `price` in CAD plus `name`.
It does not echo the source query in its output, so we call it once per keyword.
Accessory/part listings are dropped before computing the floor.
"""

import logging

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/amazon-scraper'

# Backstop for accessories that slip past the keyword filter (a $9 screen
# protector should never become a phone's floor price). Tunable per call.
DEFAULT_MIN_PRICE = 40.0


def _extract_price(row):
    """Amazon Scraper returns a numeric `price` field (CAD for marketplace CA)."""
    val = row.get('price')
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    return None


def scrape_prices_by_keyword(keywords, min_price=DEFAULT_MIN_PRICE, max_products=8):
    """
    Scrape the lowest whole-device Amazon.ca price for each keyword.

    Args:
        keywords: iterable of shopper-style search strings.
        min_price: drop results below this (accessory backstop). None disables.
        max_products: results to request per keyword.

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

    floor = None
    for row in rows:
        title = row.get('name') or row.get('title') or ''
        if is_accessory(title):
            continue
        price = _extract_price(row)
        if not price:
            continue
        if min_price is not None and price < min_price:
            continue
        if floor is None or price < floor:
            floor = price

    if floor is not None:
        log.info("Amazon CA price for '%s': $%.2f", keyword, floor)
    else:
        log.info("Amazon CA: no whole-device price for '%s'", keyword)
    return floor
