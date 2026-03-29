import json
import logging
import hashlib
import hmac
import time
from flask import Blueprint, request, jsonify, render_template_string
from ecommerce import config
from ecommerce import db
from ecommerce.listings import copy_generator
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import ebay as ebay_listings

log = logging.getLogger(__name__)

approval_bp = Blueprint('ecommerce', __name__, url_prefix='/ecommerce')

# In-memory store for pending approval batches (keyed by token)
# In production this could be Redis or a DB table, but for ~100 SKUs/day
# and single-server deployment, in-memory is fine.
_pending_batches = {}

TOKEN_EXPIRY_SECONDS = 48 * 3600  # 48 hours


def generate_approval_token(recommendations):
    """
    Store a batch of recommendations and return a signed token.
    Called by main.py after building recommendations.
    """
    timestamp = str(int(time.time()))
    payload = json.dumps([r['product'] for r in recommendations], default=str)
    raw = f"{timestamp}:{payload}"
    token = hmac.new(
        config.ANTHROPIC_API_KEY[:16].encode(),  # use first 16 chars as signing key
        raw.encode(),
        hashlib.sha256,
    ).hexdigest()[:24]

    _pending_batches[token] = {
        'recommendations': recommendations,
        'created_at': int(timestamp),
        'actions': {},  # idx -> 'approved' | 'rejected'
    }
    return token


def _get_batch(token):
    """Retrieve a pending batch and validate it hasn't expired."""
    batch = _pending_batches.get(token)
    if not batch:
        return None, "Invalid or expired approval token."
    if time.time() - batch['created_at'] > TOKEN_EXPIRY_SECONDS:
        del _pending_batches[token]
        return None, "This approval link has expired (48 hours)."
    return batch, None


RESULT_PAGE = """
<!DOCTYPE html>
<html>
<head><style>
    body { font-family: Arial, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #f5f5f5; }
    .card { background: #fff; padding: 40px; border-radius: 8px; text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); max-width: 500px; }
    .success { color: #2e7d32; }
    .error { color: #c62828; }
    .info { color: #1565c0; }
</style></head>
<body>
<div class="card">
    <h2 class="{{ css_class }}">{{ title }}</h2>
    <p>{{ message }}</p>
</div>
</body>
</html>
"""


@approval_bp.route('/approve')
def approve():
    token = request.args.get('token', '')
    idx = request.args.get('idx', type=int)

    batch, error = _get_batch(token)
    if error:
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Error', message=error), 400

    if idx is None or idx < 0 or idx >= len(batch['recommendations']):
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Error', message='Invalid product index.'), 400

    if idx in batch['actions']:
        prev = batch['actions'][idx]
        return render_template_string(RESULT_PAGE, css_class='info',
                                      title='Already Processed',
                                      message=f'This SKU was already {prev}.'), 200

    rec = batch['recommendations'][idx]
    product = rec['product']
    marketplace = rec['marketplace']
    price = rec['price']

    # Generate listing copy
    try:
        listing_copy = copy_generator.generate_listing_copy(product, marketplace)
    except Exception as e:
        log.error("Failed to generate listing copy: %s", e)
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Error',
                                      message=f'Failed to generate listing copy: {e}'), 500

    # Look up catalog info for ASIN/EPID
    catalog_info = db.lookup_product_catalog(
        product['Manufacturer'], product['Model'], product['Colour']
    )

    # Post to marketplace
    platform_listing_id = None
    if marketplace == 'Amazon':
        asin = catalog_info['asin'] if catalog_info else None
        if not asin:
            return render_template_string(RESULT_PAGE, css_class='error',
                                          title='Error',
                                          message='No ASIN found in product catalog for this SKU.'), 400
        platform_listing_id = amazon_listings.create_listing(
            product, asin, price, listing_copy
        )
    elif marketplace == 'eBay':
        platform_listing_id = ebay_listings.create_listing(
            product, price, listing_copy, catalog_info
        )

    if not platform_listing_id:
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Listing Failed',
                                      message='The marketplace API rejected the listing. Check server logs for details.'), 500

    # Log to database
    db.create_listing_record(
        product, marketplace, price, rec.get('price', price),
        str(platform_listing_id), approved_by='email_link',
    )
    batch['actions'][idx] = 'approved'

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    return render_template_string(
        RESULT_PAGE, css_class='success', title='Listing Created',
        message=f'{product_name} listed on {marketplace} at ${price:.2f}.'
    ), 200


@approval_bp.route('/reject')
def reject():
    token = request.args.get('token', '')
    idx = request.args.get('idx', type=int)

    batch, error = _get_batch(token)
    if error:
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Error', message=error), 400

    if idx is None or idx < 0 or idx >= len(batch['recommendations']):
        return render_template_string(RESULT_PAGE, css_class='error',
                                      title='Error', message='Invalid product index.'), 400

    if idx in batch['actions']:
        prev = batch['actions'][idx]
        return render_template_string(RESULT_PAGE, css_class='info',
                                      title='Already Processed',
                                      message=f'This SKU was already {prev}.'), 200

    rec = batch['recommendations'][idx]
    product = rec['product']
    batch['actions'][idx] = 'rejected'

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    return render_template_string(
        RESULT_PAGE, css_class='info', title='Listing Rejected',
        message=f'{product_name} has been rejected and will not be listed.'
    ), 200


@approval_bp.route('/status')
def status():
    """API endpoint to check the status of a batch (for debugging)."""
    token = request.args.get('token', '')
    batch, error = _get_batch(token)
    if error:
        return jsonify({'error': error}), 400
    return jsonify({
        'total': len(batch['recommendations']),
        'actions': batch['actions'],
        'created_at': batch['created_at'],
    })
