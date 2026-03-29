# Project Context

Flask-based AI inventory chatbot running on Linux EC2 (Ubuntu 24.04), connecting to SQL Server on Windows EC2 (3.96.24.178, database: bridge). Python 3.12.3, venv at `~/chatbot-env`.

## Ecommerce Pipeline (Phase 1D) — Code Complete

All 15 modules in `ecommerce/` are built and integrated. The approval Blueprint is registered in `app.py`. Credential placeholders are in `config.py` (empty strings — modules skip API calls gracefully when unconfigured).

### Remaining Deployment Tasks

1. **Create SQL Server tables** — Run DDL for `EcommerceListingsLog` and `EcommerceProductCatalog` on the Windows EC2 SQL Server. Schema is defined in `Ecommerce_AI_Plan.md` under "Database Tables".
2. **Add `Product_Placement_Created` column** — Add datetime column to `ReportingInventoryFlat` and update the refresh stored procedure to populate it.
3. **Install Python dependencies on EC2** — `pip install python-amazon-sp-api jinja2` in `~/chatbot-env`.
4. **Fill in marketplace credentials in `config.py`** — Amazon SP-API keys (Seller Central), eBay OAuth tokens (developer.ebay.com), SMTP credentials for digest emails.
5. **Set `APP_BASE_URL`** in `config.py` to the EC2 public IP (e.g. `http://3.96.54.81:5000`).
6. **Set up cron job** — `0 7 * * * cd ~/inventory-chatbot && ~/chatbot-env/bin/python -m ecommerce.main`

### Module Structure

```
ecommerce/
├── config.py              # Reads credentials from main config
├── db.py                  # SQL queries, listings CRUD, reconciliation
├── main.py                # Daily pipeline entry point (python -m ecommerce.main)
├── approval.py            # Flask Blueprint at /ecommerce/approve and /ecommerce/reject
├── pricing/
│   ├── amazon.py          # Amazon SP-API competitive pricing
│   ├── ebay.py            # eBay Browse API keyword search
│   └── algorithm.py       # Deterministic highest-floor-price selection
├── listings/
│   ├── amazon.py          # Amazon SP-API listing creation
│   ├── ebay.py            # eBay Inventory API listing creation
│   └── copy_generator.py  # Claude API generates listing copy
└── notifications/
    └── email_digest.py    # Jinja2 HTML email with approve/reject links
```
