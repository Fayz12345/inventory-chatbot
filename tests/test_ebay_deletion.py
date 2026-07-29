"""Tests for the eBay Marketplace Account Deletion (MAD) webhook.

Covers the pure challenge-response hash (eBay's exact algorithm), the public
GET challenge endpoint (no login), the payload shape-guard, and that a valid
deletion POST emails an alert to the SAME recipients as the scraper run report
while always acking HTTP 200 (even if the email fails).
"""
import hashlib
from unittest.mock import patch

import pytest

import app  # loads dotenv + blueprints + registers the /ebay/account-deletion route
import ecommerce.config as ecfg
from ecommerce.notifications import ebay_deletion


TOKEN = "test_verification_token_0123456789_abcdefgh"   # >=32 chars, [A-Za-z0-9_-]
ENDPOINT = "https://ai.bridge-renew.net/ebay/account-deletion"


@pytest.fixture
def anon_client():
    """Unauthenticated client — the webhook must work with no session."""
    app.chatbot_app.config["TESTING"] = True
    with app.chatbot_app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def _mad_config(monkeypatch):
    """Deterministic token/endpoint/recipients + a clean dedupe cache per test."""
    monkeypatch.setattr(ecfg, "EBAY_VERIFICATION_TOKEN", TOKEN)
    monkeypatch.setattr(ecfg, "EBAY_DELETION_ENDPOINT", ENDPOINT)
    monkeypatch.setattr(ecfg, "ECOMMERCE_EMAIL_TO",
                        "ops1@bridge-wireless.com, ops2@bridge-wireless.com")
    ebay_deletion._seen_ids.clear()
    yield


def _expected_hash(code):
    # eBay's documented order: challengeCode + verificationToken + endpoint
    return hashlib.sha256((code + TOKEN + ENDPOINT).encode("utf-8")).hexdigest()


def _mad_payload(notification_id="nid-1", username="testuser"):
    return {
        "metadata": {"topic": "MARKETPLACE_ACCOUNT_DELETION", "schemaVersion": "1.0"},
        "notification": {
            "notificationId": notification_id,
            "eventDate": "2026-07-29T10:00:00.000Z",
            "data": {"username": username, "userId": "u-123", "eiasToken": "eias-abc"},
        },
    }


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def test_challenge_response_matches_ebay_algorithm():
    assert ebay_deletion.challenge_response("CHALLENGE123") == _expected_hash("CHALLENGE123")
    # Order matters — a wrong concatenation order must NOT collide.
    wrong_order = hashlib.sha256(("CHALLENGE123" + ENDPOINT + TOKEN).encode()).hexdigest()
    assert ebay_deletion.challenge_response("CHALLENGE123") != wrong_order


def test_is_valid_notification_shape_guard():
    assert ebay_deletion.is_valid_notification(_mad_payload()) is True
    assert ebay_deletion.is_valid_notification(
        {"metadata": {"topic": "MARKETPLACE_ACCOUNT_DELETION"}}) is True
    assert ebay_deletion.is_valid_notification({}) is False
    assert ebay_deletion.is_valid_notification({"foo": "bar"}) is False
    assert ebay_deletion.is_valid_notification("not a dict") is False


# ---------------------------------------------------------------------------
# GET challenge (public, no login)
# ---------------------------------------------------------------------------

def test_get_challenge_returns_hash_json_unauthenticated(anon_client):
    resp = anon_client.get("/ebay/account-deletion?challenge_code=CHALLENGE123")
    assert resp.status_code == 200
    assert resp.content_type.startswith("application/json")
    assert resp.get_json() == {"challengeResponse": _expected_hash("CHALLENGE123")}


def test_get_without_challenge_code_is_400(anon_client):
    assert anon_client.get("/ebay/account-deletion").status_code == 400


# ---------------------------------------------------------------------------
# POST deletion notification
# ---------------------------------------------------------------------------

@patch("ecommerce.notifications.mailer.send_email", return_value=True)
def test_post_valid_notification_emails_and_acks_200(mock_send, anon_client):
    resp = anon_client.post("/ebay/account-deletion", json=_mad_payload(username="jdoe"))
    assert resp.status_code == 200
    mock_send.assert_called_once()
    to_arg, subject, body = mock_send.call_args.args[0:3]
    # Same recipient list as the scraper run report, passed verbatim (mailer
    # splits the comma-separated string — proven in test_run_report.py).
    assert to_arg == ecfg.ECOMMERCE_EMAIL_TO
    assert "jdoe" in subject
    assert "jdoe" in body


@patch("ecommerce.notifications.mailer.send_email", return_value=False)
def test_post_returns_200_even_if_email_fails(mock_send, anon_client):
    resp = anon_client.post("/ebay/account-deletion", json=_mad_payload())
    assert resp.status_code == 200
    mock_send.assert_called_once()


@patch("ecommerce.notifications.mailer.send_email")
def test_post_malformed_body_acks_200_without_email(mock_send, anon_client):
    assert anon_client.post("/ebay/account-deletion").status_code == 200          # no JSON body
    assert anon_client.post("/ebay/account-deletion", json={"foo": "bar"}).status_code == 200
    mock_send.assert_not_called()


@patch("ecommerce.notifications.mailer.send_email", return_value=True)
def test_post_duplicate_notification_emails_once(mock_send, anon_client):
    payload = _mad_payload(notification_id="dup-1")
    assert anon_client.post("/ebay/account-deletion", json=payload).status_code == 200
    assert anon_client.post("/ebay/account-deletion", json=payload).status_code == 200
    mock_send.assert_called_once()      # deduped by notificationId
