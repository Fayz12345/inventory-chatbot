import logging
import requests
from ecommerce import config

log = logging.getLogger(__name__)

EBAY_AUTH_URL = 'https://api.ebay.com/identity/v1/oauth2/token'
EBAY_INVENTORY_URL = 'https://api.ebay.com/sell/inventory/v1'


def _get_access_token():
    """Exchange refresh token for a short-lived access token with sell scope."""
    if not config.EBAY_REFRESH_TOKEN:
        log.warning("eBay credentials not configured — skipping")
        return None

    response = requests.post(
        EBAY_AUTH_URL,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        auth=(config.EBAY_APP_ID, config.EBAY_CERT_ID),
        data={
            'grant_type': 'refresh_token',
            'refresh_token': config.EBAY_REFRESH_TOKEN,
            'scope': (
                'https://api.ebay.com/oauth/api_scope/sell.inventory '
                'https://api.ebay.com/oauth/api_scope/sell.account'
            ),
        },
    )
    response.raise_for_status()
    return response.json()['access_token']


def _condition_enum(grade):
    """Map internal grade to eBay condition enum."""
    mapping = {
        'A': 'USED_EXCELLENT',
        'B': 'USED_VERY_GOOD',
        'C': 'USED_GOOD',
    }
    return mapping.get(grade, 'USED_GOOD')


def _condition_id(grade):
    """Map internal grade to eBay condition ID for offers."""
    mapping = {'A': '2500', 'B': '3000', 'C': '4000'}
    return mapping.get(grade, '4000')


def _build_item_specifics(product, catalog_info=None):
    """Build eBay item specifics from product data."""
    specifics = [
        {'name': 'Brand', 'values': [product['Manufacturer']]},
        {'name': 'Model', 'values': [product['Model']]},
        {'name': 'Colour', 'values': [product['Colour']]},
    ]
    return specifics


def create_listing(product, price, listing_copy, catalog_info=None):
    """
    Create an eBay listing (inventory item + offer + publish).

    Args:
        product: dict with Manufacturer, Model, Colour, Grade, Quantity
        price: listing price (float)
        listing_copy: dict with 'title', 'description', 'bullets', 'condition_note'
        catalog_info: optional dict with 'epid', 'upc', 'storage'

    Returns:
        eBay listing ID (str) on success, or None on failure.
    """
    token = _get_access_token()
    if not token:
        return None

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
        'Content-Language': 'en-CA',
    }

    sku = (
        f"{product['Manufacturer']}-{product['Model']}-"
        f"{product['Grade']}-{product['Colour']}"
    ).replace(' ', '-').upper()

    # Step 1: Create or replace inventory item
    description_html = f"<p>{listing_copy['description']}</p>"
    if listing_copy.get('bullets'):
        description_html += '<ul>'
        for bullet in listing_copy['bullets']:
            description_html += f'<li>{bullet}</li>'
        description_html += '</ul>'

    inventory_item = {
        'availability': {
            'shipToLocationAvailability': {
                'quantity': product['Quantity'],
            },
        },
        'condition': _condition_enum(product['Grade']),
        'conditionDescription': listing_copy.get('condition_note', ''),
        'product': {
            'title': listing_copy['title'],
            'description': description_html,
            'aspects': {
                spec['name']: spec['values']
                for spec in _build_item_specifics(product, catalog_info)
            },
        },
    }

    # Add eBay product catalog match if available
    if catalog_info and catalog_info.get('epid'):
        inventory_item['product']['epid'] = catalog_info['epid']
    if catalog_info and catalog_info.get('upc'):
        inventory_item['product']['upc'] = [catalog_info['upc']]

    try:
        # PUT inventory item
        resp = requests.put(
            f'{EBAY_INVENTORY_URL}/inventory_item/{sku}',
            headers=headers,
            json=inventory_item,
        )
        if resp.status_code not in (200, 201, 204):
            log.error("eBay create inventory item failed: %s %s", resp.status_code, resp.text)
            return None

        # Step 2: Create offer
        offer_body = {
            'sku': sku,
            'marketplaceId': config.EBAY_MARKETPLACE_ID,
            'format': 'FIXED_PRICE',
            'listingDescription': description_html,
            'pricingSummary': {
                'price': {'value': str(price), 'currency': 'CAD'},
            },
            'categoryId': config.EBAY_CATEGORY_ID,
            'conditionId': _condition_id(product['Grade']),
            'quantityLimitPerBuyer': 1,
        }

        resp = requests.post(
            f'{EBAY_INVENTORY_URL}/offer',
            headers=headers,
            json=offer_body,
        )
        if resp.status_code not in (200, 201):
            log.error("eBay create offer failed: %s %s", resp.status_code, resp.text)
            return None

        offer_id = resp.json().get('offerId')

        # Step 3: Publish offer
        resp = requests.post(
            f'{EBAY_INVENTORY_URL}/offer/{offer_id}/publish',
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            log.error("eBay publish offer failed: %s %s", resp.status_code, resp.text)
            return None

        listing_id = resp.json().get('listingId', offer_id)
        log.info("eBay listing published: SKU=%s listingId=%s", sku, listing_id)
        return listing_id

    except requests.RequestException as e:
        log.error("eBay API error creating listing for %s: %s", sku, e)
        return None


def delist(listing_id):
    """End an eBay listing by withdrawing the offer."""
    token = _get_access_token()
    if not token:
        return False

    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }

    try:
        resp = requests.post(
            f'{EBAY_INVENTORY_URL}/offer/{listing_id}/withdraw',
            headers=headers,
        )
        if resp.status_code in (200, 204):
            log.info("eBay listing withdrawn: %s", listing_id)
            return True
        else:
            log.error("eBay withdraw failed: %s %s", resp.status_code, resp.text)
            return False
    except requests.RequestException as e:
        log.error("eBay API error delisting %s: %s", listing_id, e)
        return False
