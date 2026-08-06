"""Unit tests for the ecommerce approve / post / mark-listed / reject routes.

New flow (posting decoupled from approval):
  - POST /approve       -> PREVIEW ONLY: returns copy + can_post/env, NO status
    change, NO marketplace call.
  - POST /post          -> auto-post to the marketplace API; atomic claim, log,
    finalize to 'approved'; 502 (claim released) on API failure; 400 if no API.
  - POST /mark-listed    -> record a MANUAL listing (PlatformListingID='manual')
    and finalize to 'approved'.
  - POST /reject         -> atomic claim as 'rejected'.
Plus listing_availability() — the single source of the modal's Auto-post gate.
"""
from unittest.mock import patch

import pytest

import app  # ensure dotenv + blueprints are loaded
import ecommerce.approval as approval
import ecommerce.config as ecfg


@pytest.fixture
def client():
    """Authenticated client — mirrors a logged-in operator."""
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        with c.session_transaction() as sess:
            sess["logged_in"] = True
            sess["username"] = "tester"
            sess["role"] = "admin"
        yield c


@pytest.fixture
def anon_client():
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        yield c


def _rec(marketplace="Amazon CA", decision=None):
    return {
        "ID": 1, "Decision": decision,
        "Manufacturer": "Samsung", "Model": "S25 Ultra", "Colour": "Black",
        "Grade": "A", "Quantity": 3,
        "RecommendedMarketplace": marketplace, "RecommendedPrice": 829.99,
        "AmazonFloor": 850.0, "EbayFloor": 780.0,
        "BestBuyFloor": 900.0, "ReebeloFloor": 760.0,
    }


def _copy():
    return {"title": "T", "description": "D", "bullets": ["b1"], "condition_note": "C"}


# ---------------------------------------------------------------------------
# approve = PREVIEW ONLY (no status change, no marketplace call)
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.listing_availability",
       return_value={"available": True, "reason": "", "env": "sandbox"})
@patch("ecommerce.approval.db.claim_recommendation")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_approve_returns_preview_without_posting(_get, _copy_, mock_claim, _avail, client):
    resp = client.post("/ecommerce/approve?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["listing"]["title"] == "T"
    assert body["marketplace"] == "eBay CA"
    assert body["can_post"] is True and body["env"] == "sandbox"
    assert "posted" not in body            # nothing posted on preview
    mock_claim.assert_not_called()         # NO status change on approve


@patch("ecommerce.approval.listing_availability",
       return_value={"available": False,
                     "reason": "No Best Buy catalog match (UPC) for this SKU.",
                     "env": "production"})
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_approve_reports_cannot_post_with_reason(_get, _copy_, _catalog, _avail, client):
    resp = client.post("/ecommerce/approve?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True
    assert body["can_post"] is False and "catalog match" in body["post_reason"].lower()


# ---------------------------------------------------------------------------
# /post — auto-post success / failure / rollback / no-api / race
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.db.create_listing_record", return_value=42)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog",
       return_value={"asin": "B0XXXX", "upc": "0123", "epid": "EPID1"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SAMSUNG-S25-A-BLACK", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_amazon_claims_posts_logs_and_approves(
        _get, _copy_, mock_amazon, _catalog, mock_claim, mock_decision, mock_log, _devcat, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["posted"] is True
    assert body["listing_id"] == "SAMSUNG-S25-A-BLACK" and body["env"] == "sandbox"
    mock_amazon.assert_called_once()
    assert mock_amazon.call_args.kwargs["device_category"] == "Handset"
    mock_claim.assert_called_once_with(1, "processing")
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["floor_price"] == 850.0
    mock_decision.assert_called_once_with(1, "approved")


@patch("ecommerce.approval.db.create_listing_record")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={"asin": None, "upc": None})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": False, "error": "Amazon SP-API: bad seller_id"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_failure_releases_claim_and_returns_502(
        _get, _copy_, _amazon, _catalog, mock_claim, mock_release, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 502
    assert "bad seller_id" in resp.get_json()["error"]
    mock_release.assert_called_once_with(1)
    mock_log.assert_not_called()
    mock_decision.assert_not_called()


@patch("ecommerce.approval.db.create_listing_record", return_value=43)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={"asin": None, "upc": "0123"})
@patch("ecommerce.approval.ebay_listings.create_listing",
       return_value={"ok": True, "listing_id": "12345", "env": "sandbox",
                     "public_listing_id": "PUB9", "listing_url": "https://x/9"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_post_ebay_success_returns_public_id_and_url(
        _get, _copy_, mock_ebay, _catalog, mock_claim, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/post?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["posted"] is True
    assert body["public_listing_id"] == "PUB9" and body["listing_url"] == "https://x/9"
    assert mock_log.call_args.kwargs["floor_price"] == 780.0


@patch("ecommerce.approval.db.lookup_device_category", return_value="Tablet")
@patch("ecommerce.approval.amazon_listings.delist", return_value=True)
@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.create_listing_record", side_effect=Exception("DB down"))
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SKU-1", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_log_failure_rolls_back_and_releases(
        _get, _copy_, _amazon, _catalog, _claim, mock_create, mock_decision,
        mock_release, mock_delist, _devcat, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 500
    mock_delist.assert_called_once_with("SKU-1", device_category="Tablet")
    mock_release.assert_called_once_with(1)
    mock_decision.assert_not_called()


@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.reebelo_listings._have_creds", return_value=False)
@patch("ecommerce.approval.reebelo_listings.create_listing")
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Reebelo CA"))
def test_post_no_api_marketplace_releases_and_400(
        _get, _copy_, mock_reebelo, _hc, mock_claim, mock_release, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 400
    assert "no listing api" in resp.get_json()["error"].lower()
    mock_reebelo.assert_not_called()
    mock_release.assert_called_once_with(1)


@patch("ecommerce.approval.amazon_listings.create_listing")
@patch("ecommerce.approval.db.claim_recommendation", return_value=False)
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_lost_race_returns_409_without_posting(_get, _copy_, mock_claim, mock_amazon, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 409
    mock_amazon.assert_not_called()


@patch("ecommerce.approval.db.create_listing_record", return_value=51)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={"asin": "B0", "upc": "0123"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SKU-9", "env": "production"})
@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.copy_generator.generate_listing_copy")
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_uses_client_echoed_copy_without_regenerating(
        _get, mock_gen, _devcat, mock_amazon, _catalog, _claim, _decision, _log, client):
    resp = client.post("/ecommerce/post?id=1", json={"listing": _copy()})
    assert resp.status_code == 200
    mock_gen.assert_not_called()   # valid client copy -> no Claude call
    assert mock_amazon.call_args.kwargs["listing_copy"]["title"] == "T"


# ---------------------------------------------------------------------------
# /mark-listed — manual resolution (no API call)
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.create_listing_record", return_value=60)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_mark_listed_records_manual_and_approves(
        _get, mock_claim, mock_decision, mock_log, client):
    resp = client.post("/ecommerce/mark-listed?id=1")
    body = resp.get_json()
    assert resp.status_code == 200 and body["ok"] is True and body["posted"] is False
    mock_claim.assert_called_once_with(1, "processing")
    assert mock_log.call_args.kwargs["platform_listing_id"] == "manual"
    assert mock_log.call_args.kwargs["floor_price"] == 900.0
    mock_decision.assert_called_once_with(1, "approved")


@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.create_listing_record", side_effect=Exception("DB down"))
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Reebelo CA"))
def test_mark_listed_log_failure_releases_and_500(
        _get, _claim, _log, mock_decision, mock_release, client):
    resp = client.post("/ecommerce/mark-listed?id=1")
    assert resp.status_code == 500
    mock_release.assert_called_once_with(1)
    mock_decision.assert_not_called()


# ---------------------------------------------------------------------------
# View a resolved listing again (read-only) — persisted copy
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.save_listing_copy")
@patch("ecommerce.approval.db.lookup_device_category", return_value="Handset")
@patch("ecommerce.approval.db.create_listing_record", return_value=42)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={"asin": "B0", "upc": "0123"})
@patch("ecommerce.approval.amazon_listings.create_listing",
       return_value={"ok": True, "listing_id": "SKU", "env": "sandbox"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_post_persists_listing_copy(
        _get, _cp, _am, _cat, _claim, _dec, _log, _dev, mock_save, client):
    assert client.post("/ecommerce/post?id=1").status_code == 200
    mock_save.assert_called_once()
    assert mock_save.call_args.args[0] == 1 and mock_save.call_args.args[1]["title"] == "T"


@patch("ecommerce.approval.db.save_listing_copy")
@patch("ecommerce.approval.db.create_listing_record", return_value=60)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_mark_listed_persists_client_copy(_get, _claim, _dec, _log, mock_save, client):
    assert client.post("/ecommerce/mark-listed?id=1", json={"listing": _copy()}).status_code == 200
    mock_save.assert_called_once()
    assert mock_save.call_args.args[1]["title"] == "T"


@patch("ecommerce.approval.db.save_listing_copy")
@patch("ecommerce.approval.db.create_listing_record", return_value=43)
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={"asin": None, "upc": "0123"})
@patch("ecommerce.approval.ebay_listings.create_listing",
       return_value={"ok": True, "listing_id": "12345", "env": "sandbox",
                     "public_listing_id": "PUB9", "listing_url": "https://x/9"})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("eBay CA"))
def test_post_persists_live_listing_link_in_meta(
        _get, _cp, _ebay, _cat, _claim, _dec, _log, mock_save, client):
    # The live URL + ids are tucked into the saved copy's _meta so the View modal
    # can re-show a clickable link later (no DB schema change).
    assert client.post("/ecommerce/post?id=1").status_code == 200
    saved = mock_save.call_args.args[1]
    assert saved["_meta"]["listing_url"] == "https://x/9"
    assert saved["_meta"]["public_listing_id"] == "PUB9"
    assert saved["_meta"]["platform_listing_id"] == "12345"
    assert saved["_meta"]["env"] == "sandbox"


@patch("ecommerce.approval.db.get_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id",
       return_value=_rec("eBay CA", decision="approved"))
def test_view_listing_returns_saved_copy_readonly(_get, _copy_, client):
    body = client.get("/ecommerce/listing/1").get_json()
    assert body["ok"] is True and body["readonly"] is True
    assert body["listing"]["title"] == "T" and body["marketplace"] == "eBay CA"
    assert body["listing_url"] is None          # no _meta saved -> no link (older rows)


@patch("ecommerce.approval.db.get_listing_copy",
       return_value={**_copy(), "_meta": {"listing_url": "https://x/9",
                                          "public_listing_id": "PUB9",
                                          "platform_listing_id": "12345", "env": "sandbox"}})
@patch("ecommerce.approval.db.get_recommendation_by_id",
       return_value=_rec("eBay CA", decision="approved"))
def test_view_listing_surfaces_saved_live_link(_get, _copy_, client):
    body = client.get("/ecommerce/listing/1").get_json()
    assert body["ok"] is True
    assert body["listing_url"] == "https://x/9"
    assert body["public_listing_id"] == "PUB9" and body["listing_id"] == "12345"
    assert body["env"] == "sandbox"


@patch("ecommerce.approval.db.get_listing_copy", return_value=None)
@patch("ecommerce.approval.db.get_recommendation_by_id",
       return_value=_rec("eBay CA", decision="approved"))
def test_view_listing_404_when_no_saved_copy(_get, _none, client):
    assert client.get("/ecommerce/listing/1").status_code == 404


def test_view_listing_unauthenticated_401(anon_client):
    assert anon_client.get("/ecommerce/listing/1").status_code == 401


# ---------------------------------------------------------------------------
# listing_availability — the Auto-post gate
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.amazon_listings._have_creds", return_value=False)
def test_availability_amazon_unconfigured(_hc):
    r = approval.listing_availability("Amazon CA")
    assert r["available"] is False and "not configured" in r["reason"].lower()


@patch("ecommerce.approval.amazon_listings._have_creds", return_value=True)
def test_availability_amazon_configured(_hc):
    assert approval.listing_availability("Amazon")["available"] is True


@patch("ecommerce.approval.ebay_listings._have_creds", return_value=True)
def test_availability_ebay_needs_publish_prereqs(_hc, monkeypatch):
    monkeypatch.setattr(ecfg, "EBAY_MERCHANT_LOCATION_KEY", "")
    r = approval.listing_availability("eBay CA")
    assert r["available"] is False and "prerequisite" in r["reason"].lower()


@patch("ecommerce.approval.ebay_listings._have_creds", return_value=True)
def test_availability_ebay_ready_with_all_prereqs(_hc, monkeypatch):
    for attr in ("EBAY_MERCHANT_LOCATION_KEY", "EBAY_FULFILLMENT_POLICY_ID",
                 "EBAY_PAYMENT_POLICY_ID", "EBAY_RETURN_POLICY_ID"):
        monkeypatch.setattr(ecfg, attr, "X")
    assert approval.listing_availability("eBay CA")["available"] is True


@patch("ecommerce.approval.bestbuy_listings._have_creds", return_value=True)
def test_availability_bestbuy_creds_only_no_upc_needed(_hc):
    # The product SKU is resolved on the fly at post time, so no catalog UPC is required.
    assert approval.listing_availability("Best Buy CA", catalog={})["available"] is True
    assert approval.listing_availability("Best Buy CA", catalog={"upc": "1"})["available"] is True


@patch("ecommerce.approval.bestbuy_listings._have_creds", return_value=False)
def test_availability_bestbuy_needs_creds(_hc):
    assert approval.listing_availability("Best Buy CA", catalog={})["available"] is False


def test_availability_unknown_marketplace_is_false():
    r = approval.listing_availability("Craigslist")
    assert r["available"] is False and r["env"] is None


# ---------------------------------------------------------------------------
# Best Buy post — SKU resolved on the fly (no seeded UPC)
# ---------------------------------------------------------------------------

@patch("ecommerce.approval.db.create_listing_record", return_value=61)
@patch("ecommerce.approval.db.save_listing_copy")
@patch("ecommerce.approval.db.update_recommendation_decision")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.bestbuy_listings.create_listing",
       return_value={"ok": True, "listing_id": "SAMSUNG-S25-ULTRA-A-BLACK",
                     "env": "production", "listing_url": "u"})
@patch("ecommerce.approval.bestbuy_pricing.find_product_sku", return_value="15997245")
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_post_bestbuy_resolves_sku_on_the_fly_and_posts(
        _get, _copy_, _catalog, mock_find, mock_create, mock_claim, mock_decision, _save, mock_log, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True and body["posted"] is True
    mock_find.assert_called_once()                                     # SKU resolved on the fly
    assert mock_create.call_args.kwargs["catalog_info"]["product_sku"] == "15997245"   # no UPC needed
    mock_claim.assert_called_once_with(1, "processing")
    mock_decision.assert_called_once_with(1, "approved")


@patch("ecommerce.approval.db.release_recommendation")
@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.bestbuy_pricing.find_product_sku", return_value=None)
@patch("ecommerce.approval.db.lookup_product_catalog", return_value={})
@patch("ecommerce.approval.copy_generator.generate_listing_copy", return_value=_copy())
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Best Buy CA"))
def test_post_bestbuy_no_sku_no_upc_is_400_and_releases(
        _get, _copy_, _catalog, mock_find, mock_claim, mock_release, client):
    resp = client.post("/ecommerce/post?id=1")
    assert resp.status_code == 400                       # no product ref -> preview-only path
    mock_release.assert_called_once_with(1)              # claim released


# ---------------------------------------------------------------------------
# Auth + reject + shared guards
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/ecommerce/approve?id=1", "/ecommerce/post?id=1",
                                  "/ecommerce/mark-listed?id=1", "/ecommerce/reject?id=1"])
def test_unauthenticated_returns_401(anon_client, path):
    resp = anon_client.post(path)
    assert resp.status_code == 401 and resp.get_json()["ok"] is False


@patch("ecommerce.approval.db.claim_recommendation", return_value=True)
@patch("ecommerce.approval.db.get_recommendation_by_id", return_value=_rec("Amazon CA"))
def test_reject_claims_atomically(_get, mock_claim, client):
    resp = client.post("/ecommerce/reject?id=1")
    assert resp.status_code == 200 and resp.get_json()["ok"] is True
    mock_claim.assert_called_once_with(1, "rejected")


@pytest.mark.parametrize("path", ["/ecommerce/approve?id=1", "/ecommerce/post?id=1",
                                  "/ecommerce/mark-listed?id=1"])
@patch("ecommerce.approval.db.get_recommendation_by_id",
       return_value=_rec("Amazon CA", decision="approved"))
def test_already_decided_returns_409(_get, client, path):
    resp = client.post(path)
    assert resp.status_code == 409 and "Already" in resp.get_json()["error"]


@pytest.mark.parametrize("path", ["/ecommerce/approve", "/ecommerce/post", "/ecommerce/mark-listed"])
def test_missing_id_returns_400(client, path):
    assert client.post(path).status_code == 400
