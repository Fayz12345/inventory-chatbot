#!/usr/bin/env python3
"""
Inspect what the eBay sandbox integration has created (ticket 1D.5 - #137).

Reads creds from `.env` via the same path `listings/ebay.py` uses, then:
  - confirms the refresh token still exchanges for an access token,
  - shows the inventory item + offer(s) for a given SKU,
  - lists merchant locations and business policies (the publish prerequisites).

Usage:
    python scripts/ebay_sandbox_check.py [SKU]

Default SKU is the Samsung test item from the first dry run.
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

import requests
from ecommerce.listings import ebay
from ecommerce import config

SKU = sys.argv[1] if len(sys.argv) > 1 else "SAMSUNG-GALAXY-S21-5G-A-PHANTOM-BLACK"


def main():
    print(f"env={config.EBAY_ENV}  marketplace={config.EBAY_MARKETPLACE_ID}\n")
    try:
        token = ebay._get_access_token()
    except requests.HTTPError as e:
        sys.exit(f"AUTH FAILED {e.response.status_code}: {e.response.text}")
    print("auth: refresh token OK (access token acquired)\n")

    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    inv = ebay._inventory_url()
    acct = inv.replace("/sell/inventory/v1", "/sell/account/v1")

    r = requests.get(f"{inv}/inventory_item/{SKU}", headers=H, timeout=30)
    print(f"inventory_item/{SKU}: {r.status_code}")
    if r.ok:
        d = r.json()
        print("   title:", d.get("product", {}).get("title"))

    r = requests.get(f"{inv}/offer?sku={SKU}&marketplace_id={config.EBAY_MARKETPLACE_ID}",
                     headers=H, timeout=30)
    if r.ok:
        for o in r.json().get("offers", []):
            print(f"   offer {o.get('offerId')}: status={o.get('status')} "
                  f"price={o.get('pricingSummary', {}).get('price')} "
                  f"listingId={o.get('listing', {}).get('listingId', '-')}")

    # Publish prerequisites
    loc = requests.get(f"{inv}/location", headers=H, timeout=30)
    n_loc = len(loc.json().get("locations", [])) if loc.ok else f"ERROR {loc.status_code}"
    print(f"\nmerchant locations: {n_loc}")
    for pol in ("fulfillment_policy", "payment_policy", "return_policy"):
        p = requests.get(f"{acct}/{pol}?marketplace_id={config.EBAY_MARKETPLACE_ID}",
                        headers=H, timeout=30)
        key = pol + "ies" if pol.endswith("y") else pol + "s"
        n = len(p.json().get(key.replace("policyies", "policies"), [])) if p.ok else f"ERROR {p.status_code}"
        print(f"   {pol}: {n}")


if __name__ == "__main__":
    main()
