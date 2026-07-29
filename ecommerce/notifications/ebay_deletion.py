"""
eBay Marketplace Account Deletion (MAD) webhook helpers.

eBay requires every PRODUCTION application to expose a public HTTPS endpoint that
(1) answers a one-time challenge-response validation and (2) returns HTTP 200 to
account-deletion / closure notifications. The Flask route lives in app.py
(`/ebay/account-deletion`); this module holds the pure, testable pieces.

Challenge-response (per eBay docs): respond with
    sha256_hex(challengeCode + verificationToken + endpoint)
concatenated in EXACTLY that order, where `endpoint` must match the URL
registered in the eBay portal character-for-character or validation fails.

On a valid deletion notification we email an alert to the SAME recipients as the
weekly scraper run report (config.ECOMMERCE_EMAIL_TO) via the shared M365 mailer.
We store no eBay buyer personal data (we scrape prices, not buyers), so there is
nothing to purge — the notification is informational.
"""

import hashlib
import html
import logging

from ecommerce import config
from ecommerce.notifications import mailer

log = logging.getLogger(__name__)

# Best-effort in-memory dedupe so eBay's retries (or a double-delivery) don't
# email the same notification twice. Bounded so it can't grow without limit; it
# is per-process (per gunicorn worker), which is fine for a low-volume webhook.
_seen_ids = []
_SEEN_MAX = 500


def challenge_response(challenge_code):
    """Compute eBay's validation hash: sha256_hex(code + token + endpoint).

    The three parts MUST be concatenated in this exact order, and `endpoint`
    must equal the URL registered in the eBay portal, or validation fails.
    """
    payload = (
        (challenge_code or "")
        + (config.EBAY_VERIFICATION_TOKEN or "")
        + (config.EBAY_DELETION_ENDPOINT or "")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_valid_notification(payload):
    """True if the POST body looks like a real eBay MAD notification. A shape
    guard so a random POST to the public URL can't trigger an alert email."""
    if not isinstance(payload, dict):
        return False
    topic = (payload.get("metadata") or {}).get("topic")
    if topic == "MARKETPLACE_ACCOUNT_DELETION":
        return True
    data = (payload.get("notification") or {}).get("data")
    return isinstance(data, dict) and bool(data.get("username") or data.get("userId"))


def _summarize(payload):
    """Pull the fields we surface in the alert email/log."""
    notif = payload.get("notification") or {}
    data = notif.get("data") or {}
    return {
        "notificationId": notif.get("notificationId", ""),
        "eventDate": notif.get("eventDate", ""),
        "username": data.get("username", ""),
        "userId": data.get("userId", ""),
        "eiasToken": data.get("eiasToken", ""),
    }


def alert_subject(info):
    who = info.get("username") or info.get("userId") or "unknown user"
    return "eBay account-deletion notification — %s" % who


def alert_html(info):
    fields = (
        ("Username", info.get("username")),
        ("User ID", info.get("userId")),
        ("EIAS token", info.get("eiasToken")),
        ("Event date", info.get("eventDate")),
        ("Notification ID", info.get("notificationId")),
    )
    rows = "".join(
        "<tr><td style='padding:4px 12px 4px 0;color:#555'>{label}</td>"
        "<td style='padding:4px 0'><code>{value}</code></td></tr>".format(
            label=html.escape(label),
            value=html.escape(str(value) if value else "—"),
        )
        for label, value in fields
    )
    return (
        "<div style='font-family:system-ui,Segoe UI,Arial,sans-serif;font-size:14px;color:#222'>"
        "<h2 style='margin:0 0 8px'>eBay Marketplace Account Deletion</h2>"
        "<p>eBay sent an account-deletion / closure notification to the webhook "
        "(<code>{endpoint}</code>). No action is required — we store no eBay buyer "
        "personal data, so there is nothing to purge. Logged for your records.</p>"
        "<table style='border-collapse:collapse;margin-top:8px'>{rows}</table>"
        "</div>"
    ).format(endpoint=html.escape(config.EBAY_DELETION_ENDPOINT or ""), rows=rows)


def handle_notification(payload):
    """Email + log a valid eBay deletion notification. Never raises — the caller
    must still return HTTP 200 to eBay even if the email fails."""
    if not is_valid_notification(payload):
        log.info("eBay MAD: ignoring POST that is not a MARKETPLACE_ACCOUNT_DELETION notification.")
        return

    info = _summarize(payload)

    nid = info.get("notificationId")
    if nid:
        if nid in _seen_ids:
            log.info("eBay MAD: duplicate notification %s — skipping alert.", nid)
            return
        _seen_ids.append(nid)
        if len(_seen_ids) > _SEEN_MAX:
            del _seen_ids[: len(_seen_ids) - _SEEN_MAX]

    log.info("eBay MAD notification received: user=%s userId=%s notificationId=%s",
             info.get("username"), info.get("userId"), nid)

    sent = mailer.send_email(config.ECOMMERCE_EMAIL_TO, alert_subject(info), alert_html(info))
    if not sent:
        log.warning("eBay MAD: alert email not sent (no recipients or M365 unconfigured).")
