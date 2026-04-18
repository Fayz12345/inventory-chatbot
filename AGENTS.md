# Project Context

Flask-based AI inventory chatbot running on Linux EC2 (Ubuntu 24.04), connecting to SQL Server on Windows EC2 (3.96.24.178, database: bridge). Python 3.12.3, venv at `~/chatbot-env`.

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
│   └── copy_generator.py  # Codex API generates listing copy
└── notifications/
    └── email_digest.py    # Jinja2 HTML dashboard templates (batch list + detail page)
```

### Dashboard

The pricing dashboard replaces the email digest. After each weekly pipeline run, recommendations are persisted to `EcommercePricingBatch` / `EcommercePricingRecommendation` tables and viewable at `/ecommerce/dashboard`. Approve/reject actions are handled inline via AJAX.

**Current mode (1D-ii): Preview only** — Approve generates listing copy via Codex and displays it in a preview modal with copy-to-clipboard buttons. No marketplace API calls yet. Once confidence is built, 1D-iii will enable auto-listing via Amazon SP-API / eBay Inventory API.

### Key DB Details

- Inventory location filter: `Product_Place = 'E-Commerce Store Front'` (note the exact spelling with hyphens and spaces)
- Storage is embedded in the Model attribute (e.g. "iPhone 14 Pro Max 128 GB" — note space before GB)
