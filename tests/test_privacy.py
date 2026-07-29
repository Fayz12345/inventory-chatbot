"""Tests for the public /privacy policy page.

This page is linked from eBay's OAuth consent screen
(https://ai.bridge-renew.net/privacy) and MUST be reachable with no login and
no session — a top-level route, NOT under the ecommerce blueprint (which
force-logins every route). Mirrors the anonymous-client pattern in
tests/test_ebay_deletion.py.
"""
import pytest

import app  # loads dotenv + blueprints + registers the /privacy route


@pytest.fixture
def anon_client():
    """Unauthenticated client — the privacy page must work with no session."""
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        yield c


def test_privacy_page_public_returns_html(anon_client):
    resp = anon_client.get("/privacy")
    assert resp.status_code == 200
    assert resp.content_type.startswith("text/html")
    body = resp.get_data(as_text=True)
    # Distinctive strings a human/eBay reviewer expects to see.
    assert "Privacy" in body
    assert "Bridge Wireless" in body
    assert "eBay" in body


def test_privacy_route_is_registered_top_level():
    assert any(str(r) == "/privacy" for r in app.chatbot_app.url_map.iter_rules())
