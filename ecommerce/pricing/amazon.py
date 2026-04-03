"""
Amazon Canada price fetching via Octoparse cloud scraping.

Uses the 'amazon-product-details-scraper' template with ASINs from
the EcommerceProductCatalog table. Extracts floor prices from scraped data.
"""

import logging
import re
from ecommerce.pricing import octoparse_client

log = logging.getLogger(__name__)

TEMPLATE = 'amazon-product-details-scraper'
# Toronto postal code — localizes Amazon.ca results to Canada
DEFAULT_ZIPCODE = 'M5V 2T6'


def _parse_price(price_str):
    """Extract a numeric price from a scraped string like '$749.99' or 'CDN$ 749.99'."""
    if not price_str:
        return None
    match = re.search(r'[\d,]+\.?\d*', str(price_str).replace(',', ''))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def scrape_prices(asins, zipcode=None):
    """
    Scrape Amazon.ca prices for a list of ASINs via Octoparse.

    Args:
        asins: list of ASIN strings (e.g. ['B0BDJH7M8H', 'B0CHX3QBCH'])
        zipcode: Canadian postal code for localization (defaults to Toronto)

    Returns:
        dict mapping ASIN -> lowest price (float), or ASIN -> None if not found.
    """
    if not asins:
        return {}

    zipcode = zipcode or DEFAULT_ZIPCODE
    parameters = {
        'MainKeys': asins,
        'ZipCode': zipcode,
    }

    log.info("Scraping Amazon.ca prices for %d ASINs...", len(asins))
    rows = octoparse_client.scrape(
        template_name=TEMPLATE,
        parameters=parameters,
        task_name=f'Amazon CA Price Scan ({len(asins)} ASINs)',
        target_max_rows=len(asins),
    )

    return _parse_results(rows, asins)


def _parse_results(rows, original_asins):
    """
    Parse Octoparse export rows into ASIN -> price mapping.

    The amazon-product-details-scraper template typically returns fields like:
    Title, Price, ASIN, Rating, etc. Field names may vary — we search flexibly.
    """
    prices = {asin: None for asin in original_asins}

    for row in rows:
        # Find ASIN in the row (field name varies by template version)
        asin = None
        for key in ('ASIN', 'asin', 'Asin', 'product_asin', 'MainKeys'):
            if key in row and row[key]:
                asin = str(row[key]).strip()
                break

        if not asin or asin not in prices:
            continue

        # Find price (try multiple possible field names)
        price = None
        for key in ('Price', 'price', 'Current Price', 'current_price',
                     'Sale Price', 'sale_price', 'Deal Price'):
            if key in row and row[key]:
                price = _parse_price(row[key])
                if price and price > 0:
                    break

        if price and price > 0:
            # Keep the lowest price seen for this ASIN
            if prices[asin] is None or price < prices[asin]:
                prices[asin] = price
                log.info("Amazon price for %s: $%.2f", asin, price)

    found = sum(1 for v in prices.values() if v is not None)
    log.info("Amazon scrape results: %d/%d ASINs with prices.", found, len(original_asins))
    return prices


def get_prices_for_products(products_with_asins, zipcode=None):
    """
    Fetch Amazon floor prices for a list of products.

    Args:
        products_with_asins: list of dicts, each with at least 'asin' key
        zipcode: optional Canadian postal code

    Returns:
        dict mapping asin -> lowest price (float or None)
    """
    asins = [p['asin'] for p in products_with_asins if p.get('asin')]
    if not asins:
        log.warning("No ASINs provided — skipping Amazon pricing.")
        return {}
    return scrape_prices(asins, zipcode)
