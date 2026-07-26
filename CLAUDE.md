# Project Context

Flask-based AI inventory chatbot running on Linux EC2 (Ubuntu 24.04, Public IP: 3.96.54.81, user: ubuntu, key: BrainAddOnMBP.pem), connecting to SQL Server on Windows EC2 (3.96.24.178, database: bridge). Python 3.12.3, venv at `~/chatbot-env`.

## Ecommerce Pipeline (Phase 1D) — Apify Cloud Scraping

Pricing modules gather competitive prices across 4 Canadian marketplaces: Amazon and eBay via Apify cloud actors, and Reebelo + Best Buy CA via their first-party search APIs (keyword-based, no Apify — Best Buy uses bestbuy.ca's refurb search; the old Mirakl P11-by-UPC path was retired because that marketplace carried almost none of our variants). The approval Blueprint is registered in `app.py`. Pricing runs weekly (Monday 6 AM EST).

### Remaining Deployment Tasks

1. **Install Python dependencies on EC2** — `pip install apify-client jinja2 anthropic` in `~/chatbot-env`.
2. **Set up cron job** — `0 11 * * 1 cd ~/inventory-chatbot && ~/chatbot-env/bin/python -m ecommerce.main >> /tmp/ecommerce_pipeline.log 2>&1` (Monday 6 AM EST = 11 UTC)
3. **Add `APIFY_API_TOKEN` to `.env`** on EC2.
4. **Populate `EcommerceProductCatalog`** with ASINs for top SKUs (only 1 entry so far).

### Module Structure

```
ecommerce/
├── config.py              # Reads credentials from main config (Apify token, marketplace keys, etc.)
├── db.py                  # SQL queries, listings CRUD, pricing batch/recommendation CRUD
├── main.py                # Weekly pipeline entry point (python -m ecommerce.main)
├── approval.py            # Flask Blueprint — dashboard at /ecommerce/dashboard, approve/reject via AJAX
├── pricing/
│   ├── apify_client.py    # Apify SDK wrapper — run actors, retrieve datasets
│   ├── amazon.py          # Run Amazon actor → floor prices by ASIN
│   ├── ebay.py            # Run eBay actor → floor prices by keyword
│   ├── bestbuy.py         # Best Buy CA refurb floor via bestbuy.ca search API (keyword, no Apify)
│   ├── reebelo.py         # Reebelo CA floor prices via reebelo.ca catalog API (Apify residential proxy)
│   ├── proxy.py           # Apify residential-proxy routing + datacenter-IP block logging
│   ├── categorize.py      # Classify device (mobile/wearable/tablet/accessory) from Model + scrape-scope filter
│   └── algorithm.py       # Deterministic highest-floor-price across 4 marketplaces
├── listings/
│   ├── amazon.py          # Amazon SP-API listing creation (1D-ii)
│   ├── ebay.py            # eBay Inventory API listing creation (1D-ii)
│   └── copy_generator.py  # Claude API generates listing copy
└── notifications/
    └── email_digest.py    # Jinja2 HTML dashboard templates (batch list + detail page)
```

### Dashboard

The pricing dashboard replaces the email digest. After each weekly pipeline run, recommendations are persisted to `EcommercePricingBatch` / `EcommercePricingRecommendation` tables and viewable at `/ecommerce/dashboard`. Approve/reject actions are handled inline via AJAX.

**Current mode: preview → explicit post.** Approve **generates the listing preview only** (Claude copy, no status change, no marketplace call). The preview modal then offers, per the recommendation's winning marketplace: an **Auto-post** button when that marketplace's API is configured (`POST /ecommerce/post` — atomic claim → SP-API/eBay/Best Buy/Reebelo call → `EcommerceListingsLog` row → Decision `approved`, with delist rollback + 502 on failure; always asks for confirmation), or a **Mark as listed** button when it isn't (`POST /ecommerce/mark-listed` — records a manual `EcommerceListingsLog` row with `PlatformListingID='manual'`). Copy-to-clipboard + Reject stay. `approval.listing_availability(marketplace)` is the single source for whether Auto-post is offered (wraps each module's `_have_creds()`; eBay also needs merchant-location + 3 policy IDs; Best Buy needs a catalog UPC match).

**View a resolved listing:** resolved rows show a **View** button that re-opens the saved copy read-only (copy buttons only) via `GET /ecommerce/listing/<rec_id>`. The copy is persisted on `EcommercePricingRecommendation.ListingCopyJSON` at post/mark-listed time — **one-time setup:** `ALTER TABLE EcommercePricingRecommendation ADD ListingCopyJSON NVARCHAR(MAX) NULL` on the bridge SQL Server (degrades gracefully until then: save logs a warning, View returns 404).

**Weekly run report (email):** after every pipeline run, `ecommerce/notifications/run_report.py` (`RunReport`) emails a report — per-source scrape outcomes for **all four** marketplaces (Amazon/eBay = Apify actors, Best Buy/Reebelo = first-party "browser" APIs) with a **FAILURES section** flagging antibot/0-coverage/exceptions — via M365 Graph (`ecommerce/notifications/mailer.py`) to `ECOMMERCE_EMAIL_TO`. Sent in `run_pipeline`'s `try/finally`, so even a pipeline crash still reports. Config in `.env`: `ECOMMERCE_EMAIL_TO` + `M365_TENANT_ID/CLIENT_ID/CLIENT_SECRET/SENDER` (same M365 app the invite emails use).

### Dashboard — Scrape scope control

The batch-list page (`/ecommerce/dashboard`) has a **Scrape scope** card that controls what the weekly run scrapes:
- **Category toggles** — Phones / Wearables / Tablets / Accessories. Inventory has no category column, so each device is classified from its `Model` string (`ecommerce/pricing/categorize.py`, reusing `listings/ebay._device_type` + `pricing/filters.is_accessory`; accessory is checked first so "watch band" ≠ wearable; unknown → phone).
- **All vs Top-N by count** — "Top N" = the N highest-volume **models** (colours/grades aggregated → N distinct search keywords).

Choices persist to a single-row **SQL Server** table `EcommerceScrapeSettings` (Id=1), read/written via `ecommerce/db.py` (`get_scrape_settings` / `save_scrape_settings`); pure defaults/validation live in `ecommerce_settings.py`. **One-time setup:** run the `CREATE TABLE` (`ecommerce/queries.py::create_scrape_settings_table_query`, also in `Queries.txt`) on the bridge SQL Server — until then reads fall back to defaults (phones+wearables+tablets, all). `run_pipeline` reads the settings right after `fetch_all_pending_products()` and logs the scope (`Scrape scope: N/M groups kept ...`). **No on-demand trigger** — settings apply on the next weekly cron; **accessories default OFF**. Routes: `POST /ecommerce/scrape-settings` (save), `GET /ecommerce/scrape-preview` (impact counts). A CLI `--limit` still overrides the saved top-N for dev.

### Key DB Details

- Inventory location filter: `Product_Place = 'E-Commerce Store Front'` (note the exact spelling with hyphens and spaces)
- Storage is embedded in the Model attribute (e.g. "iPhone 14 Pro Max 128 GB" — note space before GB)

## Analytics Module — Telus Weekly Reports

Automates the Telus Weekly repair assessment report that was previously done in Excel. Users enter a ProjectTag, the system runs the stored procedure, applies pricing formulas server-side, and renders the Repair & Resell report in the browser.

### Home Page

After login, users land on `/home` with 3 navigation cards: Inventory Chatbot, Ecommerce, Analytics.

### Module Structure

```
analytics/
├── config.py              # Re-exports root DB config
├── db.py                  # Stored proc call + TelusWeeklyPricingMaster CRUD
├── pricing.py             # Pure-Python pricing engine (replaces Excel VLOOKUP formulas)
├── routes.py              # Flask Blueprint at /analytics
├── templates.py           # Jinja2 HTML templates (analytics index, TW form, report, price review)
└── import_pricing.py      # One-time script to seed pricing master from Excel
```

### Routes

- `/analytics/` — Analytics index (list of available reports)
- `/analytics/telus-weekly` — ProjectTag input form
- `/analytics/telus-weekly/report` — POST: run stored proc + pricing engine → render report
- `/analytics/telus-weekly/export` — POST: same pipeline → download Excel (.xlsx)
- `/analytics/price-review` — View/edit the pricing master table (replaces Excel "DO NOT EDIT" sheet)
- `/analytics/price-review/save` — AJAX: bulk update prices
- `/analytics/price-review/add` — AJAX: insert new model

### Key DB Details

- Stored procedure: `GetReport_RepairAssessment_ByProjectTag` (already on SQL Server)
- Pricing master table: `TelusWeeklyPricingMaster` (Model, GradeA/B/C_Price, Defective_Price, FRP_Price, DeviceType)
- Telus Weekly devices always have `Version = '000'`, `ProjectName = 'Telus Weekly'`
- Model lookup key: `ModelVerb` from stored proc matches `Model` in pricing master (both from Brain's Option.OptionText)

### Deployment Tasks (completed 2026-05-03)

1. ~~**Create `TelusWeeklyPricingMaster` table** on SQL Server~~ — Done (829 models loaded)
2. ~~**Run import script** — `python -m analytics.import_pricing`~~ — Done
3. ~~**Install openpyxl** — `pip install openpyxl` in `~/chatbot-env`~~ — Done
4. ~~**Deploy analytics module + updated app.py + home.html to EC2**~~ — Done via SCP
