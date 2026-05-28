"""
Reebelo Canada price fetching via Apify cloud scraping.

Uses the custom 'adminbridge/reebelo-ca-scraper' actor (no public Reebelo actor
exists). It takes `searchQueries` (array) + `minPrice` and returns refurbished
device listings with a numeric `price` in CAD, the matched `query`, plus
condition/storage/color. A single batched call works because the actor echoes
the source `query` in every result row.
"""

import logging

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'adminbridge/reebelo-ca-scraper'

DEFAULT_MIN_PRICE = 30.0


def scrape_prices(keywords_list, min_price=DEFAULT_MIN_PRICE, max_results=20):
    """
    Scrape Reebelo CA for the lowest price per keyword.

    Returns:
        dict mapping keyword -> lowest price (float) or None.
    """
    if not keywords_list:
        return {}

    log.info("Scraping Reebelo CA for %d keywords...", len(keywords_list))

    run_input = {
        'searchQueries': list(keywords_list),
        'maxResults': max_results,
    }
    if min_price is not None:
        run_input['minPrice'] = int(min_price)

    rows = apify_client.run_actor(ACTOR_ID, run_input)
    return _parse_results(rows, keywords_list)


def _parse_results(rows, original_keywords):
    prices = {kw: None for kw in original_keywords}

    for row in rows:
        keyword = row.get('query')
        matched_kw = None
        if keyword:
            keyword_lower = str(keyword).strip().lower()
            for orig_kw in original_keywords:
                if orig_kw.lower() == keyword_lower:
                    matched_kw = orig_kw
                    break
        if not matched_kw:
            continue

        if is_accessory(row.get('title', '')):
            continue

        price = row.get('price')
        if not isinstance(price, (int, float)) or price <= 0:
            continue

        if prices[matched_kw] is None or price < prices[matched_kw]:
            prices[matched_kw] = float(price)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Reebelo CA: %d/%d keywords with prices.", found, len(original_keywords))
    return prices
