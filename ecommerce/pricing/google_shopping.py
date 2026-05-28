"""
Best Buy Canada price fetching via Google Shopping scraping.

Uses the 'automation-lab/google-shopping-scraper' actor with country:"ca".
Google Shopping aggregates many Canadian merchants; we attribute results to
Best Buy Canada (including its third-party Marketplace) by merchant name.

Carrier-financing listings (e.g. a "$21.67/mo" Galaxy Watch on a TELUS
contract) are filtered out so a monthly payment never becomes the device floor.

Notes:
- Google Shopping does not expose a usable product_url (Google obscures it).
- It tags currency inconsistently (often "USD" even for country:"ca"); since
  country is ca and the merchants are Canadian, prices are treated as CAD.
- Reebelo is NOT scraped here — Google Shopping never surfaces it. See reebelo.py.
"""

import logging
import re

from ecommerce.pricing import apify_client

log = logging.getLogger(__name__)

ACTOR_ID = 'automation-lab/google-shopping-scraper'

# Seller name patterns for Best Buy attribution (case-insensitive)
BESTBUY_PATTERNS = [
    'best buy canada marketplace',
    'best buy canada',
    'best buy',
    'bestbuy.ca',
    'bestbuy',
]

# Carrier names that mark a contract/financing listing (the shown price is a
# monthly payment, not the device price).
CARRIER_NAMES = [
    'telus', 'koodo', 'bell', 'rogers', 'fido', 'virgin',
    'public mobile', 'chatr', 'freedom',
]
CARRIER_FINANCING_MAX = 50.0


def _parse_price(price_val):
    """Extract a numeric price from a scraped value (string or number)."""
    if price_val is None:
        return None
    if isinstance(price_val, (int, float)):
        return float(price_val) if price_val > 0 else None
    match = re.search(r'[\d,]+\.?\d*', str(price_val).replace(',', ''))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def _match_seller(seller_name, patterns):
    if not seller_name:
        return False
    seller_lower = seller_name.lower().strip()
    return any(pattern in seller_lower for pattern in patterns)


def _is_carrier_financing(title, price):
    """A sub-$50 listing whose title names a carrier is a monthly payment."""
    if price is None or price >= CARRIER_FINANCING_MAX:
        return False
    title_lower = (title or '').lower()
    return any(carrier in title_lower for carrier in CARRIER_NAMES)


def scrape_prices(keywords_list):
    """
    Scrape Google Shopping (country=ca) for Best Buy Canada prices.

    Returns:
        dict mapping keyword -> lowest Best Buy CA price (float) or None.
    """
    if not keywords_list:
        return {}

    log.info("Scraping Google Shopping (CA) for %d keywords (Best Buy)...",
             len(keywords_list))

    run_input = {
        'queries': list(keywords_list),
        'country': 'ca',
        'maxResults': 20,
    }

    rows = apify_client.run_actor(ACTOR_ID, run_input, timeout_secs=900)
    return _parse_results(rows, keywords_list)


def _parse_results(rows, original_keywords):
    """Parse Google Shopping results and attribute Best Buy CA prices."""
    bestbuy_prices = {kw: None for kw in original_keywords}

    for row in rows:
        keyword = None
        for key in ('query', 'searchTerm', 'keyword', 'Keyword',
                    'search_keyword', 'Query'):
            if key in row and row[key]:
                keyword = str(row[key]).strip()
                break
        if not keyword:
            continue

        matched_kw = None
        keyword_lower = keyword.lower()
        for orig_kw in original_keywords:
            if orig_kw.lower() == keyword_lower:
                matched_kw = orig_kw
                break
        if not matched_kw:
            continue

        seller = str(row.get('merchant', '')).strip()
        if not _match_seller(seller, BESTBUY_PATTERNS):
            continue

        price = _parse_price(row.get('priceNumeric') or row.get('price'))
        if not price or price <= 0:
            continue

        if _is_carrier_financing(row.get('title', ''), price):
            log.info("Skipping carrier-financing listing for '%s': $%.2f (%s)",
                     matched_kw, price, seller)
            continue

        if bestbuy_prices[matched_kw] is None or price < bestbuy_prices[matched_kw]:
            bestbuy_prices[matched_kw] = price
            log.info("Best Buy CA price for '%s': $%.2f (%s)",
                     matched_kw, price, seller)

    found = sum(1 for v in bestbuy_prices.values() if v is not None)
    log.info("Google Shopping: Best Buy CA %d/%d keywords with prices.",
             found, len(original_keywords))
    return bestbuy_prices
