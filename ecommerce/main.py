"""
Ecommerce AI Pipeline — Weekly Orchestrator

Usage:
    python -m ecommerce.main

Runs the full weekly pipeline:
    1. Fetch products from Ecommerce Storefront (new + unlisted fallback)
    2. Look up catalog info (ASIN, EPID) for each product group
    3. Scrape competitive prices via Apify (Amazon CA, eBay CA, Google Shopping)
    4. Run pricing algorithm (highest floor price across 4 marketplaces)
    5. Sanity check margins
    6. Persist recommendations to DB (viewable on /ecommerce/dashboard)
"""

import logging
import sys

from ecommerce import db
from ecommerce.pricing import amazon as amazon_pricing
from ecommerce.pricing import ebay as ebay_pricing
from ecommerce.pricing import google_shopping as gs_pricing
from ecommerce.pricing.algorithm import recommend

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/ecommerce_pipeline.log'),
    ],
)
log = logging.getLogger(__name__)


def run_pipeline():
    """Execute the full weekly ecommerce pipeline."""
    log.info("=" * 60)
    log.info("Ecommerce AI Pipeline — starting weekly run")
    log.info("=" * 60)

    # Step 1: Fetch products
    log.info("Step 1: Fetching products from Ecommerce Storefront...")
    products = db.fetch_all_pending_products()
    log.info("Found %d product groups to process.", len(products))

    if not products:
        log.info("No new products to process.")
        log.info("Pipeline complete (no products).")
        return

    # Step 2: Look up catalog info and build scrape inputs
    # Keywords are product names WITHOUT grade — grade is used for condition filtering
    log.info("Step 2: Looking up catalog info...")
    asins = []
    asin_to_product = {}
    search_keywords = set()  # deduplicated product names (no grade)
    amazon_keyword_fallbacks = set()  # keywords for products with no ASIN
    catalog_cache = {}

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        colour = product['Colour']
        keyword = f"{manufacturer} {model}".strip()
        search_keywords.add(keyword)

        # Catalog lookup for Amazon ASIN
        cache_key = (manufacturer, model, colour)
        if cache_key not in catalog_cache:
            catalog = db.lookup_product_catalog(manufacturer, model, colour)
            catalog_cache[cache_key] = catalog
            if catalog and catalog.get('asin'):
                if catalog['asin'] not in asin_to_product:
                    asins.append(catalog['asin'])
                    asin_to_product[catalog['asin']] = (manufacturer, model)
            else:
                log.info("No ASIN for %s %s %s — will use keyword search for Amazon.",
                         manufacturer, model, colour)
                amazon_keyword_fallbacks.add(keyword)

    search_keywords = sorted(search_keywords)
    amazon_keyword_fallbacks = sorted(amazon_keyword_fallbacks)
    log.info("Built %d unique search keywords from %d product groups.", len(search_keywords), len(products))
    if amazon_keyword_fallbacks:
        log.info("%d keywords will use Amazon keyword search (no ASIN).", len(amazon_keyword_fallbacks))

    # Step 3: Scrape prices from all marketplaces via Apify
    log.info("Step 3: Scraping prices via Apify (3 cloud actors)...")

    # Amazon — by ASIN where available, keyword fallback for the rest
    amazon_raw = amazon_pricing.scrape_prices(asins) if asins else {}
    amazon_keyword_raw = amazon_pricing.scrape_prices_by_keyword(amazon_keyword_fallbacks) if amazon_keyword_fallbacks else {}

    # eBay — by keyword, returns all results with condition info
    ebay_results = ebay_pricing.scrape_and_return_all(search_keywords)

    # Google Shopping — by keyword (covers Best Buy + Reebelo)
    bestbuy_raw, reebelo_raw = gs_pricing.scrape_prices(search_keywords)

    # Step 4: Build recommendations
    log.info("Step 4: Running pricing algorithm...")
    recommendations = []

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        grade = product['Grade']
        colour = product['Colour']
        keyword = f"{manufacturer} {model}".strip()

        log.info("Processing: %s %s %s Grade %s (qty: %s)",
                 manufacturer, model, colour, grade, product['Quantity'])

        # Get Amazon price — by ASIN if available, keyword fallback otherwise
        amazon_price = None
        catalog = catalog_cache.get((manufacturer, model, colour))
        if catalog and catalog.get('asin'):
            amazon_price = amazon_raw.get(catalog['asin'])
        else:
            amazon_price = amazon_keyword_raw.get(keyword)

        # Get eBay price — filter by condition matching our grade
        ebay_price = ebay_pricing.get_floor_price_for_grade(ebay_results, keyword, grade)

        # Get Best Buy and Reebelo prices from Google Shopping
        bestbuy_price = bestbuy_raw.get(keyword)
        reebelo_price = reebelo_raw.get(keyword)

        # Device cost for margin check
        device_cost = db.fetch_device_cost(manufacturer, model, grade)

        # Run pricing algorithm across all 4 marketplaces
        rec = recommend(product, amazon_price, ebay_price, bestbuy_price,
                        reebelo_price, device_cost)
        recommendations.append(rec)

        if rec['margin_ok']:
            log.info("  -> Recommend: %s at $%.2f", rec['marketplace'], rec['price'])
        else:
            log.info("  -> Skipped: %s", rec['skip_reason'])

    # Step 5: Persist recommendations to DB
    log.info("Step 5: Saving recommendations to database...")
    batch_id = db.create_pricing_batch()
    for rec in recommendations:
        db.insert_recommendation(batch_id, rec)
    db.update_batch_status(batch_id, 'ready')
    log.info("Batch #%d saved with %d recommendations.", batch_id, len(recommendations))

    # Summary
    recommended = [r for r in recommendations if r['margin_ok']]
    skipped = [r for r in recommendations if not r['margin_ok']]
    log.info("=" * 60)
    log.info("Pipeline complete: %d recommended, %d skipped — view at /ecommerce/dashboard/%d",
             len(recommended), len(skipped), batch_id)
    log.info("=" * 60)


if __name__ == '__main__':
    run_pipeline()
