"""
Apify residential proxy routing + datacenter-IP block detection for plain HTTP
price fetches.

Some marketplace endpoints block requests from the EC2 datacenter IP:
  - reebelo.ca actively blocks datacenter IPs (its own actor's docs say so).
  - Best Buy's Mirakl API *might* (authenticated, so less likely).

Routing a GET through Apify's RESIDENTIAL proxy pool means a blocked IP is rotated
out — the next request comes from a fresh residential exit node. This module also
centralises block DETECTION logging so a block shows up loudly in the weekly run
log instead of silently zeroing prices.

Apify's proxy is a standard HTTP proxy that tunnels HTTPS via CONNECT, so it plugs
straight into `requests` via the `proxies=` argument with normal TLS verification
of the target host.
"""

import logging

from ecommerce import config

log = logging.getLogger(__name__)

_PROXY_HOST = "proxy.apify.com:8000"


def apify_proxy_url(country="CA", groups="RESIDENTIAL"):
    """Apify proxy URL for the given group/country, or None if the proxy password
    isn't configured. The password is the Apify *proxy* password (Console -> Proxy),
    which is distinct from the API token."""
    pw = getattr(config, "APIFY_PROXY_PASSWORD", "") or ""
    if not pw:
        return None
    return f"http://groups-{groups},country-{country}:{pw}@{_PROXY_HOST}"


def proxies_for(use_proxy, label="http"):
    """Resolve a `requests` proxies dict for a fetch.

    Returns (proxies_or_None, via) where `via` is a short human string for logging:
      - "apify-residential"          -> routed through the Apify residential pool
      - "direct(datacenter-IP)"      -> deliberately direct
      - "direct(datacenter-IP, proxy unconfigured)" -> wanted proxy but no password
    """
    if not use_proxy:
        return None, "direct(datacenter-IP)"
    purl = apify_proxy_url()
    if not purl:
        log.warning("[%s] APIFY_PROXY_PASSWORD not set — using a DIRECT datacenter-IP "
                    "request (can be blocked). Set APIFY_PROXY_PASSWORD to route via Apify.",
                    label)
        return None, "direct(datacenter-IP, proxy unconfigured)"
    return {"http": purl, "https": purl}, "apify-residential"


def looks_blocked(status_code):
    """True if an HTTP status looks like an anti-bot / IP block (vs a normal 404).

    403 (forbidden) and 429 (rate-limited) are the classic anti-bot responses; 5xx
    often means the bot-wall returned an error page. NOTE: for an authenticated API
    a 403 can also mean bad credentials/scope — callers log with that context.
    """
    return status_code in (403, 429) or status_code >= 500


def log_block(label, status, via, body=""):
    """Emit one loud WARNING describing a suspected datacenter-IP / anti-bot block,
    so it's traceable in the run log."""
    log.warning("[%s] HTTP %s via %s — possible datacenter-IP / anti-bot BLOCK. body=%r",
                label, status, via, (body or "")[:160])
