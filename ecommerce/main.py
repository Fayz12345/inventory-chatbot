"""
Ecommerce AI Pipeline — Daily Orchestrator

Usage:
    python -m ecommerce.main

Runs the full daily pipeline:
    1. Fetch products from Ecommerce Storefront (new + unlisted fallback)
    2. Look up catalog info (ASIN, EPID) for each product group
    3. Fetch competitive prices from Amazon SP-API and eBay Browse API
    4. Run pricing algorithm (highest floor price wins)
    5. Sanity check margins
    6. Reconcile stale listings (delist products no longer in storefront)
    7. Send email digest with approve/reject links
"""

import logging
import sys

from ecommerce import db
from ecommerce.pricing import amazon as amazon_pricing
from ecommerce.pricing import ebay as ebay_pricing
from ecommerce.pricing.algorithm import recommend
from ecommerce.notifications.email_digest import send_digest
from ecommerce.approval import generate_approval_token
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import ebay as ebay_listings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/tmp/ecommerce_pipeline.log'),
    ],
)
log = logging.getLogger(__name__)


def run_reconciliation():
    """Delist any active listings whose products are no longer in Ecommerce Storefront."""
    log.info("Running reconciliation...")
    stale = db.find_stale_listings()
    if not stale:
        log.info("No stale listings found.")
        return

    for listing in stale:
        platform = listing['Platform']
        platform_id = listing['PlatformListingID']
        log.info("Delisting stale %s listing %s (ID=%s)", platform, platform_id, listing['ID'])

        success = False
        if platform == 'Amazon':
            success = amazon_listings.delist(platform_id)
        elif platform == 'eBay':
            success = ebay_listings.delist(platform_id)

        if success:
            db.update_listing_status(listing['ID'], 'ended')
            log.info("Successfully delisted ID=%s", listing['ID'])
        else:
            log.warning("Failed to delist ID=%s — will retry next run", listing['ID'])

    log.info("Reconciliation complete: %d stale listings processed.", len(stale))


def run_pipeline():
    """Execute the full daily ecommerce pipeline."""
    log.info("=" * 60)
    log.info("Ecommerce AI Pipeline — starting daily run")
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

    # Step 2: Look up catalog info and fetch prices
    log.info("Step 2: Looking up catalog info and fetching prices...")
    recommendations = []

    for product in products:
        manufacturer = product['Manufacturer']
        model = product['Model']
        colour = product['Colour']
        grade = product['Grade']

        log.info("Processing: %s %s %s Grade %s (qty: %s)",
                 manufacturer, model, colour, grade, product['Quantity'])

        # Catalog lookup
        catalog = db.lookup_product_catalog(manufacturer, model, colour)

        # Amazon price (needs ASIN from catalog)
        amazon_price = None
        if catalog and catalog.get('asin'):
            amazon_price = amazon_pricing.get_competitive_price(catalog['asin'])
        else:
            log.warning("No ASIN found for %s %s %s — skipping Amazon pricing",
                        manufacturer, model, colour)

        # eBay price (keyword search, no catalog needed)
        keywords = f"{manufacturer} {model} {grade}".strip()
        ebay_price = ebay_pricing.get_floor_price(keywords)

        # Device cost for margin check
        device_cost = db.fetch_device_cost(manufacturer, model, grade)

        # Run pricing algorithm
        rec = recommend(product, amazon_price, ebay_price, device_cost)
        recommendations.append(rec)

        if rec['margin_ok']:
            log.info("  -> Recommend: %s at $%.2f", rec['marketplace'], rec['price'])
        else:
            log.info("  -> Skipped: %s", rec['skip_reason'])

    # Step 3: Reconciliation
    log.info("Step 3: Running reconciliation...")
    run_reconciliation()

    # Step 4: Send email digest
    log.info("Step 4: Sending email digest...")
    token = generate_approval_token(recommendations)
    send_digest(recommendations, token)

    # Summary
    recommended = [r for r in recommendations if r['margin_ok']]
    skipped = [r for r in recommendations if not r['margin_ok']]
    log.info("=" * 60)
    log.info("Pipeline complete: %d recommended, %d skipped",
             len(recommended), len(skipped))
    log.info("=" * 60)


if __name__ == '__main__':
    run_pipeline()
