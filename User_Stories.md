# User Stories — AI Implementation
### For Development Team

**Created:** April 4, 2026
**Source:** `AI_Implementation_Plan.md`, `Ecommerce_AI_Plan.md`

---

## How to Use This Document

Each epic maps to a phase from the AI Implementation Plan. Stories are written in standard format and include acceptance criteria. Prioritize top-down within each epic — stories are ordered by dependency.

**Point estimates and sprint assignments are left for the team to determine during planning.**

---

## Epic 0: ERP Training & Migration

> **Context:** The business is migrating from SQL Server (legacy) to a new MySQL ERP (`gadgetkg_bwqa_main`). All downstream work (chatbot, alerts, Power BI, HubSpot integration) depends on the team understanding both systems.

### 0.1 — Legacy System Knowledge Transfer

**As a** developer onboarding to the project,
**I want** documented training on the current SQL Server schema (`ReportingInventoryFlat`, `EcommerceListingsLog`, `EcommerceProductCatalog`, `EcommercePricingBatch`, `EcommercePricingRecommendation`) and the Flask chatbot architecture,
**so that** I can maintain and extend the existing system during the migration period.

**Acceptance Criteria:**
- [ ] Developer can explain the `ReportingInventoryFlat` refresh cycle (hourly via SQL Server Agent Job)
- [ ] Developer can explain the `Product_Place`, `Version`, `Grade` column semantics and filtering logic
- [ ] Developer can run the chatbot locally and trace a query from user input → Claude → SQL → response
- [ ] Developer can run the ecommerce pipeline manually (`python -m ecommerce.main`) and explain the data flow
- [ ] Developer understands the EC2 deployment (Ubuntu 24.04, gunicorn, `~/chatbot-env` venv)

### 0.2 — New ERP Schema Training

**As a** developer,
**I want** documented training on the new ERP MySQL schema (`gadgetkg_bwqa_main`),
**so that** I can build views, queries, and integrations against the new system.

**Acceptance Criteria:**
- [ ] Developer can explain the core tables: `wh_inv_master`, `web_model_master`, `web_brand_master`, `web_attribute_master`, `master_clients`
- [ ] Developer understands the foreign key relationships (e.g., `model_id` → `web_model_master.id`, `color_id` → `web_attribute_master.id`)
- [ ] Developer can explain the workshop pipeline tables: `workshop_master` → `workshop_iqc` → `workshop_device_repairs` → `workshop_oqc`
- [ ] Developer can explain the sales/invoicing tables: `bw_sales_invoice_header`, `bw_sales_invoice_items`, `shipment_header`
- [ ] Developer understands `item_status` values and their meaning (Ready, IQC, Repair, OQC, Allocated, Shipped, etc.)
- [ ] Schema documentation is written and stored in the project repo

### 0.3 — Data Migration: SQL Server → MySQL ERP

**As a** operations manager,
**I want** all active inventory, product catalog, and listing data migrated from SQL Server to the new ERP,
**so that** the ERP becomes the single source of truth and the legacy system can be decommissioned.

**Acceptance Criteria:**
- [ ] Migration plan documented: which tables map to which ERP tables, field-by-field mapping
- [ ] Data validation scripts written — row counts, spot checks, and reconciliation reports comparing old vs new
- [ ] Migration executed in a staging environment first, validated, then run in production
- [ ] Parallel run period defined — both systems active, discrepancies flagged daily
- [ ] Rollback plan documented in case of critical issues
- [ ] Legacy SQL Server decommission criteria defined (e.g., 2 weeks with zero discrepancies)

### 0.4 — Power BI Reports for New ERP

**As a** management user,
**I want** the existing Power BI reports rebuilt to connect to the new MySQL ERP,
**so that** I have the same (or improved) reporting visibility after migration.

**Acceptance Criteria:**
- [ ] Inventory of existing Power BI reports created (list of all current reports and their data sources)
- [ ] MySQL data source connection configured in Power BI (via ODBC or native MySQL connector)
- [ ] Each existing report rebuilt against the new ERP schema (or the `vw_erp_inventory_flat` view)
- [ ] Reports validated against legacy reports during parallel run — numbers match
- [ ] New reports published to Power BI Service / shared workspace
- [ ] Any new reporting opportunities identified from the richer ERP schema (workshop pipeline, invoicing, etc.)

### 0.5 — Power BI Workshop Pipeline Dashboard (New)

**As a** warehouse manager,
**I want** a Power BI dashboard showing the workshop pipeline (IQC → Repair → OQC → Ready),
**so that** I can see bottlenecks and throughput at a glance.

**Acceptance Criteria:**
- [ ] Dashboard shows device counts at each pipeline stage (IQC, Repair, OQC, Ready)
- [ ] Drill-down by brand, model, project
- [ ] Average time-in-stage metrics displayed
- [ ] Devices in stage > threshold (e.g., 48 hours in IQC) highlighted
- [ ] Auto-refresh schedule configured

---

## Epic 1A: Chatbot Production Hardening

> **Context:** The chatbot is live but runs manually. Needs to be production-grade.

### 1A.1 — Gunicorn systemd Service

**As a** sysadmin,
**I want** the Flask chatbot running as a `systemd` service,
**so that** the app automatically restarts on server reboot and can be managed with standard Linux commands.

**Acceptance Criteria:**
- [ ] `systemd` unit file created at `/etc/systemd/system/chatbot.service`
- [ ] Service starts on boot (`systemctl enable chatbot`)
- [ ] `systemctl start/stop/restart/status chatbot` all work correctly
- [ ] Gunicorn logs written to a persistent location (not just stdout)
- [ ] Service tested by rebooting the EC2 instance

### 1A.2 — Fix ProjectName Trailing Spaces

**As a** chatbot user,
**I want** queries involving ProjectName to return correct results even when the database has trailing spaces (e.g., `'Bridge Product '`),
**so that** I don't get 0-result answers for valid questions.

**Acceptance Criteria:**
- [ ] Claude's system prompt updated to `RTRIM()` ProjectName in generated SQL, or prompt includes the exact ProjectName values
- [ ] Tested with "How many devices are in Bridge Product?" — returns correct count
- [ ] Tested with Telus, MobileShop, OSL project names

---

## Epic 1B: Additional Flat Reporting Tables

### 1B.1 — Telus Flat Table

**As a** manager,
**I want** a `ReportingInventoryFlat_Telus` table that includes all Telus project devices (including shipped),
**so that** I can report on full Telus project history, not just in-stock.

**Acceptance Criteria:**
- [ ] Stored procedure created filtering `ProjectName LIKE '%Telus%'` with all version codes
- [ ] SQL Server Agent Job scheduled for Sunday 2 AM
- [ ] Table populated and row counts validated against source
- [ ] Chatbot can query this table (or a future alert can reference it)

### 1B.2 — MobileShop Flat Table

**As a** manager,
**I want** a `ReportingInventoryFlat_MobileShop` table for MobileShop project reporting.

**Acceptance Criteria:**
- [ ] Stored procedure created filtering `ProjectName = 'MobileShop'`
- [ ] Decision documented: all versions or in-stock only?
- [ ] SQL Server Agent Job scheduled for Sunday 2 AM
- [ ] Table populated and validated

### 1B.3 — OSL Flat Table

**As a** manager,
**I want** a `ReportingInventoryFlat_OSL` table for OSL project reporting.

**Acceptance Criteria:**
- [ ] Stored procedure created filtering `ProjectName = 'OSL'`
- [ ] Decision documented: all versions or in-stock only?
- [ ] SQL Server Agent Job scheduled for Sunday 2 AM
- [ ] Table populated and validated

---

## Epic 1C: Inventory Data Alerts

### 1C.1 — Alerts Module Scaffold

**As a** developer,
**I want** an `alerts/` Python module on EC2 with a configurable alert framework,
**so that** individual alert rules can be added as simple Python functions.

**Acceptance Criteria:**
- [ ] `alerts/` module created with `__init__.py`, `runner.py`, `rules/`, `notifiers/`
- [ ] Each alert rule is a function: query DB → evaluate condition → return triggered devices
- [ ] Notifiers support Email (SMTP) and Slack (webhook)
- [ ] `runner.py` loads all active rules and runs them in sequence
- [ ] Configurable via environment variables or config file (thresholds, recipients, channels)
- [ ] Cron job set up on EC2 (e.g., every 2 hours)

### 1C.2 — Grading Backlog Alert

**As a** warehouse manager,
**I want** an automatic alert when any device has been in Grading for more than 48 hours,
**so that** I can investigate bottlenecks before they grow.

**Acceptance Criteria:**
- [ ] SQL query identifies devices where `DATEDIFF(HOUR, Grading_Created, GETDATE()) > 48`
- [ ] Alert email lists ESN, ProjectName, Model, hours in grading
- [ ] Slack message sent to configured channel
- [ ] Alert only fires if there are matching devices (no empty alerts)

### 1C.3 — Telus Grading Backlog Alert

**As a** warehouse manager,
**I want** a separate alert for Telus devices in Grading > 48 hours,
**so that** Telus-specific SLAs are monitored independently.

**Acceptance Criteria:**
- [ ] Same logic as 1C.2 but filtered to `ProjectName LIKE '%Telus%'`
- [ ] Sent via Email only (per plan)

### 1C.4 — Function Test Backlog Alert

**As a** warehouse manager,
**I want** an alert when devices are stuck in Function Test for more than 24 hours.

**Acceptance Criteria:**
- [ ] SQL query identifies devices in Function Test > 24 hours
- [ ] Slack notification sent

### 1C.5 — High Volume Intake Alert

**As an** operations manager,
**I want** an alert when more than 500 new devices are received in a 24-hour period,
**so that** I can allocate resources for the increased processing load.

**Acceptance Criteria:**
- [ ] SQL counts devices with `ReceivedDate` in the last 24 hours
- [ ] Email sent if count > 500 (threshold configurable)

### 1C.6 — Ungraded Stock Alert

**As a** manager,
**I want** an alert when devices have been received for over 72 hours with no Grading start,
**so that** nothing falls through the cracks.

**Acceptance Criteria:**
- [ ] SQL identifies devices received > 72 hours ago with `Grading_Created IS NULL`
- [ ] Email sent with device list

---

## Epic 1D: Ecommerce Pipeline — Pending Tasks

> **Context:** 1D-i (price scanning + dashboard) is complete. 1D-ii (listing preview) is in testing. These stories cover remaining work through 1D-iii.

### 1D.1 — Populate EcommerceProductCatalog

**As a** ecommerce operator,
**I want** the `EcommerceProductCatalog` table populated with Amazon ASINs, UPCs, and eBay EPIDs for our top SKUs,
**so that** the pricing pipeline can use ASIN-based Amazon lookups instead of less-precise keyword search.

**Acceptance Criteria:**
- [ ] Top 50 SKUs (by volume in Ecommerce Storefront) identified
- [ ] Amazon ASINs researched and entered for each SKU
- [ ] UPCs entered where available (from packaging or vendor data)
- [ ] eBay EPIDs entered where available (from eBay catalog search)
- [ ] Pipeline re-run shows Amazon ASIN prices for populated SKUs

### 1D.2 — Remove TOP 10 Limit in Product Query

**As a** ecommerce operator,
**I want** the pipeline to process all eligible products, not just the first 10,
**so that** every SKU in Ecommerce Storefront gets a pricing recommendation.

**Acceptance Criteria:**
- [ ] `TOP 10` removed from `fetch_all_pending_products()` in `ecommerce/db.py`
- [ ] Pipeline tested with full product set — runs without timeout or memory issues
- [ ] Dashboard shows all product groups, not just 10

### 1D.3 — Validate Pricing & Listing Quality

**As a** ecommerce manager,
**I want** to review 2-3 weekly pipeline cycles of pricing recommendations and generated listings,
**so that** I have confidence the system produces accurate prices and professional listing copy before enabling auto-listing.

**Acceptance Criteria:**
- [ ] 2-3 weekly batches reviewed on the dashboard
- [ ] Recommended prices spot-checked against actual marketplace listings (manual verification)
- [ ] Generated listing copy reviewed for accuracy, professionalism, and correct condition mapping
- [ ] Any issues logged and fixed in the pipeline code
- [ ] Sign-off from ecommerce manager that quality is acceptable for auto-listing

### 1D.4 — Amazon SP-API Credentials & Integration

**As a** ecommerce operator,
**I want** Amazon SP-API credentials configured and the auto-listing flow activated,
**so that** approved listings are automatically posted to Amazon.

**Acceptance Criteria:**
- [ ] Amazon SP-API credentials obtained (refresh token, LWA app ID, LWA client secret, seller ID)
- [ ] Credentials added to `ecommerce/config.py` on EC2 (via `.env`)
- [ ] `listings/amazon.py` tested with a real listing in Amazon Seller Central sandbox (if available) or production
- [ ] Approve endpoint updated to call `amazon_listings.create_listing()` for Amazon CA recommendations
- [ ] Listing appears in Amazon Seller Central after approval

### 1D.5 — eBay API Credentials & Integration

**As a** ecommerce operator,
**I want** eBay API credentials configured and the auto-listing flow activated,
**so that** approved listings are automatically posted to eBay.

**Acceptance Criteria:**
- [ ] eBay OAuth credentials obtained (app ID, cert ID, refresh token)
- [ ] Credentials added to `ecommerce/config.py` on EC2 (via `.env`)
- [ ] `listings/ebay.py` tested with a real listing in eBay sandbox or production
- [ ] Approve endpoint updated to call `ebay_listings.create_listing()` for eBay CA recommendations
- [ ] Listing appears on eBay after approval

### 1D.6 — Switch Approve Endpoint from Preview to Auto-Post (1D-iii)

**As a** ecommerce operator,
**I want** the approve button to auto-post listings to the marketplace API (instead of just showing a preview),
**so that** the approval workflow is fully automated end-to-end.

**Acceptance Criteria:**
- [ ] `approval.py` updated to call marketplace listing modules on approve (Amazon or eBay based on recommendation)
- [ ] Listing record created in `EcommerceListingsLog` after successful API post
- [ ] Preview modal still shown with the generated copy (for reference), but listing is already posted
- [ ] Best Buy CA and Reebelo CA recommendations still show preview-only (no API for these marketplaces)
- [ ] Error handling: if API post fails, recommendation is NOT marked as approved — error shown in toast

---

## Epic 1E: ERP Inventory Chatbot

> **Context:** Depends on the ERP being live and the team completing Epic 0 training.

### 1E.1 — MySQL Connectivity from EC2

**As a** developer,
**I want** the Linux EC2 to connect to the new ERP MySQL database,
**so that** the chatbot and other integrations can query ERP data.

**Acceptance Criteria:**
- [ ] MySQL host firewall whitelisted for the Linux EC2 IP
- [ ] `PyMySQL` installed in `~/chatbot-env`
- [ ] Test script connects and runs a basic `SELECT` against `wh_inv_master`
- [ ] Connection uses a read-only MySQL user (not root)

### 1E.2 — Create Inventory Flat View in ERP

**As a** developer,
**I want** a denormalized MySQL VIEW (`vw_erp_inventory_flat`) joining core inventory tables,
**so that** Claude can generate SQL against a single readable schema.

**Acceptance Criteria:**
- [ ] VIEW created joining `wh_inv_master` with `web_model_master`, `web_brand_master`, `web_attribute_master`, `master_clients`
- [ ] VIEW includes: serial_number, imei, lot_num, item_status, bin_location, inward_grade, outward_grade, costs, model_name, brand_name, color, ram, storage, vendor_name, received_date
- [ ] VIEW returns correct data — spot-checked against raw tables
- [ ] VIEW documented (column definitions and semantics)

### 1E.3 — Create Workshop Pipeline View (Optional)

**As a** warehouse manager,
**I want** a MySQL VIEW joining the workshop pipeline tables,
**so that** I can ask the chatbot about device repair status and pipeline bottlenecks.

**Acceptance Criteria:**
- [ ] VIEW joins `workshop_master` → `workshop_iqc` → `workshop_device_repairs` → `workshop_oqc`
- [ ] Includes work order ID, device serial, stage, status, engineer, timestamps
- [ ] VIEW documented

### 1E.4 — ERP Chatbot Route

**As a** management user,
**I want** a chatbot route (`/erp-chat` or a mode toggle in the existing chatbot) that queries the new ERP,
**so that** I can ask natural language questions about ERP inventory, workshop status, and invoicing.

**Acceptance Criteria:**
- [ ] New route or mode added to the Flask app
- [ ] Claude system prompt includes the `vw_erp_inventory_flat` schema (and optionally the workshop view)
- [ ] Claude generates MySQL-dialect SQL (not T-SQL)
- [ ] Tested with: "How many devices are in Ready status by brand?", "What devices are in IQC?", "Show inventory from lot number X"
- [ ] Errors handled gracefully (connection failure, empty results, invalid SQL)

### 1E.5 — Migrate Ecommerce Pipeline to ERP

**As a** ecommerce operator,
**I want** the ecommerce pipeline to query the new ERP instead of SQL Server,
**so that** it stays operational after the legacy system is decommissioned.

**Acceptance Criteria:**
- [ ] `ecommerce/db.py` updated to connect to MySQL (via PyMySQL) instead of SQL Server (via pyodbc)
- [ ] SQL queries translated from T-SQL to MySQL dialect
- [ ] Ecommerce tables (`EcommerceListingsLog`, `EcommerceProductCatalog`, `EcommercePricingBatch`, `EcommercePricingRecommendation`) recreated in MySQL or kept on SQL Server with dual connections
- [ ] Pipeline tested end-to-end against the new database
- [ ] Dashboard still functions correctly

---

## Epic 2A: HubSpot CRM Setup

### 2A.1 — HubSpot Account & Pipeline Configuration

**As a** sales manager,
**I want** HubSpot set up with our deal pipeline, contact properties, and deal stages,
**so that** the sales team has a CRM to track customers and deals.

**Acceptance Criteria:**
- [ ] HubSpot Free (or Starter) account created
- [ ] Deal pipeline stages defined and configured (e.g., Lead → Qualified → Proposal → Negotiation → Closed Won / Lost)
- [ ] Custom contact/company properties created for industry-specific fields (e.g., device types, volume tier)
- [ ] Email integration connected (Gmail or Outlook)
- [ ] Sales team trained on basic HubSpot usage

### 2A.2 — ERP Client ID Mapping

**As a** developer,
**I want** a mapping between HubSpot Company/Contact IDs and `master_clients.id` in the ERP,
**so that** downstream integrations (inventory visibility, warehouse handoff) can link CRM deals to ERP clients.

**Acceptance Criteria:**
- [ ] Custom property `erp_client_id` created on HubSpot Company object
- [ ] Existing clients in `master_clients` matched to HubSpot companies — mapping populated
- [ ] Process documented for new clients: when a new company is created in HubSpot, the `erp_client_id` must be set
- [ ] Validation script: list HubSpot companies missing `erp_client_id`

---

## Epic 2B: Inventory Visibility in HubSpot

### 2B.1 — Inventory Sync Script

**As a** sales rep,
**I want** to see available stock counts on HubSpot deal records,
**so that** I know what inventory is available without leaving the CRM.

**Acceptance Criteria:**
- [ ] Python script queries `vw_erp_inventory_flat` for stock counts by brand/model/grade where `item_status = 'Ready'`
- [ ] Script pushes aggregated counts to HubSpot Company custom properties via HubSpot API
- [ ] Cron job runs daily (or more frequently if needed)
- [ ] HubSpot deal record shows: available stock by model, status breakdown, last sync timestamp
- [ ] Tested with a real deal record — stock numbers match ERP

### 2B.2 — HubSpot CRM Card (Optional)

**As a** sales rep,
**I want** a live inventory widget embedded on HubSpot deal records,
**so that** I get real-time stock visibility without waiting for the daily sync.

**Acceptance Criteria:**
- [ ] CRM Card API endpoint built on EC2 (Flask route)
- [ ] Card queries ERP MySQL in real-time when the deal record is viewed
- [ ] Card displays stock count, status breakdown, and model details relevant to the deal
- [ ] Card registered in HubSpot developer portal and visible on deal records

---

## Epic 2C: Warehouse Handoff Automation

### 2C.1 — HubSpot Webhook Receiver

**As a** developer,
**I want** a Flask endpoint on EC2 that receives HubSpot webhook events when a deal moves to "Closed Won",
**so that** we can trigger automated order creation in the ERP.

**Acceptance Criteria:**
- [ ] Flask route created (e.g., `POST /hubspot/webhook`)
- [ ] Webhook signature verified for security
- [ ] Event parsed: deal ID, company ID, deal properties extracted
- [ ] `erp_client_id` resolved from HubSpot company record
- [ ] Endpoint logged and monitored

### 2C.2 — ERP Order Creation on Closed Won

**As a** warehouse manager,
**I want** an order automatically created in the ERP when a deal is marked "Closed Won" in HubSpot,
**so that** I see the order natively in the ERP without manual data entry.

**Acceptance Criteria:**
- [ ] Decision made: write directly to MySQL or use ERP API (if available)
- [ ] `bw_sales_invoice_header` record created with client, date, totals
- [ ] `bw_sales_invoice_items` records created for each line item (serial, model, grade, price)
- [ ] `wh_inv_master.item_status` updated to "Allocated" for each allocated device
- [ ] `wh_inv_master.final_order_id` set to the new invoice ID
- [ ] Warehouse team confirms the order appears in the ERP UI
- [ ] Error handling: if order creation fails, alert sent to operations (no silent failures)

### 2C.3 — Shipment Record Creation (Optional)

**As a** warehouse manager,
**I want** a `shipment_header` record created when devices are marked as shipped,
**so that** shipment tracking is captured in the ERP.

**Acceptance Criteria:**
- [ ] Trigger defined: manual action in ERP, or automated when `item_status` → "Shipped"
- [ ] `shipment_header` record created with order reference, client, date, tracking info
- [ ] (Optional) HubSpot deal updated with shipment status via API callback

---

## Epic 3A: QuickBooks Flat Table

### 3A.1 — QuickBooks API Connection

**As a** developer,
**I want** a Python script that authenticates with the QuickBooks Online API and fetches financial data,
**so that** we can build a flat reporting table for AI queries.

**Acceptance Criteria:**
- [ ] QuickBooks OAuth 2.0 flow implemented (token refresh automated)
- [ ] Script can fetch: invoices, expenses, payments, accounts
- [ ] Rate limits understood and respected
- [ ] Connection tested against production QuickBooks account

### 3A.2 — Financial Flat Table

**As a** manager,
**I want** a flat SQL table containing key financial data from QuickBooks, refreshed nightly,
**so that** the AI chatbot and Power BI can query financial data.

**Acceptance Criteria:**
- [ ] Table created with columns: invoice_number, customer_name, amount, due_date, status, expense_category, vendor, revenue_month
- [ ] Nightly refresh via cron or SQL Server Agent Job (2 AM)
- [ ] Data validated against QuickBooks UI — totals match
- [ ] At least 12 months of historical data loaded

---

## Epic 3B: QuickBooks AI Chatbot

### 3B.1 — Financial Chatbot Route

**As a** manager,
**I want** to ask the chatbot financial questions in natural language,
**so that** I can get quick answers about receivables, expenses, and revenue without opening QuickBooks.

**Acceptance Criteria:**
- [ ] New route or mode in the chatbot for financial queries
- [ ] Claude system prompt includes the QB flat table schema
- [ ] Tested with: "What is our outstanding AR this month?", "Which customers have invoices overdue > 30 days?", "Total expenses in March by category?", "Revenue this month vs last month?"
- [ ] Access restricted to authorized users (management only)

---

## Epic 3C: QuickBooks Financial Alerts

### 3C.1 — Overdue Invoice Alert

**As a** finance manager,
**I want** an automatic alert when any invoice is overdue by more than 30 days,
**so that** collections follow-up happens promptly.

**Acceptance Criteria:**
- [ ] Alert rule queries QB flat table for invoices where `status = 'overdue'` and `DATEDIFF > 30`
- [ ] Email sent to finance team with customer name, invoice number, amount, days overdue

### 3C.2 — Large Expense Alert

**As a** manager,
**I want** an alert when a single expense exceeds a configurable threshold,
**so that** I'm aware of large expenditures in real time.

**Acceptance Criteria:**
- [ ] Threshold configurable (e.g., $5,000)
- [ ] Slack message sent with expense details

### 3C.3 — Low Cash Alert

**As a** manager,
**I want** an alert when the cash balance drops below a threshold,
**so that** I can take action before a cash flow problem.

**Acceptance Criteria:**
- [ ] Cash balance fetched from QB API or flat table
- [ ] Email sent if below threshold (configurable)

### 3C.4 — Payment Received Alert

**As a** sales rep,
**I want** a notification when a customer payment is received,
**so that** I can follow up or update the deal status.

**Acceptance Criteria:**
- [ ] Alert triggered when invoice status changes to "paid" in the QB flat table
- [ ] Slack notification sent with customer name and amount

---

## Epic 4: Unified AI Assistant

### 4.1 — Combined Schema Prompt

**As a** developer,
**I want** the chatbot to have a combined schema context covering inventory (ERP), CRM (HubSpot), and financial (QuickBooks) data,
**so that** Claude can route questions to the correct data source.

**Acceptance Criteria:**
- [ ] System prompt includes schemas for: `vw_erp_inventory_flat` (MySQL), HubSpot synced table or API, QB flat table
- [ ] Claude correctly identifies which data source to query based on the question
- [ ] Cross-domain questions routed to multiple sources (e.g., "inventory for deals closing this week" → ERP + HubSpot)

### 4.2 — Multi-Source Query Execution

**As a** manager,
**I want** to ask one question that pulls from multiple data sources,
**so that** I get a unified answer without asking separate questions per system.

**Acceptance Criteria:**
- [ ] Chatbot can execute queries against MySQL (ERP), SQL Server (legacy, if still active), and HubSpot
- [ ] Results combined into a single coherent response
- [ ] Tested with: "How many A-Grade devices do we have for the MobileShop deal closing this week?", "Total inventory value for customers with overdue invoices"
- [ ] Timeout handling: if one source is slow, partial results returned with a note

### 4.3 — Access Control by Role

**As an** admin,
**I want** different chatbot users to have access to different data domains,
**so that** warehouse staff don't see financial data and sales staff don't see cost data.

**Acceptance Criteria:**
- [ ] User roles defined (e.g., warehouse, sales, management, finance)
- [ ] Each role has a whitelist of queryable tables/domains
- [ ] Claude's system prompt dynamically adjusted based on logged-in user's role
- [ ] Tested: warehouse user cannot query QB data; sales user cannot query device cost fields

---

## Epic 5A: Meeting & Productivity Intelligence

### 5A.1 — Claude Cowork Setup

**As a** manager,
**I want** Claude Cowork configured with access to a shared Google Drive folder for meeting transcripts,
**so that** meeting notes, action items, and follow-ups are generated automatically.

**Acceptance Criteria:**
- [ ] Claude Pro or Team subscription active
- [ ] Cowork connected to Google Drive folder (or designated local folder)
- [ ] Test: drop a meeting transcript → Cowork produces summary, action items with owners/deadlines, and draft follow-up email
- [ ] Output format agreed upon by management team

### 5A.2 — Meeting Notes Template

**As a** manager,
**I want** a standardized meeting notes format generated by Cowork,
**so that** all meetings produce consistent, searchable documentation.

**Acceptance Criteria:**
- [ ] Template includes: Date, Attendees, Key Discussion Points, Decisions Made, Action Items (owner + deadline), Follow-up Notes
- [ ] Cowork prompt tuned to produce this format consistently
- [ ] Notes stored in a shared location accessible to all attendees

---

## Epic 5B: Productivity Automation

### 5B.1 — AI Email Drafting via HubSpot Breeze

**As a** sales rep,
**I want** AI-drafted sales emails based on deal context in HubSpot,
**so that** I can send professional follow-ups faster.

**Acceptance Criteria:**
- [ ] HubSpot Starter plan activated (for Breeze AI features)
- [ ] Breeze AI enabled for email drafting
- [ ] Sales team trained on using AI email suggestions
- [ ] Sample emails reviewed for quality and tone

### 5B.2 — Weekly Inventory Summary Reports

**As a** manager,
**I want** an AI-generated weekly inventory summary report,
**so that** I get a high-level view of stock movements, grading throughput, and notable changes.

**Acceptance Criteria:**
- [ ] Python script or Claude Cowork project generates the report
- [ ] Report includes: total stock count, intake volume, grading throughput, top models by volume, week-over-week changes
- [ ] Delivered via email or shared drive every Monday morning
- [ ] Format reviewed and approved by management

---

## Epic R-A: AI-Powered Device Grading Assistance

### RA.1 — Grading Vision POC

**As a** warehouse manager,
**I want** a proof-of-concept where a camera captures a device and an AI model suggests a grade,
**so that** we can evaluate whether AI grading improves consistency and speed.

**Acceptance Criteria:**
- [ ] POC scope defined: one device category (e.g., iPhones), limited grade set (A/B/C)
- [ ] Image capture workflow defined (tablet camera, photo station, lighting)
- [ ] Claude Vision API or alternative evaluated with sample device photos
- [ ] Grading criteria documented (what makes an A vs B vs C — scratches, dents, screen condition)
- [ ] POC tested with 50+ devices — AI grade compared against human grade
- [ ] Accuracy report produced: % agreement, common disagreements, false positives/negatives
- [ ] Go/no-go decision documented based on accuracy results

---

## Epic R-B: Demand Forecasting

### RB.1 — Historical Data Preparation

**As a** data analyst,
**I want** historical inventory data (received date, model, grade, project, time-to-sell) extracted and cleaned,
**so that** a forecasting model can be trained.

**Acceptance Criteria:**
- [ ] At least 12 months of historical data extracted from ERP / legacy SQL Server
- [ ] Data cleaned: nulls handled, outliers flagged, consistent model naming
- [ ] Dataset includes: model, brand, grade, received_date, sold_date (or time-to-sell), project, quantity

### RB.2 — Demand Forecasting Model

**As a** operations manager,
**I want** a model that predicts which device models will be in high demand next month,
**so that** I can optimize procurement and stock levels.

**Acceptance Criteria:**
- [ ] Model built using scikit-learn or Prophet (Python)
- [ ] Predictions include: top 10 models by expected demand, optimal stock levels by grade, devices at risk of margin erosion (aging stock)
- [ ] Model accuracy validated against holdout data (backtesting)
- [ ] Output delivered as a weekly report or integrated into the chatbot

---

## Epic R-C: Automated Customer Communication

### RC.1 — Post-Sale Satisfaction Survey

**As a** sales manager,
**I want** an automated satisfaction survey sent after a deal closes,
**so that** we collect customer feedback without manual follow-up.

**Acceptance Criteria:**
- [ ] HubSpot Workflow triggers survey email on "Closed Won" (after configurable delay)
- [ ] Survey is short (3-5 questions) and mobile-friendly
- [ ] Responses tracked in HubSpot

### RC.2 — Automated Follow-Up Sequences

**As a** sales rep,
**I want** automated email sequences for leads that have gone quiet,
**so that** no lead falls through the cracks.

**Acceptance Criteria:**
- [ ] HubSpot Workflow: if no activity on a deal for X days → trigger follow-up sequence
- [ ] Sequence is 3-4 emails, spaced over 2 weeks
- [ ] AI-generated email content (via Breeze) personalized to the deal context
- [ ] Rep can override or pause the sequence manually

### RC.3 — Shipment Notifications

**As a** customer,
**I want** an automatic notification when my order ships,
**so that** I know when to expect delivery.

**Acceptance Criteria:**
- [ ] Triggered by `item_status` → "Shipped" in ERP (via Phase 2C webhook or polling script)
- [ ] Email includes: order reference, tracking number (if available), estimated delivery
- [ ] HubSpot deal updated with shipment status

---

## Epic R-D: AI-Assisted B2B Pricing

### RD.1 — B2B Pricing Recommendation Engine

**As a** sales manager,
**I want** AI-generated pricing recommendations for bulk/B2B deals based on inventory data and market pricing,
**so that** I can quote competitively without manual research.

**Acceptance Criteria:**
- [ ] Pricing model considers: device grade, model, age in inventory, volume, market data (from ecommerce pipeline)
- [ ] Claude generates a pricing recommendation narrative for the sales team
- [ ] Integrated into chatbot: "Suggest pricing for 200 iPhone 14 Grade A units"
- [ ] Recommendations include: suggested unit price, margin analysis, market comparisons

---

## Epic R-E: Internal Knowledge Base Assistant

### RE.1 — Document Ingestion & RAG Setup

**As a** staff member,
**I want** to ask an AI questions about our internal processes, SOPs, and policies,
**so that** I can find answers without searching through documents or asking colleagues.

**Acceptance Criteria:**
- [ ] Internal documents identified: grading criteria, warehouse SOPs, return policies, project-specific procedures
- [ ] Documents stored in Google Drive (or a designated location)
- [ ] RAG (retrieval-augmented generation) pipeline built: document chunking → embeddings → vector store → Claude retrieval
- [ ] Chatbot route or mode created for knowledge base queries
- [ ] Tested with: "What is the grading criteria for B-Grade?", "What is the Telus return process?", "How do I create a new project?"
- [ ] Answers cite the source document

---

## Epic R-F: Carrier/Client Portal (Long-Term)

### RF.1 — Client Portal MVP

**As a** carrier client (Telus, MobileShop, OSL),
**I want** a web portal where I can log in and see my project's inventory status, grading results, and shipment readiness,
**so that** I don't need to email or call for status updates.

**Acceptance Criteria:**
- [ ] Authentication: client-specific login (one account per carrier)
- [ ] Data scoped to the client's project only (e.g., Telus sees only Telus data)
- [ ] Dashboard shows: total devices in pipeline, status breakdown (IQC/Grading/Ready/Shipped), grading results
- [ ] Powered by project-specific flat tables (Phase 1B) or ERP views
- [ ] Mobile-responsive design
- [ ] Read-only — no data modification from the portal

---

## Story Dependency Map

```
Epic 0 (ERP Training + Migration)
 ├── 0.1 Legacy Training ─────────────── Unblocks all Phase 1 work
 ├── 0.2 New ERP Training ────────────── Unblocks 0.3, 0.4, 1E, 2B, 2C
 ├── 0.3 Data Migration ──────────────── Unblocks legacy decommission
 ├── 0.4 Power BI Reports ────────────── Parallel with 0.3
 └── 0.5 Workshop Dashboard ──────────── After 0.2

Epic 1A (Chatbot Hardening) ──────────── Independent, do anytime
Epic 1B (Flat Tables) ────────────────── Independent, unblocks 1C
Epic 1C (Alerts) ─────────────────────── Depends on 1B
Epic 1D (Ecommerce Pending) ──────────── Independent, in progress

Epic 1E (ERP Chatbot) ────────────────── Depends on 0.2, 0.3
 └── 1E.5 Migrate Ecommerce ──────────── Depends on 1E.1

Epic 2A (HubSpot) ────────────────────── Independent, unblocks 2B + 2C
Epic 2B (Inventory in HubSpot) ───────── Depends on 1E + 2A
Epic 2C (Warehouse Handoff) ──────────── Depends on 2A + ERP write access

Epic 3A (QB Flat Table) ──────────────── Independent
Epic 3B (QB Chatbot) ─────────────────── Depends on 3A
Epic 3C (QB Alerts) ──────────────────── Depends on 3A + 1C (alerts framework)

Epic 4 (Unified Assistant) ───────────── Depends on 1E + 2B + 3B

Epic 5 (Meeting/Productivity) ────────── Independent, start anytime

Epics R-A through R-F ────────────────── Independent explorations, lower priority
```

---

*Generated from `AI_Implementation_Plan.md` and `Ecommerce_AI_Plan.md`. Update this document as stories are refined during sprint planning.*
