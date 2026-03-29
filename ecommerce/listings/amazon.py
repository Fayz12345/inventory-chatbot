import logging
from sp_api.api import ListingsItems
from sp_api.base import Marketplaces, SellingApiException
from ecommerce import config

log = logging.getLogger(__name__)


def _get_credentials():
    return {
        'refresh_token': config.AMAZON_REFRESH_TOKEN,
        'lwa_app_id': config.AMAZON_LWA_APP_ID,
        'lwa_client_secret': config.AMAZON_LWA_CLIENT_SECRET,
    }


def _get_marketplace():
    marketplace_map = {
        'A2EUQ1WTGCTBG2': Marketplaces.CA,
        'ATVPDKIKX0DER': Marketplaces.US,
    }
    return marketplace_map.get(config.AMAZON_MARKETPLACE_ID, Marketplaces.CA)


def _condition_type(grade):
    """Map internal grade to Amazon condition type."""
    return config.GRADE_CONDITION_MAP.get(grade, {}).get('amazon', 'UsedGood')


def create_listing(product, asin, price, listing_copy, seller_sku=None):
    """
    Create or update a used device listing on Amazon against an existing ASIN.

    Args:
        product: dict with Manufacturer, Model, Colour, Grade, Quantity
        asin: Amazon ASIN to list against
        price: listing price (float)
        listing_copy: dict with 'condition_note' from copy_generator
        seller_sku: optional custom SKU; auto-generated if not provided

    Returns:
        seller_sku (str) on success, or None on failure.
    """
    if not config.AMAZON_REFRESH_TOKEN:
        log.warning("Amazon SP-API credentials not configured — skipping listing")
        return None

    if not seller_sku:
        seller_sku = (
            f"{product['Manufacturer']}-{product['Model']}-"
            f"{product['Grade']}-{product['Colour']}"
        ).replace(' ', '-').upper()

    condition = _condition_type(product['Grade'])
    condition_note = listing_copy.get('condition_note', '')

    body = {
        'productType': 'WIRELESS_PHONE',
        'requirements': 'LISTING',
        'attributes': {
            'condition_type': [{'value': condition}],
            'condition_note': [{'value': condition_note}],
            'purchasable_offer': [{
                'currency': 'CAD',
                'our_price': [{'schedule': [{'value_with_tax': price}]}],
            }],
            'fulfillment_availability': [{
                'fulfillment_channel_code': 'DEFAULT',
                'quantity': product['Quantity'],
            }],
        },
    }

    try:
        listings_api = ListingsItems(
            credentials=_get_credentials(),
            marketplace=_get_marketplace(),
        )
        response = listings_api.put_listings_item(
            sellerId=config.AMAZON_SELLER_ID,
            sku=seller_sku,
            body=body,
        )
        status = response.payload.get('status', '')
        if status in ('ACCEPTED', 'VALID'):
            log.info("Amazon listing created: SKU=%s ASIN=%s", seller_sku, asin)
            return seller_sku
        else:
            issues = response.payload.get('issues', [])
            log.error("Amazon listing rejected: %s — issues: %s", seller_sku, issues)
            return None

    except SellingApiException as e:
        log.error("Amazon SP-API error creating listing %s: %s", seller_sku, e)
        return None
    except Exception as e:
        log.error("Unexpected error creating Amazon listing %s: %s", seller_sku, e)
        return None


def delist(seller_sku):
    """Remove a listing from Amazon by setting quantity to 0."""
    if not config.AMAZON_REFRESH_TOKEN:
        log.warning("Amazon SP-API credentials not configured — skipping delist")
        return False

    body = {
        'productType': 'WIRELESS_PHONE',
        'patches': [{
            'op': 'replace',
            'path': '/attributes/fulfillment_availability',
            'value': [{'fulfillment_channel_code': 'DEFAULT', 'quantity': 0}],
        }],
    }

    try:
        listings_api = ListingsItems(
            credentials=_get_credentials(),
            marketplace=_get_marketplace(),
        )
        listings_api.patch_listings_item(
            sellerId=config.AMAZON_SELLER_ID,
            sku=seller_sku,
            body=body,
        )
        log.info("Amazon listing delisted: SKU=%s", seller_sku)
        return True
    except Exception as e:
        log.error("Error delisting Amazon SKU %s: %s", seller_sku, e)
        return False
