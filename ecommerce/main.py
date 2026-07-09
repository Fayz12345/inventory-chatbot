"""
Ecommerce AI Pipeline — Weekly Orchestrator

Usage:
    python -m ecommerce.main

Runs the full weekly pipeline:
    1. Fetch products from Ecommerce Storefront
    2. Build clean shopper-style search queries from Manufacturer + Model
    3. Scrape competitive prices via Apify across 4 CA marketplaces:
         Amazon CA, eBay CA, Best Buy CA (Google Shopping), Reebelo CA
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
from ecommerce.pricing import reebelo as reebelo_pricing
from ecommerce.pricing.algorithm import recommend
from ecommerce.pricing.query import clean_search_query

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/ecommerce_pipeline.log'),
    ],
)
log = logging.getLogger(__name__)


def run_pipeline(limit=None, dry_run=False):
    """Execute the full weekly ecommerce pipeline.

    Args:
        limit: if set, only process the first N product groups (testing / cost control).
        dry_run: if True, scrape and compute recommendations but do NOT persist a
                 batch to the database (returns the recommendations instead).
    """
    log.info("=" * 60)
    log.info("Ecommerce AI Pipeline — starting weekly run%s",
             " (DRY RUN)" if dry_run else "")
    log.info("=" * 60)

    # Step 1: Fetch products
    log.info("Step 1: Fetching products from Ecommerce Storefront...")
    products = db.fetch_all_pending_products()
    if limit:
        products = products[:limit]
        log.info("Limited to first %d product groups (limit=%d).", len(products), limit)
    log.info("Found %d product groups to process.", len(products))

    if not products:
        log.info("No new products to process.")
        log.info("Pipeline complete (no products).")
        return []

    # Step 2: Build clean shopper-style search queries (no SKU codes, no grade)
    log.info("Step 2: Building search queries...")
    search_keywords = sorted({
        clean_search_query(p['Manufacturer'], p['Model'])
        for p in products
        if clean_search_query(p['Manufacturer'], p['Model'])
    })
    log.info("Built %d unique search queries from %d product groups.",
             len(search_keywords), len(products))

    # Step 3: Scrape prices from all 4 marketplaces via Apify
    log.info("Step 3: Scraping prices via Apify (4 marketplaces)...")

    # Amazon CA — keyword search, marketplace CA (one actor run per keyword)
    amazon_raw = amazon_pricing.scrape_prices_by_keyword(search_keywords)

    # eBay CA — keyword search via khadinakbar actor, returns results w/ condition
    ebay_results = ebay_pricing.scrape_and_return_all(search_keywords)

    # Best Buy CA — Google Shopping, attributed by merchant name
    bestbuy_raw = gs_pricing.scrape_prices(search_keywords)

    # Reebelo CA — custom reebelo.ca actor
    reebelo_raw = reebelo_pricing.scrape_prices(search_keywords)

    # Per-marketplace coverage — makes a silent scrape failure (e.g. an actor
    # timeout that the client swallows as []) visible in the run log instead of
    # quietly writing every floor as NULL.
    def _coverage(d):
        return sum(1 for v in d.values() if v is not None)

    n_kw = len(search_keywords)
    coverage = {
        'Amazon': _coverage(amazon_raw),
        'Best Buy': _coverage(bestbuy_raw),
        'Reebelo': _coverage(reebelo_raw),
    }
    log.info("Scrape coverage (of %d keywords): %s", n_kw,
             ', '.join('%s %d' % (k, v) for k, v in coverage.items()))
    for market, hits in coverage.items():
        if hits == 0:
            log.warning("%s returned 0 prices for all %d keywords — likely an actor "
                        "failure/timeout, not 'no listings'. Check the Apify run.",
                        market, n_kw)

    # Step 4: Build recommendations
    log.info("Step 4: Running pricing algorithm...")
    recommendations = []

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        grade = product['Grade']
        colour = product['Colour']
        keyword = clean_search_query(manufacturer, model)

        log.info("Processing: %s %s %s Grade %s (qty: %s)",
                 manufacturer, model, colour, grade, product['Quantity'])

        # Amazon CA — lowest whole-device price for this keyword
        amazon_price = amazon_raw.get(keyword)

        # eBay CA — filter by condition matching our grade
        ebay_price = ebay_pricing.get_floor_price_for_grade(ebay_results, keyword, grade)

        # Best Buy CA + Reebelo CA
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

    # Step 5: Persist recommendations to DB (skipped in dry-run)
    recommended = [r for r in recommendations if r['margin_ok']]
    skipped = [r for r in recommendations if not r['margin_ok']]

    if dry_run:
        log.info("=" * 60)
        log.info("DRY RUN complete: %d recommended, %d skipped (nothing saved).",
                 len(recommended), len(skipped))
        log.info("=" * 60)
        return recommendations

    log.info("Step 5: Saving recommendations to database...")
    batch_id = db.create_pricing_batch()
    for rec in recommendations:
        db.insert_recommendation(batch_id, rec)
    db.update_batch_status(batch_id, 'ready')
    log.info("Batch #%d saved with %d recommendations.", batch_id, len(recommendations))

    log.info("=" * 60)
    log.info("Pipeline complete: %d recommended, %d skipped — view at /ecommerce/dashboard/%d",
             len(recommended), len(skipped), batch_id)
    log.info("=" * 60)
    return recommendations


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Ecommerce pricing pipeline")
    parser.add_argument('--limit', type=int, default=None,
                        help="Only process the first N product groups")
    parser.add_argument('--dry-run', action='store_true',
                        help="Scrape and compute but do not persist a batch")
    args = parser.parse_args()
    run_pipeline(limit=args.limit, dry_run=args.dry_run)
