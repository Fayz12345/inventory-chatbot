"""
Ecommerce AI Pipeline — Weekly Orchestrator

Usage:
    python -m ecommerce.main

Runs the full weekly pipeline:
    1. Fetch products from Ecommerce Storefront (new + unlisted fallback)
    2. Look up catalog info (ASIN, EPID) for each product group
    3. Scrape competitive prices via Octoparse (Amazon CA, eBay CA, Google Shopping)
    4. Run pricing algorithm (highest floor price across 4 marketplaces)
    5. Sanity check margins
    6. Reconcile stale listings (delist products no longer in storefront)
    7. Persist recommendations to DB (viewable on /ecommerce/dashboard)
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
        log.info("No new products to process. Skipping to reconciliation.")
        run_reconciliation()
        log.info("Pipeline complete (no products).")
        return

    # Step 2: Look up catalog info and build scrape inputs
    log.info("Step 2: Looking up catalog info...")
    asins = []
    asin_to_product = {}
    keyword_to_product = {}
    catalog_cache = {}  # (manufacturer, model, colour) -> catalog dict

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        colour = product['Colour']
        grade = product['Grade']
        product_key = (manufacturer, model, grade)
        keywords = f"{manufacturer} {model} {grade}".strip()
        keyword_to_product[keywords] = product_key

        # Catalog lookup for Amazon ASIN (cached for reuse in Step 4)
        cache_key = (manufacturer, model, colour)
        catalog = db.lookup_product_catalog(manufacturer, model, colour)
        catalog_cache[cache_key] = catalog
        if catalog and catalog.get('asin'):
            asins.append(catalog['asin'])
            asin_to_product[catalog['asin']] = product_key
        else:
            log.warning("No ASIN found for %s %s %s — Amazon pricing will be skipped",
                        manufacturer, model, colour)

    # Step 3: Scrape prices from all marketplaces via Octoparse
    log.info("Step 3: Scraping prices via Octoparse (3 cloud tasks)...")

    # Amazon — by ASIN
    amazon_raw = amazon_pricing.scrape_prices(asins) if asins else {}

    # eBay — by keyword
    ebay_raw = ebay_pricing.scrape_prices(list(keyword_to_product.keys()))

    # Google Shopping — by keyword (covers Best Buy + Reebelo)
    bestbuy_raw, reebelo_raw = gs_pricing.scrape_prices(list(keyword_to_product.keys()))

    # Step 4: Build recommendations
    log.info("Step 4: Running pricing algorithm...")
    recommendations = []

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        grade = product['Grade']
        colour = product['Colour']
        product_key = (manufacturer, model, grade)
        keywords = f"{manufacturer} {model} {grade}".strip()

        log.info("Processing: %s %s %s Grade %s (qty: %s)",
                 manufacturer, model, colour, grade, product['Quantity'])

        # Get Amazon price by ASIN
        amazon_price = None
        catalog = catalog_cache.get((manufacturer, model, colour))
        if catalog and catalog.get('asin'):
            amazon_price = amazon_raw.get(catalog['asin'])

        # Get eBay price by keyword
        ebay_price = ebay_raw.get(keywords)

        # Get Best Buy and Reebelo prices from Google Shopping
        bestbuy_price = bestbuy_raw.get(keywords)
        reebelo_price = reebelo_raw.get(keywords)

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
