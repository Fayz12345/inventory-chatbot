# Ecommerce AI Plan
### Internal Document — Management Team

**Prepared:** March 2026
**Updated:** April 2026
**Status:** Implementation — Phase 1D (final sub-phase of Phase 1, after Inventory Intelligence)

---

## Overview

This phase adds an AI-powered ecommerce listing workflow that scans inventory flagged for ecommerce, researches competitive prices across four Canadian marketplaces via Octoparse web scraping, recommends the best platform to sell on, and — upon human approval — drafts and posts the listing automatically.

**Scope:** Amazon Canada, eBay Canada, Best Buy Marketplace Canada, and Reebelo Canada — all four marketplaces from day one via Octoparse cloud extraction. Price scanning runs weekly (Monday mornings EST). Listing creation via marketplace APIs remains a later sub-phase.

**Why Octoparse instead of marketplace APIs?** Getting approved for Amazon SP-API and eBay Browse API has been tedious. Octoparse provides a unified scraping approach across all four marketplaces with built-in IP rotation, cloud extraction, and bot humanization — no per-marketplace API credentials needed for price intelligence.

---

## Workflow (End-to-End)

```
Linux cron job (weekly, Monday 6:00 AM EST) → python -m ecommerce.main
    ↓
Query ReportingInventoryFlat → find all SKUs in 'Ecommerce Storefront' with no active listing in EcommerceListingsLog
    ↓
Reconcile against active listings table → skip already-listed SKUs, delist removed SKUs
    ↓
Build search keyword list from product groups (e.g. "iPhone 14 128GB Grade A")
    ↓
Trigger Octoparse cloud tasks via API (4 scrapers — one per marketplace):
    → Amazon Canada — template: amazon-product-details-scraper (by ASIN)
    → eBay Canada — template: ebay-product-list-scraper-by-keyword (by keyword, country=Canada)
    → Best Buy / Reebelo — template: google-shopping-product-listing-scraper (by keyword, captures aggregated prices)
    ↓
    Octoparse cloud runs with IP rotation + humanized behavior (random delays, scrolling)
    First page only per search — lightweight jobs, ~100 SKUs total
    ↓
Poll Octoparse API → export scraped data as JSON
    ↓
Parse results → extract floor prices per marketplace per SKU
    ↓
Sanity check: skip any SKU where best price < DeviceCost + minimum margin
    ↓
Pricing algorithm (deterministic — no AI needed):
    → Find lowest listed price per marketplace
    → Pick the marketplace with the highest floor price
    → Set listing price = that floor price
    ↓
Recommendations persisted to SQL Server (EcommercePricingBatch + EcommercePricingRecommendation)
    ↓
Approver visits /ecommerce/dashboard in browser:
    One row per SKU — recommended marketplace, price, all 4 floor prices, approve/reject buttons
    ↓ [on approve click — AJAX POST to Flask endpoint on EC2]
Claude API drafts listing title + description + bullet points
    ↓
[1D-ii — current] Preview modal with copy-to-clipboard — human pastes to marketplace manually
    ↓
[1D-iii — future] Post via marketplace API (eBay Inventory API / Amazon SP-API) automatically
    ↓
Log listing record to SQL Server (SKU, platform, price, timestamp, status)
```

---

## Sub-Phases

Phase 1D is broken into two sub-phases. Each delivers working value independently.

| Sub-Phase | Scope | Deliverable |
|---|---|---|
| **1D-i** | Octoparse price scanning across all 4 marketplaces + web dashboard | Weekly pipeline writes recommendations to SQL Server. Approver visits `/ecommerce/dashboard` to review recommended marketplace + price per SKU across Amazon CA, eBay CA, Best Buy CA, and Reebelo CA. No auto-listing yet — human reviews and lists manually. Proves the data pipeline end-to-end. |
| **1D-ii (current)** | Approval flow + listing preview | Approve button on dashboard → Claude generates listing copy → preview modal with copy-to-clipboard. Human pastes to marketplace manually. Builds confidence before enabling API auto-listing. |
| **1D-iii** | Auto-listing via marketplace APIs | Approve button → Claude generates copy → posts to Amazon SP-API / eBay Inventory API automatically. Marketplace API credentials needed at this stage. |

> **Why the interim 1D-ii step?** We want to validate listing quality and pricing recommendations manually before giving the system direct marketplace API access. Once we're confident, 1D-iii flips the approve action from "preview + copy-paste" to "auto-post via API".

---

## Inventory Data Structure

No schema changes required to `ReportingInventoryFlat`. The pipeline queries existing columns only.

**Daily query — unlisted SKUs with no active listing record:**
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
> Picks up any SKU in Ecommerce Storefront that doesn't already have an active listing. Automatically catches new placements, previously rejected SKUs, and missed items.

---

## Pricing Algorithm

**Rule:** For each marketplace, find the lowest listed price for the SKU. Pick the marketplace with the highest of those floor prices. List at that price.

**This is deterministic — no AI/LLM needed.** It's a `max()` over a dict of floor prices. The Python implementation is ~10 lines.

**Example (now across 4 marketplaces):**
| Marketplace | Lowest Competitor Price |
|---|---|
| Amazon CA | $750 |
| eBay CA | $800 |
| Best Buy CA | $820 |
| Reebelo CA | $690 |

→ Best Buy wins (floor = $820). List at **$820**.

**Why this works:** You enter the market where even the cheapest seller is selling high, maximizing your sale price while remaining competitive.

**Sanity check:** If recommended price < `DeviceCost` + configurable margin threshold → skip the SKU and flag it on the dashboard instead of recommending it.

**Google Shopping attribution:** Best Buy and Reebelo prices are extracted from Google Shopping results by matching the seller name field (e.g. "Best Buy", "Reebelo"). If a product appears from neither seller, those marketplaces return `None` for that SKU.

---

## Technology Stack

### AI Model

| Task | Tool | Rationale |
|---|---|---|
| Listing copy generation | **Claude API** (already in stack) | Generates title, description, bullet points from competitor listing analysis. Already authenticated, already paid for, already proven in this project. |

> **Why not DeepSeek V3?** The pricing algorithm is deterministic and doesn't need an LLM. The only AI task is listing copy generation, and Claude is already integrated. Adding a second AI provider adds credential management, a second billing relationship, and a second failure mode — for no clear benefit. If cost becomes a concern at scale, swap Claude for a cheaper model at that point.

### Price Intelligence — Apify Cloud Scraping (Sub-Phase 1D-i)

All price data is gathered via **Apify cloud actors** — no marketplace API credentials needed for pricing. Apify provides full API access on all plans (including Free), an official Python SDK (`apify-client`), and 22,000+ pre-built scraping actors.

> **Why Apify instead of Octoparse?** Octoparse's Standard plan ($69/mo) does not include API access for starting tasks programmatically — that requires the Professional plan ($249/mo). Apify provides full API access on all plans starting at $29/mo, has a mature Python SDK, and offers pre-built actors for all target marketplaces including a dedicated Best Buy Canada scraper.

| Marketplace | Apify Actor | Parameters | Notes |
|---|---|---|---|
| **Amazon Canada** | `automation-lab/amazon-scraper` | ASINs + country='CA' | Scrapes amazon.ca product pages by ASIN. Extracts title, price, ratings, seller info. |
| **eBay Canada** | `automation-lab/ebay-scraper` | Keywords + site='ebay.ca' | Keyword search on ebay.ca. Extracts title, price, URL, rating. First page only. |
| **Best Buy Canada** | `automation-lab/google-shopping-scraper` | Keywords + countryCode='CA' | Google Shopping aggregates Best Buy Marketplace CA listings with prices. Attributed by seller name. |
| **Reebelo Canada** | `automation-lab/google-shopping-scraper` | Keywords + countryCode='CA' | Google Shopping captures Reebelo CA listings alongside other sellers. Attributed by seller name. |

> **Why Google Shopping for Best Buy + Reebelo?** Google Shopping aggregates prices across sellers (including Best Buy Marketplace and Reebelo), providing a single scrape that covers both. The pipeline parses results to attribute prices back to the correct marketplace by seller name. A dedicated Best Buy CA actor (`saswave/bestbuy-ca-product-availability`) exists for future use if direct SKU-based lookups are needed.

#### Anti-Detection & IP Safety Strategy

| Concern | Mitigation |
|---|---|
| **IP blacklisting** | Apify cloud uses automatic **proxy rotation** across datacenter and residential pools. No single IP hits any site repeatedly. |
| **Bot detection** | Apify actors use Playwright/Puppeteer with **anti-detection measures**: fingerprint randomization, human-like behavior patterns, varied user-agent strings. |
| **Request volume** | **First page only** per search, **once per week** (Monday 6:00 AM EST). ~200 SKUs × 3 actor runs = ~600 page loads/week — negligible volume. |
| **Rate limiting** | Weekly cadence ensures no marketplace sees frequent automated traffic. Monday early morning avoids peak hours. |
| **Fingerprinting** | Cloud extraction runs on Apify's managed browser fleet — no local fingerprint exposed. |

### Orchestration

| Tool | Role |
|---|---|
| **Linux cron job** | Weekly trigger (Monday 6:00 AM EST) — runs `python -m ecommerce.main` on the existing EC2 |
| **Apify Cloud API** | Runs scraping actors remotely with proxy rotation. Python SDK calls `actor.call()` → blocks until complete → retrieves dataset |
| **Python modules** | Structured package (see Module Structure below) |
| **Flask (existing)** | Serves the pricing dashboard at `/ecommerce/dashboard` — handles approve/reject actions via AJAX |

---

## Module Structure

```
inventory-chatbot/
├── app.py                          # Existing chatbot (unchanged)
├── config.py                       # Existing config (add Apify API token + ecommerce keys)
├── ecommerce/
│   ├── __init__.py
│   ├── main.py                     # Entry point — orchestrates the weekly pipeline
│   ├── config.py                   # Ecommerce-specific settings (thresholds, Apify config)
│   ├── db.py                       # SQL queries — inventory fetch, listings log CRUD, reconciliation
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── apify_client.py         # Apify SDK wrapper — run actors, retrieve datasets
│   │   ├── amazon.py               # Run Amazon actor → extract floor prices by ASIN
│   │   ├── ebay.py                 # Run eBay actor → extract floor prices by keyword
│   │   ├── google_shopping.py      # Run Google Shopping actor → attribute prices to Best Buy / Reebelo by seller name
│   │   └── algorithm.py            # Deterministic pricing: highest floor price across 4 marketplaces
│   ├── listings/
│   │   ├── __init__.py
│   │   ├── amazon.py               # Amazon SP-API listing creation (Sub-Phase 1D-ii)
│   │   ├── ebay.py                 # eBay Inventory API listing creation (Sub-Phase 1D-ii)
│   │   └── copy_generator.py       # Claude API — generates listing title/description/bullets
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── email_digest.py         # Jinja2 HTML templates for the web dashboard (batch list + detail page)
│   └── approval.py                 # Flask Blueprint — /ecommerce/dashboard (batch list + detail), approve/reject via AJAX POST
```

**What changed from the original structure:**
- `pricing/amazon.py` and `pricing/ebay.py` — rewritten to use Apify actors instead of direct marketplace APIs
- `pricing/apify_client.py` — **new** — Apify SDK wrapper (run actors, poll, retrieve datasets). Replaces `octoparse_client.py`.
- `pricing/google_shopping.py` — **new** — runs Google Shopping actor, attributes prices to Best Buy and Reebelo by seller name
- `pricing/algorithm.py` — expanded to compare 4 marketplaces instead of 2

---

## Listing Creation — Per Platform

### Amazon
Amazon used listings match to an **existing ASIN** in their catalog. You provide condition, price, and quantity against an existing catalog entry.

| Need | Tool | Notes |
|---|---|---|
| Authentication | `python-amazon-sp-api` (pip) | Handles OAuth LWA token refresh automatically |
| Create/update listing | SP-API Listings Items API (`PUT /listings/2021-08-01/items/{sellerId}/{sku}`) | Provide: ASIN, condition, condition note, price, quantity, seller SKU |
| Images | Not required | ASIN catalog images used automatically |
| Category | Not required | Inferred from ASIN |

### eBay
Two-step process: create inventory item (product), then create and publish an offer (price + marketplace).

| Need | Tool | Notes |
|---|---|---|
| Authentication | eBay OAuth 2.0 via `requests` | Store refresh token in config; exchange for access token at runtime |
| Create inventory item | eBay Inventory API (`PUT /sell/inventory/v1/inventory_item/{sku}`) | Title, description, condition, images, item specifics |
| Create + publish offer | eBay Inventory API (`POST /offer` → `POST /offer/{id}/publish`) | Price, quantity, category ID, listing policies |
| Category ID | Hardcoded | eBay Canada cell phones category (e.g. `9355`) |
| Item specifics | Hardcoded mapping | Brand, Model, Storage, Colour, Network, Condition |
| Images | Required — see Image Strategy below | |

---

## Image Strategy (eBay Only)

Amazon uses catalog images automatically. eBay requires images on every listing.

| Option | Recommendation | Notes |
|---|---|---|
| eBay Product Catalog match | **First choice** | Major iPhones/Samsung devices are in eBay's catalog — catalog images applied via `epid`. Requires a catalog lookup step. |
| S3 image library (fallback) | **Second choice** | One-time build of ~50–100 stock device images by model in AWS S3. Used when catalog match fails. Cost: ~$1–2/mo. |

---

## Listing Content Generation

Claude generates listing text by analyzing top competitor listings from the winning marketplace.

| Input | Output |
|---|---|
| 3–5 competitor listings for same model + grade | Title, description, bullet points, condition note |

**Listing format:** One listing per product group — `Quantity x Model x Grade`
- Example: *"6x Apple iPhone 14 128GB — Grade A (Used – Like New)"*
- Price set at the floor price of the winning marketplace

**Grade → Marketplace condition mapping (to be agreed internally before launch):**
| Internal Grade | Amazon Condition | eBay Condition |
|---|---|---|
| A | Used – Like New | Used – Excellent |
| B | Used – Very Good | Used – Very Good |
| C | Used – Good | Used – Good |

---

## Database Tables

### EcommerceListingsLog (new)
Tracks all listings created by the system.

```sql
CREATE TABLE EcommerceListingsLog (
    ID                  int IDENTITY(1,1) PRIMARY KEY,
    Manufacturer        nvarchar(100),
    Model               nvarchar(100),
    Colour              nvarchar(50),
    Grade               nvarchar(20),
    Quantity            int,
    Platform            nvarchar(50),       -- 'Amazon', 'eBay'
    ListingPrice        decimal(10,2),
    FloorPriceAtListing decimal(10,2),      -- what the floor was when we listed
    PlatformListingID   nvarchar(100),      -- marketplace's listing/offer ID
    Status              nvarchar(20),       -- 'active', 'ended', 'sold', 'rejected'
    CreatedAt           datetime DEFAULT GETDATE(),
    EndedAt             datetime NULL,
    ApprovedBy          nvarchar(100) NULL
)
```

### EcommerceProductCatalog (new)
Lookup table for marketplace product identifiers. One-time manual build (~50–100 rows).

```sql
CREATE TABLE EcommerceProductCatalog (
    Manufacturer    nvarchar(100),
    Model           nvarchar(100),
    Colour          nvarchar(50),
    AmazonASIN      nvarchar(20),
    UPC             nvarchar(20),
    EbayEPID        nvarchar(20)    -- eBay catalog product ID (for image matching)
)
```

> Storage capacity is tracked within the Model attribute (e.g. "iPhone 14 128GB"), so no separate Storage column is needed.

---

## Python Libraries Required

| Library | Purpose | Cost |
|---|---|---|
| `apify-client` | Apify Python SDK — run actors, retrieve datasets | Free |
| `jinja2` | HTML dashboard page templating | Free |
| `python-amazon-sp-api` | Amazon SP-API listing creation (Sub-Phase 1D-ii only) | Free |
| `boto3` | AWS S3 access for eBay image hosting (if needed, 1D-ii) | Free |

> **Simplified for 1D-i:** Only `apify-client`, `jinja2`, and `python-dotenv` are needed for the price scanning phase. `python-amazon-sp-api` is deferred to 1D-ii when auto-listing begins.

All installable via pip on the existing EC2. No new infrastructure required.

---

## Infrastructure Fit

No new infrastructure. Runs on the existing Linux EC2.

| Component | How Used |
|---|---|
| Linux EC2 | Runs ecommerce pipeline via cron + Flask approval endpoint |
| SQL Server | Inventory data + listings log + product catalog |
| **Apify Cloud** | Runs scraping actors remotely — EC2 calls the Python SDK |
| AWS S3 (optional) | eBay image hosting fallback (1D-ii) |
| Marketplace APIs | Outbound from EC2 for listing creation only (1D-ii) |

---

## Volume & Scraping Considerations

- **~200 distinct SKUs** in Ecommerce Storefront (actual count as of April 2026)
- **Weekly scan** (Monday 6:00 AM EST) — not daily. Reduces detection risk and is sufficient for used device pricing which doesn't change hourly.
- **3 Apify actor runs per week:**
  - Amazon CA: ASINs from `EcommerceProductCatalog` → single actor run
  - eBay CA: ~200 keywords → single actor run, first page per keyword
  - Google Shopping: ~200 keywords → single actor run (covers Best Buy + Reebelo)
- **Estimated Apify cost:** ~$29/month (Starter plan) covers compute credits. Residential proxies extra at $7-8/GB if needed.
- **Apify handles proxy rotation automatically** — datacenter proxies included on all plans
- Dashboard: **weekly batch** written to SQL Server, viewable at `/ecommerce/dashboard` (one row per SKU, inline approve/reject)
- Claude API: ~100 calls/week for listing copy generation (only on approved SKUs) — minimal token cost

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **ASIN / UPC matching** — Amazon scraper needs ASINs. Flat table has model name but not ASIN. | High | Build `EcommerceProductCatalog` lookup table before implementation. Storage is embedded in the Model attribute. |
| **Stale pricing / bad floor price** — a one-off $50 listing could cause under-pricing. | Medium | Sanity check: skip any SKU where price < DeviceCost + margin threshold. Flag in email. |
| **Overselling** — flat table refreshes hourly; device could sell between refresh and listing. | Medium | Run cron immediately after flat table refresh. Log active listings and deduct from available quantity on next run. |
| **Listings not delisted** — product sells or moves out of Ecommerce Storefront but listing stays up. | High | Weekly reconciliation: compare active listings log against current flat table. Auto-delist via API for any SKU no longer in Ecommerce Storefront. |
| **Apify actor failures** — actor breaks if site layout changes. | Medium | Apify actors are maintained by their publishers and updated when sites change. Monitor export data for empty results — they will appear as N/A on the dashboard. |
| **Google Shopping seller attribution** — Best Buy or Reebelo may not appear in Google Shopping results for every product. | Medium | If seller name doesn't match, that marketplace returns `None` for the SKU. Algorithm still works with partial data. |
| **Apify downtime / rate limits** | Low | Weekly cadence means one attempt per week. SDK has built-in retry. Log failure — partial data will appear on the dashboard. |
| **Grade → condition mapping** — internal grades don't match marketplace labels. | Medium | Mapping defined above. Agree internally before launch. |
| **IP blacklisting** | Low | Apify proxy rotation + first-page-only + weekly cadence = negligible footprint. No single IP is reused. |

---

## Implementation Order (Sub-Phase 1D-i)

This is the build sequence for the first deliverable: weekly price scan + web dashboard.

| Step | Task | Dependencies |
|---|---|---|
| 1 | Create `EcommerceProductCatalog` table + populate for top ~50 SKUs | Manual data entry (ASINs from Amazon, UPCs from packaging) |
| 2 | Create `EcommerceListingsLog` table | SQL Server access |
| 3 | Build `ecommerce/db.py` — inventory queries + listings log CRUD | Steps 1–2 |
| 4 | Build `ecommerce/pricing/apify_client.py` — Apify SDK wrapper (run actors, retrieve datasets) | Apify API token |
| 5 | Build `ecommerce/pricing/amazon.py` — parse Amazon scrape data → extract floor prices | Step 4 |
| 6 | Build `ecommerce/pricing/ebay.py` — parse eBay scrape data → extract floor prices | Step 4 |
| 7 | Build `ecommerce/pricing/google_shopping.py` — parse Google Shopping data → attribute Best Buy / Reebelo prices | Step 4 |
| 8 | Build `ecommerce/pricing/algorithm.py` — highest floor price across 4 marketplaces | None |
| 9 | Build `ecommerce/notifications/email_digest.py` — Jinja2 HTML templates for dashboard | None |
| 10 | Build `ecommerce/main.py` — orchestrates steps 3–9, persists batch + recommendations to DB | All above |
| 11 | Set up cron job on EC2: `0 11 * * 1` (Monday 6:00 AM EST = 11:00 UTC) | Step 10 |
| 12 | **Test for 2–3 weeks** — validate pricing recommendations manually before enabling auto-listing | None |

Sub-phase 1D-ii (auto-listing) begins only after 1D-i email recommendations have been validated manually.

### Apify Integration Detail (Step 4)

The `apify_client.py` module wraps the official Apify Python SDK. The pipeline flow per scraper:

```
1. client.actor(actor_id).call(run_input={...})
   → Starts the actor on Apify cloud with dynamic parameters
   → SDK blocks with smart polling until the run completes

2. client.dataset(run['defaultDatasetId']).list_items()
   → Retrieves structured JSON results from the completed run

3. Parse results → normalize into per-SKU price records
```

**Configuration needed in `config.py`:**
```python
# Apify
APIFY_API_TOKEN = ''  # From Apify account → Settings → Integrations
```

**Actor IDs are defined in each pricing module** (not config) since they rarely change:
- Amazon: `automation-lab/amazon-scraper`
- eBay: `automation-lab/ebay-scraper`
- Google Shopping: `automation-lab/google-shopping-scraper`

---

## Confirmed Decisions

| Decision | Answer |
|---|---|
| **Price intelligence tool** | **Apify cloud actors** — replaces direct marketplace API calls for pricing |
| **Marketplaces (pricing)** | All 4 from day one: Amazon CA, eBay CA, Best Buy CA, Reebelo CA |
| **Scan frequency** | Weekly — Monday 6:00 AM EST (not daily) |
| **Scrape depth** | First page only per search — keeps jobs lightweight |
| **IP safety** | Apify proxy rotation + weekly cadence + first-page-only |
| Marketplace seller status | Approved on Amazon Seller Central and eBay |
| Pricing algorithm | Highest floor price across 4 marketplaces — deterministic, no AI |
| AI model for listing copy | Claude API (already in stack) |
| Approval UX | Web dashboard at `/ecommerce/dashboard` — one row per SKU, inline approve/reject buttons, persisted in SQL Server |
| SKU volume | ~100 distinct SKUs in Ecommerce Storefront at a time |
| Listing granularity | One listing per product group: Quantity x Model x Grade |
| Weekly filter | All unlisted SKUs in Ecommerce Storefront (no active listing in EcommerceListingsLog) |

---

## What Was Removed From the Original Plan (and Why)

| Removed | Reason |
|---|---|
| **Amazon SP-API for pricing** | Replaced by Apify scraping. SP-API approval was tedious and rate-limited (0.5 req/sec). SP-API retained for listing creation in 1D-ii. |
| **eBay Browse API for pricing** | Replaced by Apify scraping. eBay developer account approval was tedious. eBay API retained for listing creation in 1D-ii. |
| **Daily scan cadence** | Changed to weekly (Monday AM). Used device prices don't change hourly. Weekly reduces detection risk. |
| **Sub-Phase 1D-iii** | Eliminated. BestBuy and Reebelo are no longer deferred — Google Shopping scraping covers them from day one. |
| **Octoparse** | Replaced by Apify. Octoparse Standard plan ($69/mo) did not include API access for programmatic task execution — required Professional ($249/mo). Apify provides full API + Python SDK on all plans starting at $29/mo. |
| DeepSeek V3 for pricing | Pricing algorithm is deterministic (`max()` over floor prices). No LLM needed. |
| BestBuy.ca scraping (Playwright + stealth + residential proxies) | No longer needed. Google Shopping actor captures Best Buy Marketplace prices without Akamai bypass. |
| Reebelo custom scraping | No longer needed. Google Shopping captures Reebelo listings. |
| Rainforest API | Amazon-only, redundant. Apify handles Amazon scraping. |
| DeepSeek as second AI provider | Adds second billing, second set of credentials, second failure mode. Claude already integrated. |
| `playwright-extra` + `playwright-extra-plugin-stealth` | Not needed. Apify cloud handles browser automation and anti-detection. |
| `beautifulsoup4` | Not needed. Apify exports structured JSON — no HTML parsing required. |
| `python-amazon-sp-api` (for 1D-i) | Deferred to 1D-ii. Not needed for price scanning — only for listing creation. |

---

*For infrastructure context, refer to `README.md` and `AI_Implementation_Plan.md`.*
