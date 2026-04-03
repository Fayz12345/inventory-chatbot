"""
eBay Canada price fetching via Octoparse cloud scraping.

Uses the 'ebay-product-list-scraper-by-keyword' template with
product keywords. Extracts floor prices from first-page results.
"""

import logging
import re
from ecommerce.pricing import octoparse_client

log = logging.getLogger(__name__)

TEMPLATE = 'ebay-product-list-scraper-by-keyword'


def _parse_price(price_str):
    """Extract a numeric price from a scraped string like 'C $749.99' or '$749.99'."""
    if not price_str:
        return None
    match = re.search(r'[\d,]+\.?\d*', str(price_str).replace(',', ''))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def scrape_prices(keywords_list):
    """
    Scrape eBay.ca prices for a list of search keywords via Octoparse.

    Args:
        keywords_list: list of keyword strings
                       (e.g. ['iPhone 14 128GB Grade A', 'Samsung S24 256GB Grade B'])

    Returns:
        dict mapping keyword -> lowest price (float), or keyword -> None if not found.
    """
    if not keywords_list:
        return {}

    parameters = {
        '123': 'Canada',
        '6tutxf6k2ik.List': ['ebay.ca'],
        'j4s3pig01g.ExecutedTimesLimitation': '1',  # First page only
        '1x7v90yy9yr.List': keywords_list,
    }

    log.info("Scraping eBay.ca prices for %d keywords...", len(keywords_list))
    rows = octoparse_client.scrape(
        template_name=TEMPLATE,
        parameters=parameters,
        task_name=f'eBay CA Price Scan ({len(keywords_list)} keywords)',
        target_max_rows=len(keywords_list) * 10,  # ~10 results per keyword on page 1
    )

    return _parse_results(rows, keywords_list)


def _parse_results(rows, original_keywords):
    """
    Parse Octoparse export rows into keyword -> floor price mapping.

    The ebay-product-list-scraper-by-keyword template typically returns:
    Keyword, Title, Price, URL, Rating, Image, etc.
    """
    prices = {kw: None for kw in original_keywords}

    for row in rows:
        # Find which keyword this result belongs to
        keyword = None
        for key in ('Keyword', 'keyword', 'Search Keyword', 'search_keyword'):
            if key in row and row[key]:
                keyword = str(row[key]).strip()
                break

        if not keyword:
            continue

        # Match to original keyword (case-insensitive)
        matched_kw = None
        keyword_lower = keyword.lower()
        for orig_kw in original_keywords:
            if orig_kw.lower() == keyword_lower:
                matched_kw = orig_kw
                break

        if not matched_kw:
            continue

        # Extract price
        price = None
        for key in ('Price', 'price', 'Item Price', 'item_price', 'Current Price'):
            if key in row and row[key]:
                price = _parse_price(row[key])
                if price and price > 0:
                    break

        if price and price > 0:
            # Keep the lowest price seen for this keyword
            if prices[matched_kw] is None or price < prices[matched_kw]:
                prices[matched_kw] = price

    for kw, price in prices.items():
        if price:
            log.info("eBay floor price for '%s': $%.2f", kw, price)
        else:
            log.info("eBay: no results for '%s'", kw)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("eBay scrape results: %d/%d keywords with prices.", found, len(original_keywords))
    return prices


def get_prices_for_products(products):
    """
    Fetch eBay floor prices for a list of products.

    Args:
        products: list of dicts with Manufacturer, Model, Grade keys

    Returns:
        dict mapping (Manufacturer, Model, Grade) -> lowest price (float or None)
    """
    keyword_map = {}
    for p in products:
        keywords = f"{p['Manufacturer']} {p['Model']} {p.get('Grade', '')}".strip()
        key = (p['Manufacturer'], p['Model'], p['Grade'])
        keyword_map[keywords] = key

    if not keyword_map:
        return {}

    raw_prices = scrape_prices(list(keyword_map.keys()))

    results = {}
    for keywords, product_key in keyword_map.items():
        results[product_key] = raw_prices.get(keywords)
    return results
