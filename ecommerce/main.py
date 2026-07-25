"""
Ecommerce AI Pipeline — Weekly Orchestrator

Usage:
    python -m ecommerce.main

Runs the full weekly pipeline:
    1. Fetch products from Ecommerce Storefront
    2. Build clean shopper-style search queries from Manufacturer + Model
    3. Fetch competitive prices across CA marketplaces:
         Amazon CA, eBay CA (Apify), Reebelo CA (reebelo.ca catalog API) +
         Best Buy CA (Mirakl P11 API).
    4. Run pricing algorithm (highest floor price across marketplaces)
    5. Sanity check margins
    6. Persist recommendations to DB (viewable on /ecommerce/dashboard)
"""

import logging
import sys

# Load .env BEFORE importing anything that reads it — ecommerce.config resolves
# marketplace creds (BESTBUY_API_KEY, APIFY_PROXY_PASSWORD, *_USE_APIFY_PROXY, ...)
# from os.environ at import time. The cron runs `python -m ecommerce.main` (not the
# Flask app, which is the only other place that calls load_dotenv), so without this
# every .env value would be empty at run time and Best Buy P11 / the proxy would silently
# no-op. `cd ~/inventory-chatbot` in the cron puts .env on the search path; override=False
# so a real exported env var still wins.
from dotenv import load_dotenv
load_dotenv()

from ecommerce import db
from ecommerce.pricing import amazon as amazon_pricing
from ecommerce.pricing import bestbuy as bestbuy_pricing
from ecommerce.pricing import categorize
from ecommerce.pricing import ebay as ebay_pricing
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
    total_available = len(products)

    # Apply the dashboard "Scrape scope" control (ecommerce_settings): which product
    # categories to scrape (mobile/wearable/tablet/accessory, derived from the Model
    # string) and whether to cap to the top-N highest-volume *models*. A CLI --limit
    # overrides the saved top_n for dev/testing. This single choke point scopes the
    # whole run — every later step (keywords, UPCs, the 4 scrapers, recommendations)
    # derives from `products`. Logged loudly so a scope cut is never silent.
    settings = db.get_scrape_settings()
    cats = settings['categories']
    if limit:
        mode, top_n = 'top', limit
    else:
        mode, top_n = settings['scope_mode'], settings['top_n']
    products, scope = categorize.apply_scope(products, cats, mode, top_n)
    log.info("Scrape scope: %d/%d groups kept | categories=%s mode=%s top_n=%s | %d models %s",
             scope['groups_after'], total_available, cats, mode,
             (top_n if mode == 'top' else '-'), scope['models'], scope['by_category'])
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

    # Step 2b: Resolve Best Buy UPCs per product group. Best Buy uses the Mirakl P11
    # API, which is keyed by UPC (not keyword) — so map each group to its catalog UPC.
    # Groups with no usable UPC in EcommerceProductCatalog get no Best Buy price
    # (logged), the same gap as Amazon's ASIN.
    bestbuy_upc_by_group = {}
    for p in products:
        info = db.lookup_product_catalog(p['Manufacturer'], p['Model'], p['Colour'])
        upc = (info or {}).get('upc')
        if bestbuy_pricing.valid_upc(upc):
            bestbuy_upc_by_group[(p['Manufacturer'], p['Model'], p['Colour'])] = str(upc).strip()
    log.info("Resolved Best Buy UPCs for %d/%d product groups (%d unique UPCs).",
             len(bestbuy_upc_by_group), len(products),
             len(set(bestbuy_upc_by_group.values())))

    # Step 3: Fetch prices (Amazon/eBay via Apify, Best Buy via Mirakl, Reebelo via catalog API)
    log.info("Step 3: Fetching prices (Amazon/eBay via Apify, Best Buy via Mirakl, "
             "Reebelo via catalog API)...")

    # Amazon CA — keyword search, marketplace CA (one actor run per keyword)
    amazon_raw = amazon_pricing.scrape_prices_by_keyword(search_keywords)

    # eBay CA — keyword search via khadinakbar actor, returns results w/ condition
    ebay_results = ebay_pricing.scrape_and_return_all(search_keywords)

    # Best Buy CA — Mirakl P11 seller API, keyed by UPC (read-only, $0 Apify cost)
    bestbuy_raw = bestbuy_pricing.fetch_prices(sorted(set(bestbuy_upc_by_group.values())))

    # Reebelo CA — reebelo.ca first-party catalog API (routed via Apify residential proxy)
    reebelo_raw = reebelo_pricing.scrape_prices(search_keywords)

    # Per-marketplace coverage — makes a silent scrape failure (e.g. an actor
    # timeout or antibot block that the client swallows as []) visible in the run
    # log instead of quietly writing every floor as NULL.
    def _coverage(d):
        return sum(1 for v in d.values() if v is not None)

    n_kw = len(search_keywords)
    # eBay is keyed by keyword -> list of listings; count keywords that returned any.
    ebay_hits = sum(1 for kw in search_keywords if ebay_results.get(kw))
    coverage = {
        'Amazon': _coverage(amazon_raw),
        'eBay': ebay_hits,
        'Reebelo': _coverage(reebelo_raw),
    }
    log.info("Scrape coverage (of %d keywords): %s", n_kw,
             ', '.join('%s %d' % (k, v) for k, v in coverage.items()))
    for market, hits in coverage.items():
        if n_kw and hits == 0:
            log.warning("%s returned prices for 0/%d keywords — likely an actor "
                        "failure/timeout or antibot block, not 'no listings'. "
                        "Check the Apify run.", market, n_kw)
    # eBay antibot warning even on a partial blackout (Batch #17 was ~93 pct empty).
    if n_kw and 0 < ebay_hits < n_kw // 2:
        log.warning("eBay returned listings for only %d/%d keywords (under half) — eBay "
                    "likely antibot-throttled the proxy pool; check the eBay actor runs.",
                    ebay_hits, n_kw)

    # Best Buy CA is UPC-keyed (Mirakl P11), so it has its own denominator.
    bestbuy_hits = _coverage(bestbuy_raw)
    log.info("Best Buy CA (Mirakl P11) coverage: %d/%d UPCs priced.",
             bestbuy_hits, len(bestbuy_raw))
    if bestbuy_raw and bestbuy_hits == 0:
        log.warning("Best Buy returned 0 prices for all %d UPCs — check the Mirakl API "
                    "key/scope, or whether those UPCs exist in Best Buy's catalog.",
                    len(bestbuy_raw))

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

        # Best Buy CA (UPC-keyed via Mirakl P11) + Reebelo CA (keyword-keyed)
        bestbuy_price = bestbuy_raw.get(bestbuy_upc_by_group.get((manufacturer, model, colour)))
        reebelo_price = reebelo_raw.get(keyword)

        # Device cost for margin check
        device_cost = db.fetch_device_cost(manufacturer, model, grade)

        # Run pricing algorithm across the active marketplaces
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
    # Single transactional save over ONE connection (batch + all recs + status
    # 'ready'). The old create/insert-per-row/update opened a DB login per
    # recommendation (~300-400/run); SQL Server throttled that login storm so the
    # final status update failed and large batches were stranded 'pending'
    # (batches #1, #12-#18). One connection + one commit fixes that.
    batch_id = db.save_pricing_batch(recommendations)
    log.info("Batch #%d saved with %d recommendations (status: ready).",
             batch_id, len(recommendations))

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
