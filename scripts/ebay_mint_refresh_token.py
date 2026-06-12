#!/usr/bin/env python3
"""
One-shot helper to mint an eBay OAuth *refresh token* from an authorization
code (ticket 1D.5 - #137).

eBay's keyset only gives you App ID + Cert ID. The long-lived refresh token comes
from the Authorization Code grant: a seller consents in the browser, eBay
redirects with a single-use `code` (valid ~5 min), and you exchange that code
here for a refresh token (good ~18 months).

Steps:
  1. eBay dev portal -> "Get a Token from eBay via Your Application" -> click
     "Test Sign-In" and consent as a sandbox SELLER test user.
  2. Copy the FULL success-page URL (it contains "...&code=...").
  3. Run, pasting either the whole URL or just the bare code:

       python scripts/ebay_mint_refresh_token.py --runame "<YOUR_RUNAME>" "<paste URL or code>"

App ID / Cert ID and the sandbox-vs-prod choice are read from `.env` exactly the
way `ecommerce/config.py` resolves them, so a success here proves the same creds
`listings/ebay.py` will use are valid. On success the refresh token is written
straight into `.env` (the secret is masked in stdout).
"""
import argparse
import os
import sys
from urllib.parse import urlparse, parse_qs, unquote

import requests
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(ROOT, ".env")
load_dotenv(ENV_PATH)

# Mirror ecommerce/config.py's _resolve() without importing the DB/Keychain stack.
SANDBOX = (os.environ.get("EBAY_ENV") or "sandbox").strip().lower() != "production"
APP_ID = (os.environ.get("EBAY_APP_ID_SANDBOX" if SANDBOX else "EBAY_APP_ID") or "").strip()
CERT_ID = (os.environ.get("EBAY_CERT_ID_SANDBOX" if SANDBOX else "EBAY_CERT_ID") or "").strip()
AUTH_URL = ("https://api.sandbox.ebay.com/identity/v1/oauth2/token" if SANDBOX
            else "https://api.ebay.com/identity/v1/oauth2/token")
REFRESH_KEY = "EBAY_REFRESH_TOKEN_SANDBOX" if SANDBOX else "EBAY_REFRESH_TOKEN"


def extract_code(raw):
    """Accept either a full redirect URL or a bare code; return the decoded code."""
    raw = raw.strip().strip('"').strip("'")
    if "code=" in raw:
        codes = parse_qs(urlparse(raw).query).get("code")
        if not codes:
            sys.exit("Could not find a 'code' parameter in that URL.")
        return codes[0]                      # parse_qs already URL-decodes once
    return unquote(raw) if "%" in raw else raw


def write_env(key, value):
    """Update key=value in .env in place (append if absent). Returns True if replaced."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            lines = f.readlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(key + "="):
            lines[i] = f"{key}={value}\n"
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(f"{key}={value}\n")
        with open(ENV_PATH, "w") as f:
            f.writelines(lines)
        return False
    with open(ENV_PATH, "w") as f:
        f.writelines(lines)
    return True


def mask(tok):
    return f"{tok[:12]}...{tok[-6:]} ({len(tok)} chars)" if len(tok) >= 24 else tok


def main():
    ap = argparse.ArgumentParser(description="Mint an eBay refresh token from an auth code.")
    ap.add_argument("code_or_url", help="The success-page URL or the bare authorization code.")
    ap.add_argument("--runame",
                    default=os.environ.get("EBAY_RUNAME_SANDBOX") or os.environ.get("EBAY_RUNAME"),
                    help="Your RuName (eBay Redirect URL name). Defaults to EBAY_RUNAME[_SANDBOX].")
    args = ap.parse_args()

    if not args.runame:
        sys.exit("Missing RuName. Pass --runame '<your eBay Redirect URL name>'.")
    if not (APP_ID and CERT_ID):
        sys.exit(f"EBAY App/Cert ID not found in .env for env={'sandbox' if SANDBOX else 'production'}.")

    code = extract_code(args.code_or_url)
    print(f"Exchanging auth code at {'SANDBOX' if SANDBOX else 'PRODUCTION'} endpoint ...")

    resp = requests.post(
        AUTH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(APP_ID, CERT_ID),
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": args.runame},
        timeout=30,
    )
    if resp.status_code != 200:
        sys.exit(f"Exchange failed ({resp.status_code}): {resp.text}")

    body = resp.json()
    refresh = body.get("refresh_token")
    if not refresh:
        sys.exit(f"No refresh_token in response (got keys: {list(body)}). Full body: {body}")

    days = body.get("refresh_token_expires_in", 0) // 86400
    replaced = write_env(REFRESH_KEY, refresh)
    print("\nRefresh token minted.")
    print(f"  {REFRESH_KEY} = {mask(refresh)}")
    print(f"  valid ~{days} days; access token also returned (expires in {body.get('expires_in')}s)")
    print(f"  {'updated' if replaced else 'appended'} in {ENV_PATH}")


if __name__ == "__main__":
    main()
