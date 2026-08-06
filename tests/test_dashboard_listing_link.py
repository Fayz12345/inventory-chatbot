"""The dashboard modal must show a clickable 'View listing' link to the live
marketplace post — both right after Auto-post and when re-opening a resolved row
later. These render the batch-detail page and assert the wiring is present."""
from ecommerce.notifications.email_digest import render_dashboard


def _html():
    # Minimal inputs: the <script> block is static, so empty recommendations
    # still emit the full client JS we assert on.
    return render_dashboard({"ID": 1, "CreatedAt": None}, [])


def test_shared_listing_link_helper_present():
    assert "function appendListingLink(" in _html()


def test_post_success_banner_uses_shared_link_helper():
    # Green "Posted" banner appends the live link via the shared helper.
    assert "appendListingLink(status, res.listing_url)" in _html()


def test_readonly_review_renders_live_link():
    # Re-opening a resolved listing (View) shows the same clickable link.
    assert "appendListingLink(st, data.listing_url)" in _html()


def test_resolved_row_gets_view_button_after_in_place_post():
    # markRowResolved adds a View button so the listing (and its link) is
    # re-viewable immediately, without waiting for a page reload.
    assert "viewBtn.onclick = function() { viewListing(recId); }" in _html()
