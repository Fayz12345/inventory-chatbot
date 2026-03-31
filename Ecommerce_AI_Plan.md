# Ecommerce AI Plan
### Internal Document — Management Team

**Prepared:** March 2026
**Status:** Planning — Phase 1D (final sub-phase of Phase 1, after Inventory Intelligence)

---

## Overview

This phase adds an AI-powered ecommerce listing workflow that runs daily, scans inventory flagged for ecommerce, researches competitive prices via marketplace APIs, recommends the best platform to sell on, and — upon human approval — drafts and posts the listing automatically.

**Scope:** Amazon and eBay first (official APIs, no scraping). BestBuy and Reebelo added later once the core pipeline is proven.

---

## Workflow (End-to-End)

```
Linux cron job (daily, 7am) → python -m ecommerce.main
    ↓
Query ReportingInventoryFlat → find all SKUs in 'Ecommerce Storefront' with no active listing in EcommerceListingsLog
    ↓
Reconcile against active listings table → skip already-listed SKUs, delist removed SKUs
    ↓
For each unlisted product group:
    → Amazon SP-API (getCompetitivePricing)
    → eBay Browse API (findItemsByKeywords)
    ↓
Sanity check: skip any SKU where best price < DeviceCost + minimum margin
    ↓
Pricing algorithm (deterministic — no AI needed):
    → Find lowest listed price per marketplace
    → Pick the marketplace with the highest floor price
    → Set listing price = that floor price
    ↓
Email digest sent to approver:
    One row per SKU — recommended marketplace, price, approve/reject link
    ↓ [on approval click — Flask endpoint on EC2]
Fetch top 3–5 competitor listings from winning marketplace
    ↓
Claude API drafts listing title + description + bullet points
    ↓
Post via marketplace API (eBay Inventory API / Amazon SP-API)
    ↓
Log listing record to SQL Server (SKU, platform, price, timestamp, status)
```

---

## Sub-Phases

Phase 1D is broken into three sub-phases. Each delivers working value independently.

| Sub-Phase | Scope | Deliverable |
|---|---|---|
| **1D-i** | Price scanning + email digest | Daily email showing recommended marketplace + price per SKU. No auto-listing yet — human reviews and lists manually. Proves the data pipeline end-to-end. |
| **1D-ii** | Approval flow + auto-listing | Approve/reject links in email → Claude generates listing copy → posts to Amazon or eBay automatically. |
| **1D-iii** | BestBuy + Reebelo expansion | Add remaining marketplaces. Evaluate whether official APIs exist by then; if not, decide whether scraping ROI justifies the maintenance cost. |

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

**Example:**
| Marketplace | Lowest Competitor Price |
|---|---|
| Amazon | $750 |
| eBay | $800 |

→ eBay wins (floor = $800). List at **$800**.

**Why this works:** You enter the market where even the cheapest seller is selling high, maximizing your sale price while remaining competitive.

**Sanity check:** If recommended price < `DeviceCost` + configurable margin threshold → skip the SKU and flag it in the email digest instead of recommending it.

---

## Technology Stack

### AI Model

| Task | Tool | Rationale |
|---|---|---|
| Listing copy generation | **Claude API** (already in stack) | Generates title, description, bullet points from competitor listing analysis. Already authenticated, already paid for, already proven in this project. |

> **Why not DeepSeek V3?** The pricing algorithm is deterministic and doesn't need an LLM. The only AI task is listing copy generation, and Claude is already integrated. Adding a second AI provider adds credential management, a second billing relationship, and a second failure mode — for no clear benefit. If cost becomes a concern at scale, swap Claude for a cheaper model at that point.

### Price Intelligence APIs (Sub-Phase 1D-i)

| Marketplace | Tool | Cost | Notes |
|---|---|---|---|
| Amazon | **SP-API — Product Pricing API** (`getCompetitivePricing`) | Free (private seller app) | Official API. Rate limit: 0.5 req/sec → 2s delay between calls. 100 SKUs ≈ 3.5 min. |
| eBay | **eBay Browse API** (`findItemsByKeywords`) | Free with developer account | Official API. 5,000 calls/day default. |

### Future Marketplaces (Sub-Phase 1D-iii)

| Marketplace | Approach | Status |
|---|---|---|
| BestBuy | No official pricing API exists. Scraping requires Playwright + stealth plugin + residential proxies (~$5–30/mo) to bypass Akamai bot detection. **Evaluate ROI before building.** Pre-check: inspect a BestBuy.ca listing page for internal Mirakl JSON endpoints that could be called directly. | Deferred |
| Reebelo | Cobalt API is for managing own listings only, not competitor prices. Scraping required for price data. | Deferred |

> **Why defer scraping?** BestBuy.ca Akamai bypass and Reebelo scraping are fragile, require ongoing maintenance, and add residential proxy costs. Amazon + eBay cover the two largest used device marketplaces in Canada. Start there, prove the pipeline, then decide if BestBuy/Reebelo volume justifies the investment.

### Orchestration

| Tool | Role |
|---|---|
| **Linux cron job** | Daily trigger — runs `python -m ecommerce.main` on the existing EC2 |
| **Python modules** | Structured package (see Module Structure below) |
| **Flask (existing)** | Receives approval link clicks — triggers listing creation |

---

## Module Structure

```
inventory-chatbot/
├── app.py                          # Existing chatbot (unchanged)
├── config.py                       # Existing config (add ecommerce keys)
├── ecommerce/
│   ├── __init__.py
│   ├── main.py                     # Entry point — orchestrates the daily pipeline
│   ├── config.py                   # Ecommerce-specific settings (thresholds, API keys ref)
│   ├── db.py                       # SQL queries — inventory fetch, listings log CRUD, reconciliation
│   ├── pricing/
│   │   ├── __init__.py
│   │   ├── amazon.py               # Amazon SP-API price fetching
│   │   ├── ebay.py                 # eBay Browse API price fetching
│   │   └── algorithm.py            # Deterministic pricing: highest floor price selection
│   ├── listings/
│   │   ├── __init__.py
│   │   ├── amazon.py               # Amazon SP-API listing creation
│   │   ├── ebay.py                 # eBay Inventory API listing creation
│   │   └── copy_generator.py       # Claude API — generates listing title/description/bullets
│   ├── notifications/
│   │   ├── __init__.py
│   │   └── email_digest.py         # Builds and sends daily approval email
│   └── approval.py                 # Flask routes for approve/reject links (registers on existing app)
```

Each module has a single responsibility. Adding BestBuy or Reebelo later means adding one file in `pricing/` and one in `listings/`.

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
| `python-amazon-sp-api` | Amazon SP-API wrapper — OAuth, rate limiting, retries | Free |
| `requests` | eBay API calls, email sending | Free |
| `boto3` | AWS S3 access for eBay image hosting (if needed) | Free |
| `jinja2` | HTML email digest templating | Free |

All installable via pip on the existing EC2. No new infrastructure required.

---

## Infrastructure Fit

No new infrastructure. Runs on the existing Linux EC2.

| Component | How Used |
|---|---|
| Linux EC2 | Runs ecommerce pipeline via cron + Flask approval endpoint |
| SQL Server | Inventory data + listings log + product catalog |
| AWS S3 (optional) | eBay image hosting fallback |
| Marketplace APIs | Outbound from EC2 (Amazon SP-API, eBay APIs) |

---

## Volume & API Considerations

- **~100 distinct SKUs** expected in Ecommerce Storefront at any time
- Daily scan = 100 SKUs x 2 marketplaces = **200 price lookups/day**
- Amazon SP-API: 100 calls at 0.5 req/sec = ~3.5 minutes
- eBay Browse API: no meaningful rate limit concern at this volume
- Email: **daily digest** (one email, one row per SKU, individual approve/reject links)
- Claude API: ~100 calls/day for listing copy generation (only on approved SKUs) — minimal token cost

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| **ASIN / UPC matching** — Amazon requires ASIN to match catalog. Flat table has model name but not ASIN. | High | Build `EcommerceProductCatalog` lookup table before implementation. Storage is embedded in the Model attribute. |
| **Stale pricing / bad floor price** — a one-off $50 listing could cause under-pricing. | Medium | Sanity check: skip any SKU where price < DeviceCost + margin threshold. Flag in email. |
| **Overselling** — flat table refreshes hourly; device could sell between refresh and listing. | Medium | Run cron immediately after flat table refresh. Log active listings and deduct from available quantity on next run. |
| **Listings not delisted** — product sells or moves out of Ecommerce Storefront but listing stays up. | High | Daily reconciliation: compare active listings log against current flat table. Auto-delist via API for any SKU no longer in Ecommerce Storefront. |
| **Amazon SP-API rate limits** — 0.5 req/sec on `getCompetitivePricing`. | Low | 2s delay between calls. 100 SKUs in ~3.5 min. |
| **eBay token expiry** — OAuth refresh tokens expire if not used within 18 months. | Low | Token refresh runs on every daily job execution. |
| **Grade → condition mapping** — internal grades don't match marketplace labels. | Medium | Mapping defined above. Agree internally before launch. |

---

## Implementation Order (Sub-Phase 1D-i)

This is the build sequence for the first deliverable: daily price scan + email digest.

| Step | Task | Dependencies |
|---|---|---|
| 1 | Create `EcommerceProductCatalog` table + populate for top ~50 SKUs | Manual data entry (ASINs from Amazon, UPCs from packaging) |
| 2 | Create `EcommerceListingsLog` table | SQL Server access |
| 3 | Build `ecommerce/db.py` — inventory queries + listings log CRUD | Steps 1–2 |
| 4 | Build `ecommerce/pricing/amazon.py` — SP-API price fetching | Amazon Seller Central credentials |
| 5 | Build `ecommerce/pricing/ebay.py` — Browse API price fetching | eBay developer account |
| 6 | Build `ecommerce/pricing/algorithm.py` — highest floor price selection | None |
| 7 | Build `ecommerce/notifications/email_digest.py` — daily approval email | SMTP credentials or SES |
| 8 | Build `ecommerce/main.py` — orchestrates steps 3–7 | All above |
| 9 | Set up cron job on EC2 | Step 8 |
| 10 | **Test for 1–2 weeks** — validate pricing recommendations manually before enabling auto-listing | None |

Sub-phase 1D-ii (auto-listing) begins only after 1D-i email recommendations have been validated manually.

---

## Confirmed Decisions

| Decision | Answer |
|---|---|
| Marketplace seller status | Approved on Amazon Seller Central and eBay |
| Pricing algorithm | Highest floor price across marketplaces — deterministic, no AI |
| AI model for listing copy | Claude API (already in stack) |
| Approval UX | Email digest (one email, one row per SKU, approve/reject links) |
| SKU volume | ~100 distinct SKUs in Ecommerce Storefront at a time |
| Listing granularity | One listing per product group: Quantity x Model x Grade |
| Daily filter | All unlisted SKUs in Ecommerce Storefront (no active listing in EcommerceListingsLog) |
| Initial marketplaces | Amazon + eBay (official APIs). BestBuy + Reebelo deferred. |

---

## What Was Removed From the Original Plan (and Why)

| Removed | Reason |
|---|---|
| DeepSeek V3 for pricing | Pricing algorithm is deterministic (`max()` over floor prices). No LLM needed. |
| BestBuy.ca scraping (Playwright + stealth + residential proxies) | Fragile, requires Akamai bypass, ongoing proxy cost, maintenance burden. Deferred to 1D-iii — evaluate ROI when core pipeline is proven. |
| Reebelo scraping | Same fragility concerns. Cobalt API only manages own listings. Deferred. |
| Rainforest API | Amazon-only, redundant with SP-API which is free. Was listed as a risk in the original plan but explicitly stated as "not applicable" in the same document. |
| DeepSeek as second AI provider | Adds second billing, second set of credentials, second failure mode. Claude already integrated and running. |
| `playwright-extra` + `playwright-extra-plugin-stealth` | Only needed for BestBuy/Reebelo scraping. Deferred with those marketplaces. |
| `beautifulsoup4` | Only needed for scraping. Deferred. |

---

*For infrastructure context, refer to `README.md` and `AI_Implementation_Plan.md`.*
