# Project Context

Flask-based AI inventory chatbot running on Linux EC2 (Ubuntu 24.04), connecting to SQL Server on Windows EC2 (3.96.24.178, database: bridge). Python 3.12.3, venv at `~/chatbot-env`.

## Ecommerce Pipeline (Phase 1D) — Refactoring for Octoparse

Pricing modules are being rewritten to use Octoparse cloud scraping instead of direct marketplace APIs. The approval Blueprint is registered in `app.py`. Pricing runs weekly (Monday 6 AM EST) across 4 Canadian marketplaces.

### Remaining Deployment Tasks

1. **Create SQL Server tables** — Run DDL for `EcommercePricingBatch` and `EcommercePricingRecommendation` on the Windows EC2 SQL Server (see below for DDL).
2. **Install Python dependencies on EC2** — `pip install requests jinja2 anthropic python-amazon-sp-api` in `~/chatbot-env`.
3. **Set up cron job** — `0 11 * * 1 cd ~/inventory-chatbot && ~/chatbot-env/bin/python -m ecommerce.main >> /tmp/ecommerce_pipeline.log 2>&1` (Monday 6 AM EST = 11 UTC)
4. **Move secrets to `.env`** — DB password, API keys are currently hardcoded in `config.py`.

### Module Structure

```
ecommerce/
├── config.py              # Reads credentials from main config (Octoparse token, marketplace keys, etc.)
├── db.py                  # SQL queries, listings CRUD, pricing batch/recommendation CRUD, reconciliation
├── main.py                # Weekly pipeline entry point (python -m ecommerce.main)
├── approval.py            # Flask Blueprint — dashboard at /ecommerce/dashboard, approve/reject via AJAX
├── pricing/
│   ├── octoparse_client.py # Octoparse REST API — create tasks, poll, export JSON (with single retry)
│   ├── amazon.py          # Parse Amazon scrape results → floor prices
│   ├── ebay.py            # Parse eBay scrape results → floor prices
│   ├── google_shopping.py # Parse Google Shopping → attribute Best Buy / Reebelo prices
│   └── algorithm.py       # Deterministic highest-floor-price across 4 marketplaces
├── listings/
│   ├── amazon.py          # Amazon SP-API listing creation (1D-ii)
│   ├── ebay.py            # eBay Inventory API listing creation (1D-ii)
│   └── copy_generator.py  # Claude API generates listing copy
└── notifications/
    └── email_digest.py    # Jinja2 HTML dashboard templates (batch list + detail page)
```

### Dashboard

The pricing dashboard replaces the email digest. After each weekly pipeline run, recommendations are persisted to `EcommercePricingBatch` / `EcommercePricingRecommendation` tables and viewable at `/ecommerce/dashboard`. Approve/reject actions are handled inline via AJAX and trigger listing creation on the marketplace API.
