# Ecommerce AI Plan
### Internal Document — Management Team

**Prepared:** March 2026
**Status:** Planning — Phase 1D (final sub-phase of Phase 1, after Inventory Intelligence)

---

## Overview

This phase adds an AI-powered ecommerce listing workflow that runs daily, scans inventory flagged for ecommerce, researches competitive prices across marketplaces, recommends the best platform to sell on, and — upon human approval — drafts and posts the listing automatically.

---

## Workflow (End-to-End)

```
Linux cron job (daily, e.g. 7am) → python ecommerce_agent.py
    ↓
Query ReportingInventoryFlat → two queries, results merged:
  1. Product_Place = 'Ecommerce Storefront' AND Product_Placement_Created = prev business day
  2. Product_Place = 'Ecommerce Storefront' AND no active listing in EcommerceListingsLog (fallback)
    ↓
Reconcile against active listings table → skip already-listed SKUs, delist removed SKUs
    ↓
For each unlisted product group:
    → eBay Browse API        (free, official — no scraping)
    → Amazon SP-API          (free with seller account — no scraping)
    → BestBuy Products API or direct scraper  (BestBuy — no competitor pricing API exists)
    → Reebelo Cobalt API or direct scraper    (Reebelo — seller API exists; pricing data TBD)
    ↓
Sanity check: skip any SKU where best price < DeviceCost threshold
    ↓
DeepSeek V3 applies pricing algorithm → ranked marketplace recommendation per SKU
    ↓
Email digest sent to approver:
    one row per SKU with recommended marketplace, floor price, approve/reject link
    ↓ [on approval click — Flask endpoint on EC2]
Fetch top 3–5 competitor listings from winning marketplace
    ↓
DeepSeek V3 drafts listing title + description + bullet points
    ↓
Post via marketplace API (eBay Inventory API / Amazon SP-API / BestBuy Seller API / Reebelo Cobalt API)
    ↓
Log listing record to SQL Server (SKU, platform, price, timestamp)
```

---

## Inventory Data Structure

**One schema addition to `ReportingInventoryFlat`:** a `Product_Placement_Created` datetime column recording when each ESN was moved into its current `Product_Place`. The flat table remains the source of truth; no other structural changes needed.

**New column:**
| Column | Type | Source | Purpose |
|---|---|---|---|
| `Product_Placement_Created` | datetime | ReceiveDetailProcessLog or the relevant audit trail for Product Place changes | Identifies when each device entered its current Product Place — used to filter for newly ecommerce-ready devices |

**Primary query — previous business day additions:**
```sql
SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
FROM ReportingInventoryFlat
WHERE Product_Place = 'Ecommerce Storefront'
  AND CAST(Product_Placement_Created AS DATE) = :prev_business_day
GROUP BY Manufacturer, Model, Colour, Grade
ORDER BY Quantity DESC
```
> `prev_business_day` is calculated in Python before the query runs:
> Monday → Friday, all other days → yesterday.
> Canadian public holidays not currently handled — flag for future improvement.

**Fallback query — unlisted SKUs with no active listing record:**
```sql
SELECT Manufacturer, Model, Colour, Grade, COUNT(*) AS Quantity
FROM ReportingInventoryFlat r
WHERE Product_Place = 'Ecommerce Storefront'
  AND NOT EXISTS (
      SELECT 1 FROM EcommerceListingsLog l
      WHERE l.Manufacturer = r.Manufacturer
        AND l.Model = r.Model
        AND l.Grade = r.Grade
        AND l.Colour = r.Colour
        AND l.Status = 'active'
  )
GROUP BY Manufacturer, Model, Colour, Grade
ORDER BY Quantity DESC
```
> Catches SKUs that were rejected, skipped, or missed on a prior day.
> Both queries run on each daily job — results are merged and deduplicated before price scanning.

---

## Pricing Algorithm

**Rule (confirmed):** For each marketplace, find the lowest listed price for the SKU. Pick the marketplace with the highest of those floor prices. List at that price.

**Example:**
| Marketplace | Lowest Competitor Price | Highest Competitor Price |
|---|---|---|
| Amazon | $750 | $900 |
| eBay | $800 | $950 |
| BestBuy Marketplace | $700 | $850 |

→ eBay wins (floor = $800, highest among all floors). List at **$800**.

**Why this works:** You're entering the market where even the cheapest seller is selling high, maximizing your sale price while remaining competitive with the lowest-priced seller on that platform.

---

## Technology Stack

### Orchestration
| Tool | Role |
|---|---|
| **Linux cron job** | Daily trigger — runs `ecommerce_agent.py` on the existing EC2 |
| **Python script** | Full pipeline: DB query → price APIs → AI ranking → email → listing post → logging |
| **Flask (existing)** | Receives approval link clicks — triggers listing creation |

> **OpenClaw not required for this workflow.** OpenClaw's strength is flexible AI-driven alerting (Phase 1C). This pipeline is a structured, deterministic sequence of steps — a Python cron job handles it more simply with no new platform dependency. All infrastructure (EC2, Python, ODBC, Flask) already exists.

### AI / Reasoning
| Tool | Role | Notes |
|---|---|---|
| **DeepSeek V3** | Price comparison logic, marketplace ranking, listing generation | Cost-effective; "DeepSeek V4" does not exist yet — V3 is current latest general model |
| **Claude API** (optional) | Listing copy generation | May produce more polished marketplace-ready text; can be used alongside DeepSeek |

### Price Intelligence APIs
| Marketplace | Tool | Cost | Notes |
|---|---|---|---|
| Amazon | **SP-API — Product Pricing API** (`getCompetitivePricing`) | Free (private seller app) | Official API — no scraping. Returns competitive pricing per ASIN. Rate limit: 0.5 req/sec → throttle with 2s delay between calls. 100 SKUs ≈ 3.5 min. Free if tool is built for your own seller account only; $1,400 USD/year if built as a third-party developer app. |
| eBay | **eBay Browse API** (`findItemsByKeywords`) | Free with developer account | Official API — no scraping. Returns active listings with prices. 5,000 calls/day default; higher limits via Application Growth Check. |
| BestBuy Marketplace | **BeautifulSoup + Playwright** (with stealth + residential proxies) | Free + ~$5–30/mo proxy cost | No official BestBuy Canada API exists. BestBuy.ca has no public pricing API and Rainforest API is Amazon-only. Direct scraping with Playwright (stealth-patched) is the only reliable programmatic option. BestBuy.ca uses aggressive bot detection (Akamai) — plain requests or datacenter IPs will be blocked. Residential proxies required. **Pre-build action:** Inspect a BestBuy.ca phone listing page manually — as a Mirakl-powered marketplace, it may make internal JSON API calls for seller offers that can be targeted directly with `requests`, bypassing full browser rendering. |
| Reebelo | **Direct scraper** (Python + `requests`/`playwright`) | Free | Reebelo's Cobalt seller API is for managing your own listings, not for reading competitor prices. Scrape Reebelo search/listing pages for competitor prices by model + grade. Rate-limit requests; add 1–2s delay between calls. |

**Note:** Amazon and eBay use official seller APIs — no scraping risk. BestBuy and Reebelo require direct scraping for competitor price data. Rainforest API is **Amazon-only** and is not applicable to any other platform in this workflow.

### Listing Creation — Per Platform

#### Amazon
Amazon used listings match to an **existing ASIN** in their catalog. You are not creating a new product page — you provide condition, price, and quantity against an existing catalog entry. Amazon pulls title, images, and description automatically.

| Need | Tool | Notes |
|---|---|---|
| Authentication | `python-amazon-sp-api` (pip install) | Handles OAuth LWA token refresh automatically |
| Create/update listing | SP-API Listings Items API (`PUT /listings/2021-08-01/items/{sellerId}/{sku}`) | Provide: ASIN, condition, condition note, price, quantity, seller SKU |
| Images | Not required | ASIN catalog images used automatically |
| Category | Not required | Inferred from ASIN |

#### eBay
eBay is a two-step process: create an inventory item (defines the product), then create and publish an offer (defines price, quantity, marketplace).

| Need | Tool | Notes |
|---|---|---|
| Authentication | eBay OAuth 2.0 via `requests` | Store refresh token in config; exchange for access token at runtime |
| Create inventory item | eBay Inventory API (`PUT /sell/inventory/v1/inventory_item/{sku}`) | Provide: title, description, condition, images, item specifics |
| Create + publish offer | eBay Inventory API (`POST /offer` → `POST /offer/{id}/publish`) | Provide: price, quantity, category ID, listing policies |
| Category ID | Hardcoded | eBay Canada cell phones category (e.g. `9355`) |
| Item specifics | Hardcoded mapping | eBay requires structured fields: Brand, Model, Storage, Colour, Network, Condition — not just free text |
| Images | Required — see Image Strategy below | |

#### BestBuy Marketplace
Matches to existing BestBuy catalog by UPC/EAN. Same pattern as Amazon — you provide an offer against an existing catalog item.

| Need | Tool | Notes |
|---|---|---|
| Authentication | API key via BestBuy Marketplace Seller Portal | |
| Create offer | BestBuy Marketplace Seller API | Provide: UPC/EAN, condition, price, quantity |
| Images | Not required | BestBuy catalog images used automatically |
| Category | Not required | Inferred from catalog match |

#### Reebelo
Reebelo is a true third-party marketplace with a documented seller API via their **Cobalt** platform (cobalt.reebelo.com). Listing creation can be programmatic. Fee structure: $99 USD/month flat + 10–15% commission per sale.

| Need | Tool | Notes |
|---|---|---|
| Competitor price data | Python scraper (`requests` + `BeautifulSoup` or `playwright`) | Cobalt API manages your own listings only — scrape Reebelo public pages for competitor prices by model + grade |
| Create listing | **Reebelo Cobalt API** | Documented API supports creating/updating products, inventory, and prices programmatically. Full docs require a seller account login at cobalt.reebelo.com/documentation/custom-api |
| Multichannel option | Sellercloud / ChannelEngine | Both have documented Reebelo integrations — viable if already using a multichannel tool |
| Images | Required — confirm Reebelo requirements | Likely stock images per model; confirm via Cobalt docs |
| Category / condition | Confirm via Cobalt API docs | Map internal grades (A/B/C) to Reebelo's condition taxonomy |

> **Action item:** Obtain Reebelo seller account to access full Cobalt API documentation and confirm listing fields, condition labels, and image requirements before implementation.

---

### Image Strategy (eBay Only)

Amazon and BestBuy use catalog images automatically. eBay requires images on every listing. Three options evaluated:

| Option | Recommendation | Notes |
|---|---|---|
| eBay Product Catalog match | **First choice** | Most major iPhones and Samsung devices are in eBay's catalog — catalog images applied automatically via `epid` (eBay Product ID). Requires a catalog lookup step. |
| S3 image library (fallback) | **Second choice** | One-time build of ~50–100 stock device images by model, stored in AWS S3. Used when eBay catalog match fails. Cost: ~$1–2/mo. |
| Pull stock image from web at runtime | Not recommended | Fragile, potential copyright issues, eBay may reject hotlinked images. |

---

### Listing Content Generation

AI (DeepSeek V3 or Claude) generates the text layer by analyzing top competitor listings from the winning marketplace.

| Input | Output |
|---|---|
| 3–5 competitor listings for same model + grade | Title, description, bullet points, condition note |

**Listing format (confirmed):** One listing per product group — `Quantity × Model × Grade`
- Example: *"6x Apple iPhone 14 128GB — Grade A (Used – Like New)"*
- Price set at the floor price of the winning marketplace

**Grade → Marketplace condition mapping (to be agreed internally before launch):**
| Internal Grade | Amazon Condition | eBay Condition |
|---|---|---|
| A | Used – Like New | Used – Excellent |
| B | Used – Very Good | Used – Very Good |
| C | Used – Good | Used – Good |

---

### Python Libraries Required

| Library | Purpose | Cost |
|---|---|---|
| `python-amazon-sp-api` | Amazon SP-API wrapper — OAuth, rate limiting, retries | Free (open source) |
| `requests` | eBay and BestBuy API calls | Free |
| `boto3` | AWS S3 access for eBay image hosting (if needed) | Free |
| `jinja2` | HTML description templating for eBay listings | Free |
| `beautifulsoup4` + `playwright-extra` | BestBuy and Reebelo scraping — `bs4` for HTML parsing, `playwright-extra` with stealth plugin patches headless browser signals that trigger bot detection | Free |
| `playwright-extra-plugin-stealth` | Patches `navigator.webdriver` and other fingerprint signals detected by BestBuy.ca's Akamai bot protection | Free |

All installable via pip on the existing EC2. No new infrastructure required.

---

## Infrastructure Fit

No new infrastructure required. This runs on the existing Linux EC2.

| Component | How Used |
|---|---|
| Linux EC2 | Runs `ecommerce_agent.py` via cron + Flask approval endpoint |
| SQL Server | Inventory data (`ReportingInventoryFlat`) + listings log (`EcommerceListingsLog`) + ASIN/UPC lookup table |
| AWS S3 (optional) | eBay image hosting fallback — only needed if eBay catalog match fails |
| Marketplace APIs | Called outbound from Linux EC2 (Amazon SP-API, eBay APIs, BestBuy Seller API, Reebelo Cobalt API) |
| Residential proxy service | Required for BestBuy.ca scraping — EC2 datacenter IPs are blocked by Akamai bot protection. ~$5–30/mo at 100 req/day volume. (Providers: Oxylabs, Bright Data, Webshare) |

### Pre-Build Requirement: ASIN / UPC Lookup Table

Amazon and BestBuy require a product identifier (ASIN or UPC/EAN) to match listings to their catalogs. Your flat table has `Manufacturer + Model + Grade + Colour` but not these identifiers. A lookup table must be built in SQL Server before implementation begins.

```sql
-- EcommerceProductCatalog (one-time manual build, ~50–100 rows)
CREATE TABLE EcommerceProductCatalog (
    Manufacturer    nvarchar(100),
    Model           nvarchar(100),
    Storage         nvarchar(50),   -- e.g. '128GB', '256GB'
    Colour          nvarchar(50),
    AmazonASIN      nvarchar(20),
    UPC             nvarchar(20),   -- used for BestBuy matching
    EbayEPID        nvarchar(20)    -- optional: eBay catalog product ID
)
```

> This is a one-time manual build covering your typical SKU range. Maintained by adding a row whenever a new model enters the Ecommerce Storefront for the first time. If `Storage` is not currently captured in `ReportingInventoryFlat`, it must be added as a column before this lookup will work reliably.

---

## Volume & API Considerations

- **~100 distinct SKUs** expected in Ecommerce Storefront at any given time
- Daily scan = 100 SKUs × 4 marketplaces = **400 price lookups/day**
- Amazon SP-API: 100 calls at 0.5 req/sec = ~3.5 minutes — within limits
- eBay Browse API: No meaningful rate limit concern at this volume
- BestBuy scraper: 100 page requests/day via Playwright + residential proxies — low volume; pace at 2–3s between requests
- Reebelo scraper: 100 page requests/day — low volume; add 1–2s delay between requests to avoid triggering bot detection
- Email approval: **daily digest** (one email, one row per SKU, individual approve/reject links) — not 100 separate emails

---

## Phasing

**Confirmed: Phase 1D** — the final sub-phase of Phase 1. Builds directly on the existing flat table infrastructure. No dependency on HubSpot or any Phase 2+ work.

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **ASIN / UPC matching** — Amazon and BestBuy require a product identifier to match catalog listings. Flat table has model name but not ASIN or UPC. | High | Build `EcommerceProductCatalog` lookup table in SQL Server before implementation (see Infrastructure Fit). Confirm whether storage capacity is captured in inventory data — required for accurate ASIN matching. |
| **Rejected/skipped SKUs falling through** — `Product_Placement_Created` filter only catches previous business day. Unapproved items won't be reprocessed. | Medium | Fallback query (see Inventory Data Structure) catches any SKU in Ecommerce Storefront with no active listing record, regardless of date. |
| **Public holidays** — Previous business day logic doesn't account for Canadian holidays; could skip a day or double-process. | Low | Flag for future improvement. Manually re-trigger if needed on post-holiday mornings. |
| **Grade → condition mapping** — Internal grades (A/B/C) don't match marketplace condition labels. | Medium | Mapping defined in Listing Content Generation section. Agree internally before launch. |
| **Stale pricing / bad floor price** — A one-off $50 listing could skew the floor price and cause under-pricing. | Medium | Add a sanity check: if recommended price < `DeviceCost` + minimum margin threshold, skip the SKU and flag it in the email rather than auto-proceeding. |
| **Overselling** — Flat table refreshes hourly; a device could sell after the last refresh but before listing is posted. | Medium | Run the cron job immediately after a scheduled flat table refresh. Log all active listings in SQL Server and deduct from available quantity on next run. |
| **Listings not delisted** — If a product sells or moves out of Ecommerce Storefront, the live marketplace listing stays up. | High | Daily job must reconcile active listing log against current flat table. Any SKU no longer in Ecommerce Storefront → call marketplace API to end listing. |
| **Amazon SP-API rate limits** — 0.5 req/sec on `getCompetitivePricing`. | Low | Add `time.sleep(2)` between Amazon API calls. 100 SKUs completes in ~3.5 minutes — no issue. |
| **Rainforest API cost** | Low | ~$50–200/mo depending on tier. 100 BestBuy lookups/day is light usage — likely the entry tier. |
| **BestBuy.ca bot detection** — No official API exists. Scraping required, but BestBuy.ca uses Akamai bot protection; datacenter IPs (EC2) will be blocked without additional hardening. | High | Use `playwright-extra` with stealth plugin + residential proxy rotation. Keep request rate low (2–3s delay). **Pre-build:** Manually inspect a BestBuy.ca phone listing page to check if Mirakl's internal seller-offer JSON endpoint is callable directly with `requests` — this would bypass full browser rendering and simplify the stack significantly. |
| **Reebelo scraper fragility** — Cobalt API is for managing your own listings, not reading competitor prices; public page scraper depends on HTML structure. | Medium | Build scraper with clear CSS/XPath selectors and add error handling so failures surface in logs rather than silently skipping Reebelo pricing. Re-test after any Reebelo site update. |
| **Reebelo bot detection** — Scraping may be blocked if Reebelo implements rate limiting or bot detection. | Medium | Add request delays (1–2s), rotate user-agent headers. If blocked, consider Playwright with a real browser context. Check Reebelo's `robots.txt` before launch. |
| **Reebelo Cobalt API access** — Full API documentation requires an active seller account. Listing fields, condition taxonomy, and image requirements are unknown until access is granted. | Medium | Obtain Reebelo seller account early to unblock API implementation. $99 USD/month + 10–15% commission. |

---

## Confirmed Decisions

| Decision | Answer |
|---|---|
| Marketplace seller status | Approved on Amazon Seller Central, eBay, BestBuy Marketplace, and Reebelo |
| Pricing algorithm | Highest floor price across marketplaces — list at that price |
| Approval UX | Email digest (one email, one row per SKU, individual approve/reject links) |
| SKU volume | ~100 distinct SKUs in Ecommerce Storefront at a time |
| Listing granularity | One listing per product group: Quantity × Model × Grade |
| Daily filter | `Product_Placement_Created` = previous business day + fallback for unlisted SKUs |

---

*For infrastructure context, refer to `README.md` and `AI_Implementation_Plan.md`.*
