"""
Ecommerce approval routes — Flask Blueprint.

Serves the pricing dashboard and handles approve/reject actions.

Mode: Per ADO #138 (1D.6), approve now AUTO-POSTS to the marketplace API for
Amazon CA and eBay CA recommendations. Best Buy CA and Reebelo CA stay
preview-only (no API for these per #138 AC). On API failure, the
recommendation is NOT marked as approved so the user can retry.
"""

import logging

from flask import Blueprint, jsonify, redirect, request, session, url_for

import roles
from ecommerce import db
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import bestbuy as bestbuy_listings
from ecommerce.listings import copy_generator
from ecommerce.listings import ebay as ebay_listings
from ecommerce.listings import reebelo as reebelo_listings
from ecommerce.notifications.email_digest import render_batch_list, render_dashboard

log = logging.getLogger(__name__)

approval_bp = Blueprint("ecommerce", __name__, url_prefix="/ecommerce")


@approval_bp.before_request
def _gate_ecommerce():
    role = session.get('role', 'user')
    if session.get('logged_in') and not roles.role_allows(role, 'ecommerce'):
        return redirect(url_for('home'))

# Marketplaces that auto-post on approve. Best Buy CA (Mirakl, 1D.11) posts only
# when a catalog UPC match exists; Reebelo CA (Cobalt, 1D.12) posts only when its
# API key is configured — both fall back to preview-only otherwise. Anything else
# is preview-only — the modal still shows the generated copy for manual paste.
AUTO_POST_MARKETPLACES = {"Amazon CA", "eBay CA", "Amazon", "eBay",
                          "Best Buy CA", "Best Buy", "Reebelo CA", "Reebelo"}

# Map RecommendedMarketplace -> the per-marketplace floor column on
# EcommercePricingRecommendation (for the EcommerceListingsLog audit row).
_FLOOR_COL_BY_MARKETPLACE = {
    "Amazon CA":   "AmazonFloor",
    "Amazon":      "AmazonFloor",
    "eBay CA":     "EbayFloor",
    "eBay":        "EbayFloor",
    "Best Buy CA": "BestBuyFloor",
    "Best Buy":    "BestBuyFloor",
    "Reebelo CA":  "ReebeloFloor",
    "Reebelo":     "ReebeloFloor",
}


def _floor_price_for(marketplace, rec):
    col = _FLOOR_COL_BY_MARKETPLACE.get(marketplace)
    if not col:
        return None
    val = rec.get(col)
    return float(val) if val is not None else None


def _require_login_json():
    """Auth guard for the mutating AJAX endpoints (#198 / 1D.10). Returns a
    401 JSON response if there's no authenticated user, else None. Mirrors the
    JSON-401 pattern in analytics/routes.py."""
    if not session.get("logged_in") or not session.get("username"):
        return jsonify({"ok": False, "error": "Authentication required."}), 401
    return None


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------

@approval_bp.route("/dashboard")
def dashboard_index():
    batches = db.get_all_batches()
    return render_batch_list(batches)


@approval_bp.route("/dashboard/<int:batch_id>")
def dashboard_detail(batch_id):
    batch = db.get_batch_by_id(batch_id)
    if not batch:
        return "<h2>Batch not found.</h2>", 404
    recommendations = db.get_recommendations_for_batch(batch_id)
    return render_dashboard(batch, recommendations)


# ---------------------------------------------------------------------------
# Approve / Reject actions (AJAX from the dashboard)
# ---------------------------------------------------------------------------

def _post_to_marketplace(marketplace, product, price, listing_copy):
    """Dispatch to the right listing module. Returns the {'ok':..., ...} dict
    each module's create_listing() returns. Returns None for preview-only
    marketplaces (caller should treat that as "not auto-posted")."""
    mp = (marketplace or "").lower()
    if mp not in ("amazon ca", "amazon", "ebay ca", "ebay",
                  "best buy ca", "best buy", "reebelo ca", "reebelo"):
        return None  # preview-only

    # Reebelo (Cobalt, 1D.12): lists by our own SKU (no catalog match needed),
    # but stays preview-only until its API key is configured.
    if mp in ("reebelo ca", "reebelo"):
        if not reebelo_listings._have_creds():
            return None
        return reebelo_listings.create_listing(
            product=product, price=price, listing_copy=listing_copy,
        )

    # Single catalog lookup shared by all branches (#198 cleanup).
    catalog = db.lookup_product_catalog(
        product["Manufacturer"], product["Model"], product["Colour"],
    ) or {}

    if mp in ("amazon ca", "amazon"):
        return amazon_listings.create_listing(
            product=product,
            asin=catalog.get("asin"),
            price=price,
            listing_copy=listing_copy,
            device_category=db.lookup_device_category(product["Model"]),
        )

    if mp in ("ebay ca", "ebay"):
        return ebay_listings.create_listing(
            product=product,
            price=price,
            listing_copy=listing_copy,
            catalog_info=catalog,
        )

    # Best Buy (Mirakl, 1D.11): an offer must match a catalog product by UPC.
    # Without one we can't list, so stay preview-only rather than fail approve.
    if not catalog.get("upc"):
        return None
    return bestbuy_listings.create_listing(
        product=product,
        price=price,
        listing_copy=listing_copy,
        catalog_info=catalog,
    )


def _delist_from_marketplace(marketplace, listing_id, product=None):
    """Best-effort rollback of a just-created listing (#198 atomicity). Returns
    True if the marketplace confirmed the delist."""
    mp = (marketplace or "").lower()
    try:
        if mp in ("amazon ca", "amazon"):
            category = db.lookup_device_category(product["Model"]) if product else None
            return amazon_listings.delist(listing_id, device_category=category)
        if mp in ("ebay ca", "ebay"):
            return ebay_listings.delist(listing_id)
        if mp in ("best buy ca", "best buy"):
            return bestbuy_listings.delist(listing_id)
        if mp in ("reebelo ca", "reebelo"):
            return reebelo_listings.delist(listing_id)
    except Exception:
        log.exception("Delist failed for %s listing %s", marketplace, listing_id)
    return False


@approval_bp.route("/approve", methods=["POST"])
def approve():
    """Generate listing copy, auto-post to Amazon/eBay if applicable, log it.

    Auth-guarded and race-safe (#198): the recommendation is atomically claimed
    before any marketplace call, so two near-simultaneous approves can't both
    post. A claim is released back to undecided on any post/log failure, and a
    post that can't be logged is rolled back (delisted) so a live listing never
    exists without a DB record.
    """
    guard = _require_login_json()
    if guard:
        return guard

    rec_id = request.args.get("id", type=int)
    if not rec_id:
        return jsonify({"ok": False, "error": "Missing recommendation ID."}), 400

    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({"ok": False, "error": "Recommendation not found."}), 404
    if rec.get("Decision"):
        return jsonify({"ok": False, "error": f'Already {rec["Decision"]}.'}), 409

    marketplace = rec["RecommendedMarketplace"]
    price = float(rec["RecommendedPrice"])
    product = {
        "Manufacturer": rec["Manufacturer"],
        "Model":        rec["Model"],
        "Colour":       rec["Colour"],
        "Grade":        rec["Grade"],
        "Quantity":     rec["Quantity"],
    }
    approved_by = session.get("username")

    # Step 1: generate the listing copy (always — preview modal needs it).
    try:
        listing_copy = copy_generator.generate_listing_copy(product, marketplace)
    except Exception as e:
        log.error("Listing copy generation failed for rec %s: %s", rec_id, e)
        return jsonify({"ok": False, "error": f"Listing copy generation failed: {e}"}), 500

    auto_post = marketplace in AUTO_POST_MARKETPLACES

    # Step 2: atomically claim the row BEFORE any marketplace call (race guard).
    # Auto-post rows are claimed as 'processing' and only become 'approved' once
    # the post is confirmed (released to NULL on failure, per #138). Preview-only
    # rows are claimed straight to 'approved'.
    claim_state = "processing" if auto_post else "approved"
    if not db.claim_recommendation(rec_id, claim_state):
        return jsonify({"ok": False, "error": "Already being processed or decided."}), 409

    # Step 3: auto-post to marketplace if applicable.
    posted     = False
    listing_id = None
    env        = None
    public_listing_id = None
    listing_url       = None
    if auto_post:
        result = _post_to_marketplace(marketplace, product, price, listing_copy)
        if result is None:
            # Defensive — marketplace was in AUTO_POST set but dispatch returned
            # None. Treat as preview-only: finalize the claim to 'approved'.
            log.warning("Marketplace %r in auto-post set but dispatch returned None.", marketplace)
            db.update_recommendation_decision(rec_id, "approved")
        elif not result.get("ok"):
            # Per #138 AC: post failed -> NOT approved. Release the claim so the
            # row isn't stuck in 'processing' and the user can retry.
            db.release_recommendation(rec_id)
            return jsonify({
                "ok":    False,
                "error": result.get("error") or "Marketplace API post failed.",
            }), 502
        else:
            posted     = True
            listing_id = result.get("listing_id")
            env        = result.get("env")
            public_listing_id = result.get("public_listing_id")
            listing_url       = result.get("listing_url")

    # Step 4: if we posted, log it then finalize. If logging fails after a real
    # post, roll the post back (delist) and release the claim so we never leave
    # a live listing with no DB row.
    if posted and listing_id:
        try:
            db.create_listing_record(
                product=product,
                platform=marketplace,
                listing_price=price,
                floor_price=_floor_price_for(marketplace, rec),
                platform_listing_id=listing_id,
                approved_by=approved_by,
            )
        except Exception:
            log.exception("Posted to %s (listing %s) but failed to log — rolling back.",
                          marketplace, listing_id)
            rolled_back = _delist_from_marketplace(marketplace, listing_id, product)
            db.release_recommendation(rec_id)
            if rolled_back:
                return jsonify({"ok": False, "error": (
                    "Posted but could not record the listing; it was rolled back. "
                    "Please retry."
                )}), 500
            return jsonify({"ok": False, "error": (
                f"Posted to {marketplace} (listing {listing_id}) but could not record it "
                f"and rollback failed — needs manual reconciliation."
            )}), 500
        # Post + log both succeeded -> finalize the claim.
        db.update_recommendation_decision(rec_id, "approved")

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    if posted:
        msg = f"{product_name} approved AND posted to {marketplace} ({env}) at ${price:.2f}."
    else:
        msg = f"{product_name} approved for {marketplace} at ${price:.2f} (preview only — paste manually)."
    return jsonify({
        "ok":          True,
        "message":     msg,
        "listing":     listing_copy,
        "marketplace": marketplace,
        "price":       price,
        "product":     product_name,
        "posted":      posted,
        "listing_id":  listing_id,
        "public_listing_id": public_listing_id,
        "listing_url": listing_url,
        "env":         env,
    })


@approval_bp.route("/reject", methods=["POST"])
def reject():
    guard = _require_login_json()
    if guard:
        return guard

    rec_id = request.args.get("id", type=int)
    if not rec_id:
        return jsonify({"ok": False, "error": "Missing recommendation ID."}), 400

    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({"ok": False, "error": "Recommendation not found."}), 404
    if rec.get("Decision"):
        return jsonify({"ok": False, "error": f'Already {rec["Decision"]}.'}), 409

    # Atomically claim as 'rejected'; loses gracefully to a concurrent decision.
    if not db.claim_recommendation(rec_id, "rejected"):
        return jsonify({"ok": False, "error": "Already being processed or decided."}), 409

    product_name = f"{rec['Manufacturer']} {rec['Model']} Grade {rec['Grade']}"
    return jsonify({"ok": True, "message": f"{product_name} rejected."})
