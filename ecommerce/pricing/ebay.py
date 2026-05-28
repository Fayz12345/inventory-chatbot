"""
eBay Canada price fetching via Apify cloud scraping.

Uses the 'khadinakbar/ebay-all-in-one-scraper' actor. The previous actor
('automation-lab/ebay-scraper') silently ignored its `site` parameter and only
ever returned ebay.com listings in USD; this one targets ebay.ca natively via
`marketplace:"ebay.ca"` and returns CAD prices. It takes a single `searchQuery`
per run, so we call it once per keyword. Results are filtered by condition (to
match the device's internal grade) and by an accessory/parts filter before
taking the floor.
"""

import logging
import re

from ecommerce.pricing import apify_client
from ecommerce.pricing.filters import is_accessory

log = logging.getLogger(__name__)

ACTOR_ID = 'khadinakbar/ebay-all-in-one-scraper'

DEFAULT_MIN_PRICE = 30.0

# Map internal grades to acceptable eBay condition substrings (case-insensitive).
# Vocabulary observed from this actor: "Brand New", "New (Other)", "Pre-Owned",
# "Open Box", "Excellent - Refurbished", "Good - Refurbished", "Used", etc.
GRADE_CONDITION_MAP = {
    'NEW': ['brand new', 'new'],
    'A+': ['open box', 'new (other)', 'excellent', 'like new', 'seller refurbished',
           'certified - refurbished', 'excellent - refurbished'],
    'A': ['open box', 'new (other)', 'excellent', 'like new', 'seller refurbished',
          'certified - refurbished', 'excellent - refurbished'],
    'B': ['very good', 'good - refurbished', 'very good - refurbished',
          'seller refurbished', 'pre-owned', 'used'],
    'C': ['good', 'acceptable', 'good - refurbished', 'pre-owned', 'used'],
}


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


def _condition_matches_grade(ebay_condition, grade):
    """Check if an eBay listing condition is appropriate for our internal grade."""
    if not ebay_condition or not grade:
        return False
    acceptable = GRADE_CONDITION_MAP.get(grade, GRADE_CONDITION_MAP.get('C', []))
    return any(pattern in ebay_condition.lower().strip() for pattern in acceptable)


def scrape_and_return_all(keywords_list, min_price=DEFAULT_MIN_PRICE, max_results=20):
    """
    Scrape eBay.ca for each keyword via Apify (one actor run per keyword, since
    the actor does not echo the source query in its output).

    Returns:
        dict mapping keyword -> list of result dicts (title, price, condition, url).
    """
    grouped = {}
    for keyword in keywords_list:
        grouped[keyword] = _scrape_one(keyword, min_price, max_results)
    return grouped


def _scrape_one(keyword, min_price, max_results):
    run_input = {
        'searchQuery': keyword,
        'mode': 'active',
        'marketplace': 'ebay.ca',
        'maxResults': max_results,
        'condition': 'any',
    }
    if min_price is not None:
        run_input['minPrice'] = int(min_price)

    rows = apify_client.run_actor(ACTOR_ID, run_input)

    results = []
    for row in rows:
        title = row.get('title', '')
        if is_accessory(title):
            continue
        results.append({
            'title': title,
            'price': _parse_price(row.get('price')),
            'condition': row.get('condition', ''),
            'url': row.get('itemUrl', ''),
        })
    log.info("eBay CA: %d usable results for '%s'", len(results), keyword)
    return results


def get_floor_price_for_grade(grouped_results, keyword, grade):
    """
    Lowest eBay.ca price for a keyword filtered by condition matching the grade.

    Returns float (lowest matching price) or None.
    """
    items = grouped_results.get(keyword, [])
    floor_price = None
    for item in items:
        price = item.get('price')
        if not price or price <= 0:
            continue
        if _condition_matches_grade(item.get('condition', ''), grade):
            if floor_price is None or price < floor_price:
                floor_price = price

    if floor_price:
        log.info("eBay CA floor for '%s' Grade %s: $%.2f", keyword, grade, floor_price)
    else:
        log.info("eBay CA: no condition-matched results for '%s' Grade %s", keyword, grade)
    return floor_price
