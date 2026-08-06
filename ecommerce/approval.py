"""
Ecommerce approval routes — Flask Blueprint.

Serves the pricing dashboard and handles approve/post/mark-listed/reject actions.

Mode: **Approve generates the listing PREVIEW only** — no status change, no
marketplace call — so the operator reviews the copy first. Posting is a
separate, explicit action:
  - POST /post — auto-post to the recommendation's marketplace API (only when
    that marketplace is configured); atomically claimed + logged, with delist
    rollback if logging fails, and 502 (claim released) on API failure so the
    user can retry.
  - POST /mark-listed — record a MANUAL listing for a marketplace with no API,
    so the recommendation is still clearable after a manual copy/paste.
Both finalize the recommendation to 'approved'; /reject sets 'rejected'.
"""

import logging

from flask import Blueprint, jsonify, redirect, request, session, url_for

import admin_audit
import roles
from ecommerce import config
from ecommerce import db
from ecommerce.pricing import categorize
from ecommerce.pricing import bestbuy as bestbuy_pricing
from ecommerce.pricing.query import clean_search_query
from ecommerce.listings import amazon as amazon_listings
from ecommerce.listings import bestbuy as bestbuy_listings
from ecommerce.listings import copy_generator
from ecommerce.listings import ebay as ebay_listings
from ecommerce.listings import reebelo as reebelo_listings
from ecommerce.notifications.email_digest import render_batch_list, render_dashboard

log = logging.getLogger(__name__)

approval_bp = Blueprint("ecommerce", __name__, url_prefix="/ecommerce")


# Endpoints that self-guard with _require_login_json (they answer the AJAX
# caller with a JSON 401). The before_request gate must NOT bounce these to the
# HTML login page — an XHR expects a JSON body, not a 302 redirect.
_SELF_GUARDED_JSON_ENDPOINTS = {
    "ecommerce.scrape_settings_save",
    "ecommerce.scrape_preview",
    "ecommerce.approve",
    "ecommerce.post_listing",
    "ecommerce.mark_listed",
    "ecommerce.view_listing",
    "ecommerce.reject",
}


@approval_bp.before_request
def _gate_ecommerce():
    # Unauthenticated: send page requests to the login screen. The JSON/AJAX
    # endpoints fall through to their own _require_login_json guard so they
    # still answer with a 401 JSON body instead of an HTML redirect.
    if not session.get('logged_in'):
        if request.endpoint in _SELF_GUARDED_JSON_ENDPOINTS:
            return None
        return redirect(url_for('login'))
    role = roles.effective_role(session.get('role'), session.get('is_admin'))
    if not roles.role_allows(role, 'ecommerce'):
        return redirect(url_for('home'))

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
    return render_batch_list(batches, db.get_scrape_settings())


@approval_bp.route("/dashboard/<int:batch_id>")
def dashboard_detail(batch_id):
    batch = db.get_batch_by_id(batch_id)
    if not batch:
        return "<h2>Batch not found.</h2>", 404
    recommendations = db.get_recommendations_for_batch(batch_id)
    return render_dashboard(batch, recommendations)


# ---------------------------------------------------------------------------
# Scrape-scope settings (AJAX from the dashboard's "Scrape scope" card)
# ---------------------------------------------------------------------------

@approval_bp.route("/scrape-settings", methods=["POST"])
def scrape_settings_save():
    """Persist which categories to scrape + all-vs-top-N. The weekly cron
    (ecommerce/main.py) reads this on its next run — nothing runs now."""
    guard = _require_login_json()
    if guard:
        return guard
    data = request.get_json(silent=True) or {}
    saved = db.save_scrape_settings(
        data.get("categories"), data.get("scope_mode"), data.get("top_n"),
        actor=session.get("username"))
    admin_audit.log_action(
        session.get("username"), "ecommerce_scrape_settings",
        detail="categories=%s mode=%s top_n=%s" % (
            saved["categories"], saved["scope_mode"], saved["top_n"]))
    return jsonify({"ok": True, "settings": saved})


@approval_bp.route("/scrape-preview")
def scrape_preview():
    """Impact preview for the scope card: how many distinct models the current
    selection would scrape, broken down by category. On-demand only (a live
    inventory query), so it never slows the dashboard's initial load."""
    guard = _require_login_json()
    if guard:
        return guard
    cats = [c for c in (request.args.get("categories") or "").split(",")
            if c in categorize.CATEGORIES]
    mode = request.args.get("scope_mode")
    mode = mode if mode in ("all", "top", "top_sku") else "all"
    try:
        top_n = int(request.args.get("top_n") or 30)
    except (TypeError, ValueError):
        top_n = 30
    products = db.fetch_all_pending_products()
    return jsonify({"ok": True,
                    **categorize.preview_breakdown(products, cats, mode, top_n)})


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

    # Best Buy (Mirakl, 1D.11): an offer must reference a Best Buy catalog product.
    # Prefer a seeded UPC; otherwise resolve the product SKU on the fly from the same
    # bestbuy.ca search used for pricing (Mirakl accepts product-id-type=SKU), so no
    # UPC seeding is needed. Only stay preview-only if neither can be resolved.
    sku = None
    if not catalog.get("upc"):
        sku = bestbuy_pricing.find_product_sku(
            clean_search_query(product["Manufacturer"], product["Model"]),
            colour=product.get("Colour"),
        )
    if not (catalog.get("upc") or sku):
        return None
    return bestbuy_listings.create_listing(
        product=product,
        price=price,
        listing_copy=listing_copy,
        catalog_info={**catalog, "product_sku": sku},
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


# ---------------------------------------------------------------------------
# Availability + shared recommendation loaders
# ---------------------------------------------------------------------------

def listing_availability(marketplace, catalog=None):
    """Whether we can auto-post to `marketplace` right now — the single source of
    truth for the modal's Auto-post button and the /post pre-check. Returns
    ``{"available": bool, "reason": str, "env": str|None}``.

    eBay additionally requires the publishOffer prerequisites (merchant location
    + the 3 business policies). Best Buy needs only credentials — its product SKU is
    resolved on the fly at post time, so no catalog UPC is required (the `catalog`
    param is accepted for signature compatibility but no longer gates Best Buy).
    """
    mp = (marketplace or "").lower()

    if mp in ("amazon ca", "amazon"):
        if not amazon_listings._have_creds():
            return {"available": False, "reason": "Amazon SP-API not configured.",
                    "env": config.AMAZON_ENV}
        return {"available": True, "reason": "", "env": config.AMAZON_ENV}

    if mp in ("ebay ca", "ebay"):
        if not ebay_listings._have_creds():
            return {"available": False, "reason": "eBay API not configured.",
                    "env": config.EBAY_ENV}
        if not all([config.EBAY_MERCHANT_LOCATION_KEY, config.EBAY_FULFILLMENT_POLICY_ID,
                    config.EBAY_PAYMENT_POLICY_ID, config.EBAY_RETURN_POLICY_ID]):
            return {"available": False,
                    "reason": "eBay publish prerequisites missing (merchant location + 3 business policies).",
                    "env": config.EBAY_ENV}
        return {"available": True, "reason": "", "env": config.EBAY_ENV}

    if mp in ("reebelo ca", "reebelo"):
        if not reebelo_listings._have_creds():
            return {"available": False, "reason": "Reebelo API not configured.",
                    "env": config.REEBELO_ENV}
        return {"available": True, "reason": "", "env": config.REEBELO_ENV}

    if mp in ("best buy ca", "best buy"):
        # Best Buy Mirakl is production-only (no sandbox).
        if not bestbuy_listings._have_creds():
            return {"available": False, "reason": "Best Buy API not configured.",
                    "env": "production"}
        # No catalog UPC required — the Best Buy product SKU is resolved on the fly
        # from the pricing search at post time (a Best Buy win implies a real product).
        return {"available": True, "reason": "", "env": "production"}

    return {"available": False, "reason": f"No listing API for {marketplace}.", "env": None}


def _catalog_for(product):
    return db.lookup_product_catalog(
        product["Manufacturer"], product["Model"], product["Colour"],
    ) or {}


def _product_from_rec(rec):
    return {
        "Manufacturer": rec["Manufacturer"],
        "Model":        rec["Model"],
        "Colour":       rec["Colour"],
        "Grade":        rec["Grade"],
        "Quantity":     rec["Quantity"],
    }


def _load_undecided_rec():
    """Load the recommendation named by ?id=, guarding missing id / not found /
    already decided. Returns (rec, None) or (None, (json_response, status))."""
    rec_id = request.args.get("id", type=int)
    if not rec_id:
        return None, (jsonify({"ok": False, "error": "Missing recommendation ID."}), 400)
    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return None, (jsonify({"ok": False, "error": "Recommendation not found."}), 404)
    if rec.get("Decision"):
        return None, (jsonify({"ok": False, "error": f'Already {rec["Decision"]}.'}), 409)
    return rec, None


def _valid_listing_copy(obj):
    """Accept a client-echoed preview copy only if it matches the generator's
    shape (title/description/bullets/condition_note); else None so the caller
    regenerates. Each field is bounded so a tampered client can't post a blob."""
    if not isinstance(obj, dict):
        return None
    title = obj.get("title"); desc = obj.get("description")
    bullets = obj.get("bullets"); cond = obj.get("condition_note")
    if not isinstance(title, str) or not isinstance(desc, str):
        return None
    if not isinstance(bullets, list) or not all(isinstance(b, str) for b in bullets):
        return None
    return {
        "title":          title[:200],
        "description":    desc[:2000],
        "bullets":        [b[:200] for b in bullets][:10],
        "condition_note": cond[:500] if isinstance(cond, str) else "",
    }


@approval_bp.route("/approve", methods=["POST"])
def approve():
    """Generate the listing PREVIEW for a recommendation — no status change and
    no marketplace call. Posting is a separate, explicit action (/post or
    /mark-listed) so the operator reviews the copy first; approve is safely
    re-runnable while the rec is undecided. Returns the copy plus
    `can_post`/`post_reason`/`env` so the modal shows an Auto-post or a
    Mark-as-listed button."""
    guard = _require_login_json()
    if guard:
        return guard

    rec, err = _load_undecided_rec()
    if err:
        return err

    marketplace = rec["RecommendedMarketplace"]
    price = float(rec["RecommendedPrice"])
    product = _product_from_rec(rec)

    try:
        listing_copy = copy_generator.generate_listing_copy(product, marketplace)
    except Exception as e:
        log.error("Listing copy generation failed for rec %s: %s", rec["ID"], e)
        return jsonify({"ok": False, "error": f"Listing copy generation failed: {e}"}), 500

    # Best Buy availability depends on a catalog UPC match; skip the lookup otherwise.
    catalog = _catalog_for(product) if marketplace.lower() in ("best buy ca", "best buy") else None
    avail = listing_availability(marketplace, catalog=catalog)

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    return jsonify({
        "ok":          True,
        "listing":     listing_copy,
        "marketplace": marketplace,
        "price":       price,
        "product":     product_name,
        "can_post":    avail["available"],
        "post_reason": avail["reason"],
        "env":         avail["env"],
    })


@approval_bp.route("/post", methods=["POST"])
def post_listing():
    """Auto-post an already-previewed recommendation to its marketplace API.

    Atomically claims the row, posts, logs to EcommerceListingsLog, finalizes to
    'approved' — with delist rollback if logging fails. 502 (claim released) on a
    marketplace failure so the user can retry; 400 if the marketplace has no API.
    Prefers the exact copy the operator reviewed (echoed from the modal) and
    regenerates only if it's absent/malformed.
    """
    guard = _require_login_json()
    if guard:
        return guard

    rec, err = _load_undecided_rec()
    if err:
        return err

    marketplace = rec["RecommendedMarketplace"]
    price = float(rec["RecommendedPrice"])
    product = _product_from_rec(rec)
    approved_by = session.get("username")

    listing_copy = _valid_listing_copy((request.get_json(silent=True) or {}).get("listing"))
    if listing_copy is None:
        try:
            listing_copy = copy_generator.generate_listing_copy(product, marketplace)
        except Exception as e:
            log.error("Listing copy generation failed for rec %s: %s", rec["ID"], e)
            return jsonify({"ok": False, "error": f"Listing copy generation failed: {e}"}), 500

    # Atomic claim BEFORE any marketplace call (race guard).
    if not db.claim_recommendation(rec["ID"], "processing"):
        return jsonify({"ok": False, "error": "Already being processed or decided."}), 409

    result = _post_to_marketplace(marketplace, product, price, listing_copy)
    if result is None:
        # No API path for this marketplace (or Best Buy has no catalog match) —
        # the button shouldn't have been offered; caller should Mark-as-listed.
        db.release_recommendation(rec["ID"])
        return jsonify({"ok": False,
                        "error": f"No listing API available for {marketplace}."}), 400
    if not result.get("ok"):
        db.release_recommendation(rec["ID"])
        return jsonify({"ok": False,
                        "error": result.get("error") or "Marketplace API post failed."}), 502

    listing_id        = result.get("listing_id")
    env               = result.get("env")
    public_listing_id = result.get("public_listing_id")
    listing_url       = result.get("listing_url")
    if not listing_id:
        db.release_recommendation(rec["ID"])
        return jsonify({"ok": False, "error": "Marketplace returned no listing id."}), 502

    # Log then finalize; roll the post back (delist) if logging fails so we never
    # leave a live listing with no DB row.
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
        db.release_recommendation(rec["ID"])
        if rolled_back:
            return jsonify({"ok": False, "error": (
                "Posted but could not record the listing; it was rolled back. Please retry."
            )}), 500
        return jsonify({"ok": False, "error": (
            f"Posted to {marketplace} (listing {listing_id}) but could not record it "
            f"and rollback failed — needs manual reconciliation."
        )}), 500
    db.update_recommendation_decision(rec["ID"], "approved")
    # Persist the live-listing link (and ids) inside the saved copy so the "View"
    # modal can re-show a clickable link anytime later — no schema change needed.
    listing_copy["_meta"] = {
        "listing_url":         listing_url,
        "public_listing_id":   public_listing_id,
        "platform_listing_id": listing_id,
        "env":                 env,
    }
    db.save_listing_copy(rec["ID"], listing_copy)  # so it can be re-viewed later

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    try:
        admin_audit.log_action(
            approved_by, 'ecommerce_post',
            target=f"{product['Manufacturer']} {product['Model']} {product.get('Colour', '')} Grade {product['Grade']}".strip(),
            detail=f"${price:.2f} on {marketplace} — posted ({env}), listing {listing_id}",
        )
    except Exception:
        log.exception("Audit logging failed for ecommerce post (rec %s)", rec["ID"])

    return jsonify({
        "ok":                True,
        "posted":            True,
        "message":           f"{product_name} posted to {marketplace} ({env}) at ${price:.2f}.",
        "marketplace":       marketplace,
        "listing_id":        listing_id,
        "public_listing_id": public_listing_id,
        "listing_url":       listing_url,
        "env":               env,
    })


@approval_bp.route("/mark-listed", methods=["POST"])
def mark_listed():
    """Resolve a recommendation as MANUALLY listed (no marketplace API call) — for
    marketplaces with no configured API. Records a manual EcommerceListingsLog row
    (PlatformListingID='manual') and finalizes the decision to 'approved'."""
    guard = _require_login_json()
    if guard:
        return guard

    rec, err = _load_undecided_rec()
    if err:
        return err

    marketplace = rec["RecommendedMarketplace"]
    price = float(rec["RecommendedPrice"])
    product = _product_from_rec(rec)
    approved_by = session.get("username")
    listing_copy = _valid_listing_copy((request.get_json(silent=True) or {}).get("listing"))

    if not db.claim_recommendation(rec["ID"], "processing"):
        return jsonify({"ok": False, "error": "Already being processed or decided."}), 409
    try:
        db.create_listing_record(
            product=product,
            platform=marketplace,
            listing_price=price,
            floor_price=_floor_price_for(marketplace, rec),
            platform_listing_id="manual",
            approved_by=approved_by,
        )
    except Exception:
        log.exception("Failed to record manual listing for rec %s", rec["ID"])
        db.release_recommendation(rec["ID"])
        return jsonify({"ok": False, "error": "Could not record the manual listing. Please retry."}), 500
    db.update_recommendation_decision(rec["ID"], "approved")
    if listing_copy:
        db.save_listing_copy(rec["ID"], listing_copy)  # so it can be re-viewed later

    product_name = f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}"
    try:
        admin_audit.log_action(
            approved_by, 'ecommerce_mark_listed',
            target=f"{product['Manufacturer']} {product['Model']} {product.get('Colour', '')} Grade {product['Grade']}".strip(),
            detail=f"${price:.2f} on {marketplace} — marked listed (manual)",
        )
    except Exception:
        log.exception("Audit logging failed for ecommerce mark-listed (rec %s)", rec["ID"])

    return jsonify({"ok": True, "posted": False,
                    "message": f"{product_name} marked as listed on {marketplace}."})


@approval_bp.route("/listing/<int:rec_id>", methods=["GET"])
def view_listing(rec_id):
    """Return the stored listing copy for a resolved recommendation so the modal
    can be re-opened read-only. 404 if the rec or its saved copy is missing."""
    guard = _require_login_json()
    if guard:
        return guard
    rec = db.get_recommendation_by_id(rec_id)
    if not rec:
        return jsonify({"ok": False, "error": "Recommendation not found."}), 404
    copy = db.get_listing_copy(rec_id)
    if not copy:
        return jsonify({"ok": False,
                        "error": "No saved listing content for this recommendation."}), 404
    product = _product_from_rec(rec)
    meta = (copy or {}).get("_meta") or {}
    return jsonify({
        "ok":                True,
        "readonly":          True,
        "listing":           copy,
        "marketplace":       rec["RecommendedMarketplace"],
        "price":             float(rec["RecommendedPrice"]),
        "product":           f"{product['Manufacturer']} {product['Model']} Grade {product['Grade']}",
        "decision":          rec.get("Decision"),
        "listing_url":       meta.get("listing_url"),
        "public_listing_id": meta.get("public_listing_id"),
        "listing_id":        meta.get("platform_listing_id"),
        "env":               meta.get("env"),
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
    try:
        admin_audit.log_action(
            session.get('username'),
            'ecommerce_reject',
            target=f"{rec['Manufacturer']} {rec['Model']} {rec.get('Colour', '')} Grade {rec['Grade']}".strip(),
            detail=f"${float(rec['RecommendedPrice']):.2f} on {rec['RecommendedMarketplace']}",
        )
    except Exception:
        log.exception("Audit logging failed for ecommerce reject (rec %s)", rec_id)
    return jsonify({"ok": True, "message": f"{product_name} rejected."})
