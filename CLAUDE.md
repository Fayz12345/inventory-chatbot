# Project Context

Flask-based AI inventory chatbot running on Linux EC2 (Ubuntu 24.04, Public IP: 3.96.54.81, user: ubuntu, key: BrainAddOnMBP.pem), connecting to SQL Server on Windows EC2 (3.96.24.178, database: bridge). Python 3.12.3, venv at `~/chatbot-env`.

## Ecommerce Pipeline (Phase 1D) — Apify Cloud Scraping

Pricing modules use Apify cloud actors to scrape competitive prices across 4 Canadian marketplaces. The approval Blueprint is registered in `app.py`. Pricing runs weekly (Monday 6 AM EST).

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
│   ├── google_shopping.py # Run Google Shopping actor → attribute Best Buy / Reebelo prices
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

**Current mode (1D-ii): Preview only** — Approve generates listing copy via Claude and displays it in a preview modal with copy-to-clipboard buttons. No marketplace API calls yet. Once confidence is built, 1D-iii will enable auto-listing via Amazon SP-API / eBay Inventory API.

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
