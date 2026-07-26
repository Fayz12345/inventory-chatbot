"""Standalone M365 Graph email sender for the ecommerce pipeline.

The Flask app (app.py) already sends invites via M365 Graph, but the weekly cron
runs `python -m ecommerce.main` WITHOUT the Flask app, so the run-report send
needs its own transport. Client-credentials OAuth -> Graph sendMail. Every path
is best-effort: a report-email failure must never crash the pipeline.
"""

import logging
import time

import requests

from ecommerce import config

log = logging.getLogger(__name__)

_token_cache = {"token": "", "exp": 0.0}


def _access_token():
    now = time.time()
    if _token_cache["token"] and _token_cache["exp"] - 60 > now:
        return _token_cache["token"]
    url = "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % config.M365_TENANT_ID
    resp = requests.post(url, data={
        "client_id": config.M365_CLIENT_ID,
        "client_secret": config.M365_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["exp"] = now + max(int(data.get("expires_in", 0)), 300)
    return _token_cache["token"]


def recipients(to):
    """Normalise a comma/semicolon string or a list into a clean address list."""
    if isinstance(to, str):
        parts = [p.strip() for p in to.replace(";", ",").split(",")]
    else:
        parts = [str(p).strip() for p in (to or [])]
    return [p for p in parts if p]


def is_configured():
    return bool(config.M365_TENANT_ID and config.M365_CLIENT_ID
                and config.M365_CLIENT_SECRET and config.M365_SENDER)


def send_email(to, subject, html_body):
    """Send an HTML email via M365 Graph. `to` is a list or comma/semicolon
    string. Returns True on success; logs and returns False on any failure."""
    to_list = recipients(to)
    if not to_list:
        log.warning("send_email: no recipients (ECOMMERCE_EMAIL_TO empty) — skipping.")
        return False
    if not is_configured():
        log.warning("send_email: M365 not configured — skipping report email.")
        return False
    try:
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html_body},
            "toRecipients": [{"emailAddress": {"address": r}} for r in to_list],
        }
        url = "https://graph.microsoft.com/v1.0/users/%s/sendMail" % config.M365_SENDER
        resp = requests.post(
            url,
            headers={"Authorization": "Bearer %s" % _access_token(),
                     "Content-Type": "application/json"},
            json={"message": message, "saveToSentItems": True},
            timeout=30,
        )
        if resp.status_code in (200, 202):
            log.info("Run report emailed to %s.", ", ".join(to_list))
            return True
        log.error("send_email: Graph sendMail returned %s: %s", resp.status_code, resp.text[:300])
        return False
    except Exception:
        log.exception("send_email: failed to send report email.")
        return False
