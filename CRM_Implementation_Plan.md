# Bridge CRM - Implementation Plan

## Context

Bridge Wireless is a **B2B wholesale** refurbished electronics business — selling bulk inventory to resellers, retailers, and carriers. Deals are large and account-based. The business needs a CRM to manage its wholesale sales pipeline (Leads, Accounts, Opportunities). Currently, leads and deals are tracked manually.

The business has an ERP system (`gadgetkg_bwqa_main` on MySQL 5.7) that manages inventory at the serial-number level. The ERP database lives on a **separate EC2 instance** (remote). The CRM will be a **separate project** running alongside the existing inventory chatbot on the **same EC2 instance**, with its own PostgreSQL database on that same machine. The CRM syncs product data from the remote ERP MySQL over the network.

> **Decision: Custom CRM replaces HubSpot.** The earlier project roadmap (`AI_Implementation_Plan.md` Phase 2A, `User_Stories.md` Epic 2A/2B) planned HubSpot as the CRM. That decision has been reversed. This custom CRM supersedes all HubSpot references in those documents. The HubSpot epics (2A, 2B, 2C) should be updated to reference this CRM instead.

### Data Authority Model

- **CRM is the source of truth** for sales data: Leads, Accounts, Contacts, Opportunities, communication history
- **ERP is the source of truth** for operational data: inventory, invoicing, workshop, logistics
- `crm_accounts.erp_client_id` is a **UNIQUE nullable** foreign reference to `master_clients.id` in the ERP — set manually when linking a CRM account to an existing ERP client. Uniqueness enforced at the database level to prevent duplicate mappings
- New accounts created in the CRM do **not** automatically create ERP client records. ERP client creation happens through the ERP's own workflow when a deal progresses to fulfillment
- The CRM never writes to the ERP database — it reads only (via the product sync)

---

## Architecture

| Component | Choice | Reasoning |
|---|---|---|
| Backend | **Flask** | Already proven in production, user knows it well |
| CRM Database | **PostgreSQL** | JSONB for activity metadata, Power BI native connector, better indexing |
| ERP Database | **MySQL 5.7** (remote EC2, read-only) | On a separate EC2 instance; CRM connects over the network to sync product data |
| SQL Layer | **SQLAlchemy Core** | Database portability without ORM complexity — you still write SQL-shaped queries |
| Migrations | **Alembic** | Standard migration tooling for SQLAlchemy |
| Frontend | **Bootstrap 5 + htmx** | No build step, no npm. CDN links only. Interactive without a SPA |
| Charts | **Chart.js** (CDN) | Simple reporting charts |
| Drag-and-drop | **SortableJS** (CDN) | Pipeline kanban board |
| Email | **smtplib via Outlook 365 SMTP** | Org already uses Outlook 365 — use `smtp.office365.com:587` with existing credentials |
| WhatsApp | **WhatsApp Business Cloud API** (direct, no Twilio) | No markup, direct Meta integration |
| Mobile | **PWA** | Zero additional codebase — installable via "Add to Home Screen" |
| ERP Sync | **cron + pymysql** | Same pattern as existing ecommerce pipeline |
| Reporting | **Built-in + Power BI** via PostgreSQL read-only user | Covers simple and advanced needs |
| Deployment | **gunicorn + Nginx** | Same as existing chatbot app |

### Deployment Layout

**Recommended: Subdomain approach** — Avoids URL prefix issues entirely. Flask routes stay as `/accounts`, `/dashboard`, etc. with no rewriting.

```
CRM EC2 (Ubuntu 24.04) — same machine as inventory-chatbot
  Nginx (port 80/443, Let's Encrypt SSL)
  |-- chatbot.yourdomain.com  -> gunicorn :5000 (inventory-chatbot, existing)
  |-- crm.yourdomain.com      -> gunicorn :5001 (bridge-crm, all routes)
  |     includes /lead-form   (public, no auth)
  |     includes /api/leads   (public, CORS)
  |
  PostgreSQL :5432 (bridge_crm database — local, bound to 127.0.0.1)
  |
  Cron:
    - Every Monday 6 AM:   ecommerce pipeline (existing)
    - Every 15 min:         ERP product sync — incremental (connects to remote ERP EC2)
    - Every Sunday 2 AM:    ERP product sync — full reconciliation

ERP EC2 (separate instance)
  MySQL 5.7 :3306 (gadgetkg_bwqa_main)
  Security group: allow inbound 3306 from CRM EC2's IP
```

**Subdomain setup:** Add a DNS A record for `crm.yourdomain.com` pointing to the EC2 public IP. Nginx `server` block listens on `server_name crm.yourdomain.com` and proxies to port 5001. Let's Encrypt cert covers both subdomains via `certbot --nginx -d chatbot.yourdomain.com -d crm.yourdomain.com`.

**Fallback (path prefix):** If subdomains are not available, mount at `/crm/` with WSGI prefix awareness:
- Nginx: `location /crm/ { proxy_pass http://127.0.0.1:5001/; proxy_set_header X-Forwarded-Prefix /crm; ... }`
- Flask: `app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)` — this makes `url_for()` generate correct URLs with the `/crm` prefix so redirects and static asset links work properly

---

## Project Structure

```
bridge-crm/
  app.py                          # Flask app factory, register blueprints
  config.py                       # os.environ[] via python-dotenv (same pattern as chatbot)
  config.example.py               # Documented template
  .env / .gitignore / requirements.txt / CLAUDE.md
  db/
    engine.py                     # SQLAlchemy engine + connection helper
    schema.py                     # SQLAlchemy Core table definitions
    migrate.py                    # Alembic setup
  crm/
    auth/       routes.py, queries.py       # /auth/* — login, logout, user management
    leads/      routes.py, queries.py       # /leads/* — CRUD, status changes
    opportunities/ routes.py, queries.py    # /opportunities/* — CRUD, pipeline, product picker
    accounts/   routes.py, queries.py       # /accounts/* — CRUD, contacts
    products/   routes.py, queries.py       # /products/* — read-only browse of synced ERP items
    dashboard/  routes.py, queries.py       # /dashboard/* — home, reports
  integrations/
    erp_sync.py                   # cron: sync ERP products -> crm_products
    email_sender.py               # smtplib wrapper: compose + send + log
    whatsapp.py                   # WhatsApp Cloud API: send + receive webhook
  api/
    lead_capture.py               # /api/leads — public POST endpoint for iFrame form
  templates/
    base.html                     # Bootstrap 5 + htmx CDN, navbar, flash messages
    auth/ leads/ opportunities/ accounts/ products/ dashboard/ reports/
    components/
      activity_timeline.html      # Reusable: activity feed for any entity
      email_compose.html          # Reusable: email modal
      whatsapp_compose.html       # Reusable: WhatsApp modal
      quote_line_builder.html      # Reusable: add model/grade/qty lines to opportunity with stock visibility
  static/
    css/custom.css
    js/app.js                     # Shared utilities (toast, modal helpers)
    manifest.json + service-worker.js   # PWA (Phase 8)
  lead_form/
    index.html                    # Standalone HTML for iFrame embedding
```

---

## Database Schema

### Core Tables

**`crm_users`** — Internal CRM users
```
id SERIAL PK, email UNIQUE, password_hash, full_name, role ('admin'|'manager'|'user'),
is_active BOOLEAN, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
```

**`crm_accounts`** — Companies / customers
```
id SERIAL PK, company_name, contact_name, email, phone, phone_prefix, website,
address_line_1, address_line_2, city, state_province, postal_code, country, industry,
erp_client_id VARCHAR(11) nullable (link to master_clients.id in ERP),
notes, owner_id FK->crm_users, created_by FK->crm_users, created_at, updated_at
```

**`crm_contacts`** — People at accounts
```
id SERIAL PK, account_id FK->crm_accounts, first_name, last_name, email, phone,
phone_prefix, job_title, is_primary BOOLEAN, whatsapp_number, created_at, updated_at
```

**`crm_leads`** — Inbound leads
```
id SERIAL PK, first_name, last_name, email, phone, phone_prefix, company_name,
source ('web_form'|'manual'|'import'|'referral'|'whatsapp'),
status ('new'|'contacted'|'qualified'|'unqualified'|'converted'),
notes, interest TEXT, owner_id FK->crm_users,
converted_account_id FK->crm_accounts, converted_opportunity_id FK->crm_opportunities,
converted_at TIMESTAMPTZ, created_at, updated_at
```

**`crm_opportunities`** — Deals
```
id SERIAL PK, title, account_id FK->crm_accounts NOT NULL, contact_id FK->crm_contacts,
stage ('prospecting'|'qualification'|'proposal'|'negotiation'|'closed_won'|'closed_lost'),
amount DECIMAL(14,2), currency DEFAULT 'CAD', probability INT (0-100),
expected_close_date DATE, close_date DATE, close_reason TEXT,
owner_id FK->crm_users, lead_id FK->crm_leads, notes,
created_by FK->crm_users, created_at, updated_at
```

**`crm_pipeline_stages`** — Configurable stages
```
id SERIAL PK, stage_key VARCHAR(30) UNIQUE, display_name, display_order INT,
default_probability INT, is_active BOOLEAN
```

### Product Sync Tables

**`crm_products`** — Mirror of ERP inventory (denormalized, human-readable)
```
id SERIAL PK, erp_inventory_id INT UNIQUE (wh_inv_master.id),
serial_number VARCHAR(25) UNIQUE, imei_1, model_name, brand_name, category_name,
color, ram, rom, outward_grade, inward_grade,
outward_sales_price DECIMAL(11,2), item_status, bin_location,
inward_item_cost DECIMAL(11,2), lot_num,
erp_last_modified TIMESTAMPTZ, synced_at TIMESTAMPTZ
```

**`crm_product_sync_log`** — Sync run history
```
id SERIAL PK, sync_started_at, sync_completed_at, records_processed INT,
records_inserted INT, records_updated INT,
status ('running'|'completed'|'failed'), error_message TEXT
```

**`crm_opportunity_lines`** — Quote lines on deals (model-level, not serial-level)
```
id SERIAL PK, opportunity_id FK->crm_opportunities ON DELETE CASCADE,
brand VARCHAR(50) NOT NULL, model VARCHAR(50) NOT NULL, grade VARCHAR(4),
category VARCHAR(50), storage VARCHAR(10),
quantity INT NOT NULL, unit_price DECIMAL(11,2) NOT NULL,
line_total DECIMAL(14,2) GENERATED ALWAYS AS (quantity * unit_price) STORED,
notes TEXT, created_at TIMESTAMPTZ, updated_at TIMESTAMPTZ
```
Sales reps quote at the model level (e.g., "50x iPhone 14 Pro Grade A at $450 each"), not by serial number.
Individual serial assignment happens downstream in the ERP during fulfillment.
The `crm_products` table provides inventory visibility (available stock counts by model/grade) to inform quoting — it is not linked to quote lines directly.

### Communication Tables

**`crm_emails`** — Email history
```
id SERIAL PK, direction ('outbound'|'inbound'), related_type ('lead'|'opportunity'|'account'),
related_id INT, from_address, to_address, cc_address, subject, body_html, body_text,
status ('draft'|'sent'|'failed'), sent_at, sent_by FK->crm_users, error_message, created_at
```

**`crm_whatsapp_messages`** — WhatsApp history
```
id SERIAL PK, direction, related_type, related_id, wa_message_id,
from_number, to_number, message_type ('text'|'template'|'media'),
body TEXT, template_name, status ('sent'|'delivered'|'read'|'failed'),
sent_at, sent_by FK->crm_users, created_at
```

### Activity Trail

**`crm_activities`** — Unified timeline for all entities
```
id SERIAL PK, related_type, related_id,
activity_type ('note'|'call'|'meeting'|'email_sent'|'whatsapp_sent'|'stage_changed'|'status_changed'|'product_added'|'created'|'converted'),
description TEXT, metadata JSONB, created_by FK->crm_users, created_at
```

### ERP Sync Query

The ERP uses VARCHAR for all FK columns (e.g., `model_id` is `varchar(11)`, not `int`). MySQL auto-casts these on JOIN. The sync query resolves all IDs to human-readable names in a single pass:

```sql
SELECT
  inv.id, inv.serial_number, inv.imei_1,
  m.model_name, b.brand_name, c.category_name,
  color_attr.attribute_value AS color,
  ram_attr.attribute_value AS ram,
  rom_attr.attribute_value AS rom,
  inv.outward_grade, inv.inward_grade,
  inv.outward_sales_price, inv.item_status,
  inv.bin_location, inv.inward_item_cost, inv.lot_num,
  COALESCE(inv.mod_dateTime, inv.cr_dateTime) AS last_modified
FROM wh_inv_master inv
LEFT JOIN web_model_master m ON inv.model_id = m.id
LEFT JOIN web_brand_master b ON inv.brand_id = b.id
LEFT JOIN web_category_master c ON inv.prod_cat_id = c.id
LEFT JOIN web_attribute_master color_attr ON inv.color_id = color_attr.id
LEFT JOIN web_attribute_master ram_attr ON inv.ram_id = ram_attr.id
LEFT JOIN web_attribute_master rom_attr ON inv.rom_id = rom_attr.id
WHERE COALESCE(inv.mod_dateTime, inv.cr_dateTime) >= %s
```

Target table uses `INSERT ... ON CONFLICT (erp_inventory_id) DO UPDATE SET ...` for idempotent upserts.

**Sync safety strategy:**
- Use `>=` (not `>`) on the high-water mark to avoid missing rows with identical timestamps. The upsert is idempotent, so re-processing the same row is harmless
- Store the high-water mark as `MAX(last_modified)` from the previous successful sync in `crm_product_sync_log`
- **Weekly full reconciliation:** Every Sunday, run a full sync (no WHERE clause) to catch lookup-table corrections (e.g., brand name fixed in `web_brand_master`) that don't update `wh_inv_master.mod_dateTime`. The cron runs the full sync via a `--full` flag: `python -m integrations.erp_sync --full`
- Incremental syncs run every 15 minutes; the full reconciliation runs once weekly. For a catalog of a few thousand items, a full sync completes in seconds

---

## Phased Build Plan

### Phase 1: Foundation (Weeks 1-2)
**Deliverable: Running CRM with auth, PostgreSQL, and Accounts CRUD**

1. **Scaffold project** — `bridge-crm/` directory, git init, `.gitignore`, `requirements.txt` (`flask`, `flask-wtf`, `gunicorn`, `python-dotenv`, `psycopg2-binary`, `pymysql`, `sqlalchemy`, `alembic`, `werkzeug`), virtualenv. Copy `CRM_Implementation_Plan.md` into the project root for reference
2. **Config** — `config.py` using `os.environ[]` + `python-dotenv` (same pattern as `inventory-chatbot/config.py`). Keys: `CRM_DB_HOST` (localhost), `CRM_DB_PORT`, `CRM_DB_NAME`, `CRM_DB_USER`, `CRM_DB_PASSWORD`, `SECRET_KEY` (32+ bytes), `ERP_DB_HOST` (remote ERP EC2 IP), `ERP_DB_PORT`, `ERP_DB_NAME`, `ERP_DB_USER`, `ERP_DB_PASSWORD`, `SMTP_*`, `CORS_ALLOWED_ORIGINS`
3. **PostgreSQL setup** — Install PostgreSQL (`brew install postgresql@16` locally, `apt install postgresql` on EC2). Create `bridge_crm` database. Bind to localhost only. Create `db/engine.py` (SQLAlchemy engine from config), `db/schema.py` (table definitions with UNIQUE constraint on `crm_accounts.erp_client_id`), `db/migrate.py` (create_all for now, Alembic later). Set up daily `pg_dump` backup cron
4. **ERP network access** — On the remote ERP EC2, open port 3306 in the security group for the CRM EC2's IP. Create a read-only MySQL user on the ERP for CRM sync: `CREATE USER 'crm_reader'@'<CRM_EC2_IP>' IDENTIFIED BY '...'; GRANT SELECT ON gadgetkg_bwqa_main.* TO 'crm_reader'@'<CRM_EC2_IP>';`. Test connectivity from CRM EC2: `mysql -h <ERP_EC2_IP> -u crm_reader -p gadgetkg_bwqa_main -e "SELECT COUNT(*) FROM wh_inv_master"`
5. **Auth + security** — `crm/auth/routes.py`: login page, logout, `login_required` decorator using `session['user_id']`. Seed admin user via script. Same werkzeug password hashing pattern as chatbot. Add `CSRFProtect(app)` via Flask-WTF. Configure secure session cookies (HttpOnly, Secure, SameSite=Lax). Add login rate limiting (5 failures = 15 min lockout). Add ProxyFix middleware. Add `/health` endpoint
6. **Base template** — `templates/base.html`: Bootstrap 5 + htmx via CDN. Navbar (Dashboard, Leads, Opportunities, Accounts, Products). Flash messages. CSRF meta tag for htmx: `<body hx-headers='{"X-CSRFToken": "{{ csrf_token() }}"}'>`
7. **Accounts CRUD** — `crm/accounts/queries.py` (SQLAlchemy Core: `select()`, `insert()`, `update()`), `crm/accounts/routes.py` (Blueprint at `/accounts`). Templates: list (searchable table), detail (card layout with tabs), create/edit form. `erp_client_id` field with UNIQUE validation
8. **Deploy** — gunicorn on port 5001, Nginx reverse proxy via subdomain (`crm.yourdomain.com`), Let's Encrypt SSL, security headers (see Security section), HTTP -> HTTPS redirect, access logging

### Phase 2: Leads + Lead Capture Form (Weeks 3-4)
**Deliverable: Lead management + embeddable web form for any website**

1. **Leads CRUD** — Blueprint at `/leads`. List with status filter tabs (New | Contacted | Qualified | All). Detail page with activity timeline. Manual create form
2. **Lead capture API** — `api/lead_capture.py`: `POST /api/leads` (public, no auth). JSON input validation, rate limiting (5/IP/hour), CORS headers for allowed domains. Returns `{ok, message}` or `{ok: false, errors}`
3. **iFrame form** — `lead_form/index.html`: standalone HTML page, not a Jinja2 template. Clean form (First Name, Last Name, Email, Phone, Company, Interest). Vanilla JS fetch to `/api/leads`. Served at `GET /lead-form` (no auth). Embed: `<iframe src="https://your-domain/lead-form" width="100%" height="600">`
4. **Lead conversion** — "Convert to Account + Opportunity" button on lead detail. Creates Account (or matches existing), creates Contact, creates Opportunity in `prospecting` stage, updates lead status to `converted`

### Phase 3: Opportunities + Pipeline Board (Weeks 5-6)
**Deliverable: Deal management with visual kanban pipeline**

1. **Opportunities CRUD** — Blueprint at `/opportunities`. List with filters (stage, owner, date range). Detail page with tabs: Info, Products, Activity, Emails, WhatsApp. Create form requires selecting an Account
2. **Pipeline kanban** — `templates/opportunities/pipeline.html`. One column per stage. Cards show company, title, amount, expected close date. Drag-and-drop via SortableJS. On drop: htmx POST updates stage + probability. Stage totals at column bottom
3. **Pipeline stages config** — Seed `crm_pipeline_stages` with defaults (Prospecting 10%, Qualification 30%, Proposal 50%, Negotiation 70%, Closed Won 100%, Closed Lost 0%). Admin page to manage
4. **Activity timeline component** — `templates/components/activity_timeline.html`: reusable partial for any entity. "Add Note" form at top (htmx POST). Shows activities chronologically with type icons

### Phase 4: ERP Product Sync (Weeks 7-8)
**Deliverable: Products synced from ERP, browsable, attachable to deals**

1. **ERP connection** — `pymysql` already in requirements from Phase 1. `ERP_DB_*` config vars point to the remote ERP EC2 IP (port 3306). MySQL connection in `integrations/erp_sync.py` using the `crm_reader` read-only user created in Phase 1. Network connectivity already verified in Phase 1 step 4
2. **Sync logic** — Connect to `gadgetkg_bwqa_main`, run the JOIN query above, upsert into `crm_products`. First run: full sync (no WHERE clause). Subsequent: incremental via `mod_dateTime >= last_sync` (use `>=` to avoid missing same-timestamp rows; upsert is idempotent). Log to `crm_product_sync_log`. Support `--full` flag for weekly reconciliation
3. **Cron** — Two entries: `*/15 * * * * cd ~/bridge-crm && ~/crm-env/bin/python -m integrations.erp_sync >> /var/log/bridge-crm/erp_sync.log 2>&1` (incremental) and `0 2 * * 0 cd ~/bridge-crm && ~/crm-env/bin/python -m integrations.erp_sync --full >> /var/log/bridge-crm/erp_sync.log 2>&1` (Sunday 2 AM full reconciliation)
4. **Product browsing** — Blueprint at `/products` (read-only). Searchable/filterable list (brand, model, status, grade). Detail view
5. **Quote line builder on Opportunities** — `templates/components/quote_line_builder.html`. On Opportunity detail, "Quote Lines" tab shows line items (brand, model, grade, qty, unit price, line total). "Add Line" button opens a form with dropdowns populated from `crm_products` (distinct brands, models, grades with available stock counts). Sales rep selects model-level attributes and enters quantity + unit price. Auto-calculate opportunity amount as sum of all line totals. Stock count badge shows available inventory for the selected model/grade to inform quoting

### Phase 5: Email Integration (Weeks 9-10)
**Deliverable: Send emails from any entity, tracked in activity timeline**

1. **Email infrastructure** — `integrations/email_sender.py`: `send_email(to, subject, body_html, body_text, cc)` using smtplib + `email.mime`. Use Outlook 365 SMTP: `SMTP_HOST=smtp.office365.com`, `SMTP_PORT=587`, `SMTP_USER=your-outlook-email`, `SMTP_PASSWORD=app-password` (generate an App Password in Microsoft 365 admin if MFA is enabled). STARTTLS required. `SMTP_FROM_ADDRESS` must match the authenticated Outlook user
2. **Compose UI** — `templates/components/email_compose.html`: Bootstrap modal with To (pre-filled), CC, Subject, Body (textarea or TinyMCE via CDN). Include on Lead, Opportunity, Account detail pages
3. **Send route** — `POST /api/email/send`: validate, send, insert into `crm_emails`, log activity
4. **Email history** — "Emails" tab on each entity detail page. Query `crm_emails WHERE related_type = ? AND related_id = ?`. Timeline display with subject, date, status badge. Click to expand body
5. **Email templates** (optional) — `crm_email_templates` table. Template variables: `{{contact_name}}`, `{{company_name}}`, etc. Dropdown in compose modal

### Phase 6: WhatsApp Integration (Weeks 11-13)
**Deliverable: Send/receive WhatsApp messages from CRM entities**

1. **WhatsApp Business setup** — Register at business.facebook.com. Create Meta Developer app. Add WhatsApp product. Register phone number. Create message templates. Get permanent access token
2. **API client** — `integrations/whatsapp.py`: `send_text_message(to_number, message)`, `send_template_message(to_number, template_name, params)`. POST to `https://graph.facebook.com/v19.0/{phone_number_id}/messages`. Log to `crm_whatsapp_messages` + activity
3. **Compose UI** — `templates/components/whatsapp_compose.html`: modal with To number (pre-filled from contact), message type toggle (Template vs Text), body textarea. Include on entity detail pages
4. **Incoming webhook** — `GET /api/whatsapp/webhook` (verification), `POST /api/whatsapp/webhook` (receive messages). Match incoming number to contact. Insert as inbound message. Create activity
5. **Conversation view** — "WhatsApp" tab on entity detail pages. Chat-bubble layout (outbound right, inbound left). htmx polling every 30s. Quick reply compose at bottom

### Phase 7: Reporting + Power BI (Weeks 14-15)
**Deliverable: Built-in dashboard + reports + Power BI connectivity**

1. **Dashboard home** — `GET /dashboard`: pipeline summary (deals per stage, total value), lead funnel (count by status), recent activity feed, my open deals, upcoming closes (next 30 days)
2. **Pipeline report** — Stage breakdown table + bar chart (Chart.js). Filterable by date range, owner. CSV export button
3. **Lead source report** — Source breakdown table + pie chart. Conversion rates per source
4. **Sales forecast** — `SUM(amount * probability / 100) GROUP BY month`. Line chart
5. **Power BI setup** — Create read-only PostgreSQL user (`powerbi_reader`). Grant SELECT on all tables. Create views (`v_pipeline_report`, `v_lead_report`). **Do NOT expose port 5432 publicly.** Instead, connect Power BI via SSH tunnel: `ssh -L 5432:localhost:5432 ubuntu@<EC2_IP>` — Power BI Desktop connects to `localhost:5432` through the tunnel. Document connection instructions for the team

### Phase 8: PWA + Mobile Polish (Weeks 16-17)
**Deliverable: Installable mobile app via "Add to Home Screen"**

1. **PWA manifest** — `static/manifest.json` with app name, icons, start_url, display: standalone. Link in `base.html`
2. **Service worker** — `static/service-worker.js`: cache static assets (Bootstrap, custom CSS/JS). Network-first for HTML pages
3. **Responsive audit** — Pipeline board: vertical list on mobile. Tables: Bootstrap responsive wrapper. Forms: stack vertically on small screens. Navbar: hamburger collapse
4. **Touch fallbacks** — "Move to Stage" dropdown on pipeline cards as fallback for drag-and-drop

---

## Security

Security is baked into each phase, not bolted on at the end. This CRM is public-facing (lead capture form) and handles customer PII, so it needs hardening from Phase 1.

### Session and Authentication (Phase 1)
- **Session cookies:** Set `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SECURE=True` (HTTPS only), `SESSION_COOKIE_SAMESITE='Lax'` in Flask config
- **Secret key:** Minimum 32 bytes, generated via `python -c "import secrets; print(secrets.token_hex(32))"` — never reuse the chatbot's key
- **Login rate limiting:** Track failed login attempts per IP in-memory (or a small `crm_login_attempts` table). Lock out after 5 failures for 15 minutes. Log all failures
- **Password policy:** Minimum 12 characters enforced in the seed script and any future user management UI

### CSRF Protection (Phase 1)
- Use `Flask-WTF` for CSRF tokens on all state-changing forms. Add `CSRFProtect(app)` in the app factory
- For htmx AJAX requests: include the CSRF token in a `<meta>` tag in `base.html` and configure htmx to send it as a header: `<body hx-headers='{"X-CSRFToken": "{{ csrf_token() }}"}'>`
- The public lead capture API (`POST /api/leads`) is exempt from CSRF (it's a cross-origin API) — protect it with rate limiting and CORS instead

### Public Endpoint Hardening (Phase 2)
- **Lead capture rate limiting:** 5 submissions per IP per hour, enforced server-side. Use an in-memory dict with TTL, or a `crm_rate_limits` table
- **CORS:** Explicit allowlist of domains in config (`CORS_ALLOWED_ORIGINS`). Never use `*`. Return 403 for unknown origins
- **Input sanitization:** All string inputs stripped, length-limited, and HTML-escaped before storage. Use `markupsafe.escape()` on any user input rendered in templates
- **Content-Type enforcement:** Reject requests to `/api/leads` that aren't `application/json`

### HTTPS and Headers (Phase 1 deploy)
- **HTTPS mandatory:** Let's Encrypt via certbot. Nginx redirects all HTTP to HTTPS
- **Security headers** in Nginx config:
  ```
  add_header X-Content-Type-Options nosniff;
  add_header X-Frame-Options DENY;              # default for the authenticated CRM UI
  add_header X-XSS-Protection "1; mode=block";
  add_header Referrer-Policy strict-origin-when-cross-origin;
  add_header Content-Security-Policy "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline';";
  ```
- **Lead form embedding:** `/lead-form` is intended for external iFrame embedding, so do not apply `X-Frame-Options: SAMEORIGIN` there. Instead, use a route-specific `Content-Security-Policy: frame-ancestors https://allowed-site-1.com https://allowed-site-2.com;` allowlist (or the exact parent domains that will embed the form). Keep `X-Frame-Options: DENY` on the rest of the CRM.
- **ProxyFix middleware:** `ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_prefix=1)` so Flask trusts Nginx's forwarded headers

### Database Security
- **PostgreSQL:** Bind to `127.0.0.1` only (`listen_addresses = 'localhost'` in `postgresql.conf`). No public port exposure
- **Power BI access:** Via SSH tunnel only (see Phase 7) — never open port 5432 in the security group
- **Backups:** Daily automated backup via cron: `pg_dump bridge_crm | gzip > /backups/bridge_crm_$(date +\%Y\%m\%d).sql.gz`. Rotate: keep 7 daily + 4 weekly. Test restore monthly
- **ERP connection:** Read-only MySQL user (`crm_reader`) with `SELECT` only on `gadgetkg_bwqa_main`. No write permissions

### Monitoring (Phase 1 deploy)
- **Health check endpoint:** `GET /health` returns `{"status": "ok", "db": "ok"}` — checks PostgreSQL connectivity. Unauthenticated, for uptime monitoring
- **Access logs:** Nginx access logs with IP, path, status code, response time. Rotate weekly via logrotate
- **Application logging:** Python `logging` module, dual output to stdout + `/var/log/bridge-crm/app.log`. Log all authentication events, email sends, WhatsApp sends, sync runs
- **Uptime monitoring:** Use a free service (UptimeRobot, Better Uptime) to ping `/health` every 5 minutes and alert on downtime

---

## Verification Plan

After each phase, verify end-to-end:

- **Phase 1**: Login, create an Account, view Account list, view Account detail. Confirm PostgreSQL has correct data
- **Phase 2**: Submit lead via iFrame form from a test HTML page. Verify lead appears in CRM. Convert lead to Account + Opportunity
- **Phase 3**: Create Opportunity, drag between pipeline stages on kanban. Verify probability updates. Add notes to activity timeline
- **Phase 4**: Run `python -m integrations.erp_sync` manually. Verify products appear in `/products`. Run `--full` sync and confirm counts match ERP. Add quote lines to an Opportunity using the model/grade picker. Verify stock counts display and opportunity amount auto-calculates
- **Phase 5**: Send email from Opportunity detail page. Verify email arrives. Verify it appears in "Emails" tab and activity timeline
- **Phase 6**: Send WhatsApp template message from a Lead. Verify delivery. Test incoming message webhook with Meta's test tool
- **Phase 7**: Verify dashboard shows correct pipeline stats. Export CSV. Connect Power BI Desktop via SSH tunnel to PostgreSQL read-only user. Verify queries return expected data
- **Phase 8**: Open CRM on mobile browser. "Add to Home Screen." Verify all pages are usable. Test pipeline kanban on touch device

---

## Key Reference Files

- `inventory-chatbot/app.py` — Flask app structure, Blueprint registration, session auth pattern
- `inventory-chatbot/config.py` + `config.example.py` — `os.environ[]` + python-dotenv pattern to replicate
- `inventory-chatbot/ecommerce/db.py` — Query patterns (parameterized SQL, dict-from-row) to adapt for SQLAlchemy Core
- `inventory-chatbot/ecommerce/approval.py` — Blueprint + AJAX pattern reference
- `inventory-chatbot/ecommerce/notifications/email_digest.py` — Jinja2 template-as-string and UI patterns (modals, toasts)
- `~/Downloads/gadgetkg_bwqa_main_schema_v2.3.9.sql` — ERP schema (sync targets: lines 722-768 `wh_inv_master`, 683-698 `web_model_master`, 628-638 `web_attribute_master`, 646-657 `web_brand_master`, 665-675 `web_category_master`)
