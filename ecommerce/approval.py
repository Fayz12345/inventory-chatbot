"""
Ecommerce approval routes — Flask Blueprint.

Serves the pricing dashboard and handles approve/reject actions.
All state is persisted in SQL Server (EcommercePricingBatch / EcommercePricingRecommendation).
"""

import logging
from flask import Blueprint, request, jsonify

from ecommerce import db
from ecommerce.listings import copy_generator
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import ebay as ebay_listings
from ecommerce.notifications.email_digest import render_batch_list, render_dashboard

log = logging.getLogger(__name__)

approval_bp = Blueprint('ecommerce', __name__, url_prefix='/ecommerce')


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------

@approval_bp.route('/dashboard')
def dashboard_index():
    """List all pricing batches."""
    batches = db.get_all_batches()
    return render_batch_list(batches)


@approval_bp.route('/dashboard/<int:batch_id>')
def dashboard_detail(batch_id):
    """Show recommendations for a single batch."""
    batch = db.get_batch_by_id(batch_id)
    if not batch:
        return '<h2>Batch not found.</h2>', 404
    recommendations = db.get_recommendations_for_batch(batch_id)
    return render_dashboard(batch, recommendations)


# ---------------------------------------------------------------------------
# Approve / Reject actions (called via AJAX from the dashboard)
# ---------------------------------------------------------------------------

@approval_bp.route('/approve', methods=['POST'])
def approve():
    rec_id = request.args.get('id', type=int)
    if not rec_id:
        return jsonify({'ok': False, 'error': 'Missing recommendation ID.'}), 400

    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({'ok': False, 'error': 'Recommendation not found.'}), 404

    if rec.get('Decision'):
        return jsonify({'ok': False, 'error': f'Already {rec["Decision"]}.'}), 409

    marketplace = rec['RecommendedMarketplace']
    price = float(rec['RecommendedPrice'])

    product = {
        'Manufacturer': rec['Manufacturer'],
        'Model': rec['Model'],
        'Colour': rec['Colour'],
        'Grade': rec['Grade'],
        'Quantity': rec['Quantity'],
    }

    # Generate listing copy via Claude
    try:
        listing_copy = copy_generator.generate_listing_copy(product, marketplace)
    except Exception as e:
        log.error("Failed to generate listing copy for rec %s: %s", rec_id, e)
        return jsonify({'ok': False, 'error': f'Listing copy generation failed: {e}'}), 500

    # Look up catalog info for ASIN/EPID
    catalog_info = db.lookup_product_catalog(
        product['Manufacturer'], product['Model'], product['Colour']
    )

    # Post to marketplace
    platform_listing_id = None
    if marketplace == 'Amazon CA':
        asin = catalog_info.get('asin') if catalog_info else None
        if not asin:
            return jsonify({'ok': False, 'error': 'No ASIN in product catalog.'}), 400
        platform_listing_id = amazon_listings.create_listing(product, asin, price, listing_copy)
    elif marketplace == 'eBay CA':
        platform_listing_id = ebay_listings.create_listing(product, price, listing_copy, catalog_info)

    if not platform_listing_id:
        # For Best Buy CA / Reebelo CA there's no auto-listing — just mark approved
        if marketplace not in ('Amazon CA', 'eBay CA'):
            db.update_recommendation_decision(rec_id, 'approved')
            product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
            return jsonify({
                'ok': True,
                'message': f'{product_name} approved for {marketplace} (manual listing required).',
            })
        return jsonify({'ok': False, 'error': 'Marketplace API rejected the listing.'}), 500

    # Log listing to EcommerceListingsLog
    db.create_listing_record(
        product, marketplace, price, price,
        str(platform_listing_id), approved_by='dashboard',
    )
    db.update_recommendation_decision(rec_id, 'approved')

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    return jsonify({
        'ok': True,
        'message': f'{product_name} listed on {marketplace} at ${price:.2f}.',
    })


@approval_bp.route('/reject', methods=['POST'])
def reject():
    rec_id = request.args.get('id', type=int)
    if not rec_id:
        return jsonify({'ok': False, 'error': 'Missing recommendation ID.'}), 400

    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({'ok': False, 'error': 'Recommendation not found.'}), 404

    if rec.get('Decision'):
        return jsonify({'ok': False, 'error': f'Already {rec["Decision"]}.'}), 409

    db.update_recommendation_decision(rec_id, 'rejected')

    product_name = f"{rec['Manufacturer']} {rec['Model']} Grade {rec['Grade']}"
    return jsonify({
        'ok': True,
        'message': f'{product_name} rejected.',
    })
