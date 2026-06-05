"""
Ecommerce approval routes — Flask Blueprint.

Serves the pricing dashboard and handles approve/reject actions.

Mode: Per ADO #138 (1D.6), approve now AUTO-POSTS to the marketplace API for
Amazon CA and eBay CA recommendations. Best Buy CA and Reebelo CA stay
preview-only (no API for these per #138 AC). On API failure, the
recommendation is NOT marked as approved so the user can retry.
"""

import logging

from flask import Blueprint, jsonify, request, session

from ecommerce import db
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import copy_generator
from ecommerce.listings import ebay as ebay_listings
from ecommerce.notifications.email_digest import render_batch_list, render_dashboard

log = logging.getLogger(__name__)

approval_bp = Blueprint("ecommerce", __name__, url_prefix="/ecommerce")

# Marketplaces that auto-post on approve (per #138). Anything else stays
# preview-only — the modal still shows the generated copy for manual paste.
AUTO_POST_MARKETPLACES = {"Amazon CA", "eBay CA", "Amazon", "eBay"}

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

    if mp in ("amazon ca", "amazon"):
        catalog = db.lookup_product_catalog(
            product["Manufacturer"], product["Model"], product["Colour"],
        ) or {}
        return amazon_listings.create_listing(
            product=product,
            asin=catalog.get("asin"),
            price=price,
            listing_copy=listing_copy,
        )

    if mp in ("ebay ca", "ebay"):
        catalog = db.lookup_product_catalog(
            product["Manufacturer"], product["Model"], product["Colour"],
        ) or {}
        return ebay_listings.create_listing(
            product=product,
            price=price,
            listing_copy=listing_copy,
            catalog_info=catalog,
        )

    # Best Buy CA, Reebelo CA, etc. — preview-only per #138 AC.
    return None


@approval_bp.route("/approve", methods=["POST"])
def approve():
    """Generate listing copy, auto-post to Amazon/eBay if applicable, log it."""
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

    # Step 1: generate the listing copy (always — preview modal needs it).
    try:
        listing_copy = copy_generator.generate_listing_copy(product, marketplace)
    except Exception as e:
        log.error("Listing copy generation failed for rec %s: %s", rec_id, e)
        return jsonify({"ok": False, "error": f"Listing copy generation failed: {e}"}), 500

    # Step 2: auto-post to marketplace if it's in the auto-post set.
    posted     = False
    listing_id = None
    env        = None
    if marketplace in AUTO_POST_MARKETPLACES:
        result = _post_to_marketplace(marketplace, product, price, listing_copy)
        if result is None:
            # Defensive — marketplace was in AUTO_POST set but dispatch returned
            # None. Treat as preview-only rather than silently dropping the post.
            log.warning("Marketplace %r in auto-post set but dispatch returned None.", marketplace)
        elif not result.get("ok"):
            # Per #138 AC: API post failed -> recommendation is NOT marked as
            # approved -> error shown in toast.
            return jsonify({
                "ok":    False,
                "error": result.get("error") or "Marketplace API post failed.",
            }), 502
        else:
            posted     = True
            listing_id = result.get("listing_id")
            env        = result.get("env")

    # Step 3: log the listing to EcommerceListingsLog if we auto-posted.
    approved_by = session.get("username") or "unknown"
    try:
        if posted and listing_id:
            db.create_listing_record(
                product=product,
                platform=marketplace,
                listing_price=price,
                floor_price=_floor_price_for(marketplace, rec),
                platform_listing_id=listing_id,
                approved_by=approved_by,
            )
    except Exception as e:
        # Listing already posted to the marketplace at this point; failing to
        # log is bad but shouldn't roll back the post. Log loudly so it's
        # caught in ops.
        log.exception("Posted to %s as %s but failed to log to EcommerceListingsLog: %s",
                      marketplace, listing_id, e)

    # Step 4: mark approved (only reached if auto-post succeeded OR marketplace
    # is preview-only).
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
        "env":         env,
    })


@approval_bp.route("/reject", methods=["POST"])
def reject():
    rec_id = request.args.get("id", type=int)
    if not rec_id:
        return jsonify({"ok": False, "error": "Missing recommendation ID."}), 400

    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({"ok": False, "error": "Recommendation not found."}), 404
    if rec.get("Decision"):
        return jsonify({"ok": False, "error": f'Already {rec["Decision"]}.'}), 409

    db.update_recommendation_decision(rec_id, "rejected")
    product_name = f"{rec['Manufacturer']} {rec['Model']} Grade {rec['Grade']}"
    return jsonify({"ok": True, "message": f"{product_name} rejected."})
