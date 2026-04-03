# AI Implementation Plan
### Internal Document — Management Team

**Prepared:** March 2026
**Last Updated:** April 2, 2026
**Status:** Active — Phase 1 In Progress (1D Code Complete, 1E Planned)

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current State](#current-state)
3. [AI Tool Stack](#ai-tool-stack)
4. [Phase 1 — Inventory Intelligence (Active)](#phase-1--inventory-intelligence-active)
5. [Phase 2 — CRM & Sales Pipeline](#phase-2--crm--sales-pipeline)
6. [Phase 3 — Financial Intelligence (QuickBooks)](#phase-3--financial-intelligence-quickbooks)
7. [Phase 4 — Unified AI Assistant](#phase-4--unified-ai-assistant)
8. [Phase 5 — Meeting & Productivity Intelligence](#phase-5--meeting--productivity-intelligence)
9. [Additional AI Recommendations](#additional-ai-recommendations)
10. [Infrastructure Overview](#infrastructure-overview)
11. [Phasing & Timeline Summary](#phasing--timeline-summary)
12. [Investment Overview](#investment-overview)

---

## Executive Summary

This document outlines a multi-phase AI implementation strategy for the business. The goal is to progressively automate data access, alert management, customer relationship tracking, and financial intelligence — reducing manual effort across warehouse, sales, and management teams.

The foundation has already been laid: a live AI chatbot is operational for inventory queries, and the ecommerce listing pipeline (Phase 1D) is code-complete and ready for deployment. This plan builds on that foundation systematically, ending with a unified AI assistant that can answer questions across inventory, CRM, and financial data simultaneously.

**Core Principles:**
- Build on existing infrastructure where possible (SQL Server, new ERP on MySQL, EC2)
- Leverage Claude's ecosystem (API, Claude Code, Cowork) as the primary AI toolchain
- Each phase delivers standalone value before the next begins
- Security and access control are non-negotiable at every phase

---

## Current State

### What We Have Today

| System | Status | Details |
|---|---|---|
| Inventory AI Chatbot | **Live** | Flask app on Linux EC2, powered by Claude API, queries `ReportingInventoryFlat` |
| Ecommerce Pipeline | **Code Complete** | 15 modules in `ecommerce/` — price scanning, approval flow, auto-listing. Awaiting deployment (credentials, DB tables, cron). See `Ecommerce_AI_Plan.md`. |
| Flat Reporting Table | **Live** | `ReportingInventoryFlat` — ~41,277 in-stock devices, refreshes hourly |
| SQL Server (Legacy) | **Live** | Windows EC2, hosts current inventory data — will be phased out after ERP migration |
| New ERP | **Migration Planned** | MySQL 5.7 (`gadgetkg_bwqa_main`) — normalized schema with `wh_inv_master`, workshop pipeline, invoicing, client management. Will become single source of truth |
| Linux EC2 | **Live** | Ubuntu 24.04, t2.medium, hosts chatbot + ecommerce pipeline |
| CRM | **None** | No CRM in place |
| Financial AI | **None** | QuickBooks used manually |
| Data Alerts | **None** | No automated alerting |
| Meeting AI | **None** | No AI meeting tooling |

### What the Chatbot Can Answer Today
- How many devices are in stock by Manufacturer, Model, Grade, Colour
- Device counts by Project, Product Place, Received Grade
- When devices were received, when they completed Function Test or Grading
- Device cost queries

### Known Limitations Today
- ProjectName trailing spaces (e.g., `'Bridge Product '`) can cause 0-result queries — being addressed in prompt engineering
- In-stock only (Version = '000') — shipped devices not yet queryable
- Single data source — inventory only

---

## AI Tool Stack

| Tool | Purpose | Cost |
|---|---|---|
| **Anthropic Claude API** | Text-to-SQL, answer formatting, listing copy generation, all AI generation | Pay per token |
| **Claude Code** | Development agent, scheduled data alerts (replaces OpenClaw), cron-triggered monitoring scripts, CI/CD automation | Included in Max plan ($100/mo) or usage-based |
| **Claude Cowork** | Meeting summaries, action items, document generation | Included in Pro/Team/Enterprise |
| **HubSpot (Free/Starter)** | CRM — contacts, deals, pipeline | Free tier available |
| **Python Flask** | Chatbot backend + ecommerce approval endpoints | Free / open source |
| **PyMySQL** | MySQL connector for new ERP database queries | Free / open source |
| **SQL Server Agent** | Scheduled flat table refreshes (legacy) | Already licensed |

> **Why Claude Code over OpenClaw?** OpenClaw was originally planned for autonomous data alerts. Claude Code's scheduled agents and CLI provide the same capability (connect to SQL Server, run queries on a schedule, send alerts via email/Slack) while staying within a single vendor ecosystem. This eliminates a separate open-source tool to install, maintain, and troubleshoot. Claude Code can run Python scripts directly, access the database, and integrate with notification services — all from the same toolchain already used for development.

---

## Phase 1 — Inventory Intelligence (Active)

### 1A. AI Inventory Chatbot ✅
**Status: Live**

Management staff can log into the chatbot and ask natural language questions about in-stock inventory. Claude generates SQL, executes it against the flat table, and returns a plain English answer.

**Example queries working today:**
- "How many A Grade Apple devices do we have?"
- "What is the total value of Samsung devices in Bridge Product?"
- "Show me all iPhone 13 models currently in grading"

**Pending:**
- Set up `gunicorn` as a `systemd` service so the app survives server reboots
- Improve prompt engineering to handle trailing spaces in ProjectName

---

### 1B. Additional Flat Reporting Tables
**Status: Planned — Phase 1**

Three new flat tables to support project-specific reporting and alerting:

| Table | Filter | Refresh Schedule | Purpose |
|---|---|---|---|
| `ReportingInventoryFlat_Telus` | `ProjectName LIKE '%Telus%'`, all versions | Weekly (Sunday 2am) | Full Telus project history including shipped |
| `ReportingInventoryFlat_MobileShop` | `ProjectName = 'MobileShop'` | Weekly (Sunday 2am) | MobileShop project reporting |
| `ReportingInventoryFlat_OSL` | `ProjectName = 'OSL'` | Weekly (Sunday 2am) | OSL project reporting |

> **Note:** Unlike the main chatbot table (in-stock only), the Telus table includes all version codes to provide full shipment history. Confirm whether MobileShop and OSL should also include all versions.

Each table gets its own stored procedure and SQL Server Agent Job.

---

### 1C. Inventory Data Alerts via Claude Code
**Status: Planned — Phase 1**

Use Claude Code's scheduled agents to monitor the flat table and send automated alerts. A Python alert script runs on a cron schedule, queries SQL Server, evaluates conditions, and sends notifications.

**How it works:**
1. A Python monitoring script connects to SQL Server via the existing ODBC Driver 18 connection
2. Claude Code scheduled agent (or Linux cron) triggers the script on a defined interval (e.g., every 2 hours)
3. If a condition is met, the script sends an alert via Email or Slack

**Implementation approach:**
- Write a standalone `alerts/` module (similar pattern to the `ecommerce/` module)
- Each alert rule is a Python function: run SQL query, evaluate threshold, send notification
- Claude Code can help develop, test, and iterate on alert rules directly from the CLI
- Scheduled via cron on the EC2 or via Claude Code's remote scheduled agents

**Initial Alert Rules:**

| Alert | Condition | Recipient | Channel |
|---|---|---|---|
| Grading Backlog | Device in Grading > 48 hours | Warehouse Manager | Email + Slack |
| Telus Grading Backlog | Telus device in Grading > 48 hours | Warehouse Manager | Email |
| Function Test Backlog | Device in Function Test > 24 hours | Warehouse Manager | Slack |
| High Volume Intake | >500 new devices received in 24 hours | Operations Manager | Email |
| Ungraded Stock | Device received > 72 hours with no Grading start | Manager | Email |

**SQL for Grading Backlog alert (example):**
```sql
SELECT ESN, ProjectName, Grading_Created,
       DATEDIFF(HOUR, Grading_Created, GETDATE()) AS HoursInGrading
FROM ReportingInventoryFlat
WHERE Grading_Created IS NOT NULL
AND Function_Test_Created IS NOT NULL
AND DATEDIFF(HOUR, Grading_Created, GETDATE()) > 48
ORDER BY HoursInGrading DESC
```

> **Security note:** The alert script will use a read-only database connection and run under a limited Linux user account — not root.

---

### 1D. Ecommerce Listing Pipeline ✅
**Status: Code Complete — Awaiting Deployment**

An AI-powered ecommerce listing workflow that runs daily, scans inventory flagged for ecommerce, researches competitive prices via marketplace APIs, recommends the best platform to sell on, and — upon human approval — drafts and posts the listing automatically.

All 15 modules are built and integrated in the `ecommerce/` directory. The approval Blueprint is registered in `app.py`. Full details in `Ecommerce_AI_Plan.md`.

**What's built:**
- Daily pipeline entry point (`ecommerce/main.py`)
- Amazon SP-API + eBay Browse API price fetching
- Deterministic pricing algorithm (highest floor price selection)
- HTML email digest with per-SKU approve/reject links
- Claude API listing copy generation (title, description, bullets)
- Amazon SP-API + eBay Inventory API listing creation
- Flask approval/rejection endpoints
- SQL Server listings log CRUD + daily reconciliation

**Remaining deployment tasks:**
1. Create `EcommerceListingsLog` and `EcommerceProductCatalog` tables on SQL Server
2. Install Python dependencies on EC2 (`python-amazon-sp-api`, `jinja2`)
3. Fill in marketplace credentials in `config.py` (Amazon SP-API, eBay OAuth, SMTP)
4. Set `APP_BASE_URL` in `config.py` to the EC2 public IP
5. Set up cron job: `0 7 * * * cd ~/inventory-chatbot && ~/chatbot-env/bin/python -m ecommerce.main`

---

### 1E. ERP Inventory Chatbot (New ERP)
**Status: Planned — Phase 1**

A second inventory chatbot instance (or extended mode within the existing chatbot) that queries the new ERP system (`gadgetkg_bwqa_main`) on MySQL. This gives management the same natural language Q&A experience they have today with `ReportingInventoryFlat`, but against the live ERP data — covering inventory, workshop pipeline, invoicing, and client records.

**Why a separate data source:**
- The current chatbot queries `ReportingInventoryFlat` on SQL Server (the legacy system)
- The new ERP runs on MySQL 5.7 (`gadgetkg_bwqa_main`) and uses a normalized schema with foreign key references across master tables
- During the migration period, both systems may run in parallel; after migration, the ERP becomes the single source of truth

**Key ERP tables the chatbot will query:**

| Table | Purpose |
|---|---|
| `wh_inv_master` | Core inventory — serial number, model, grade, status, bin location, cost, sales price |
| `web_model_master` | Model name/code lookup (joined via `model_id`) |
| `web_brand_master` | Brand name lookup (joined via `brand_id`) |
| `web_attribute_master` | Color, RAM, ROM lookups (joined via `color_id`, `ram_id`, `rom_id`) |
| `workshop_master` | Work order status and pipeline tracking (IQC → Repair → OQC) |
| `workshop_iqc` / `workshop_oqc` | Quality check status and dates |
| `workshop_device_repairs` | Repair status, engineer assignment, costs |
| `bw_sales_invoice_header` / `bw_sales_invoice_items` | Sales order and line item data |
| `master_clients` | Client/vendor details |
| `shipment_header` | Shipment tracking and status |

**Example queries this enables:**
- "How many devices are in Ready status by brand and model?"
- "What devices are currently in IQC or awaiting repair?"
- "Show me all inventory received from lot number X"
- "What is the total outward sales value of devices graded A?"
- "Which devices have been in the workshop for more than 48 hours?"
- "How many units were shipped to client Y this month?"

**Implementation approach:**
1. **Denormalized VIEW or flat table** — Create a MySQL VIEW (e.g., `vw_erp_inventory_flat`) that JOINs `wh_inv_master` with the model/brand/attribute master tables. This gives Claude a single, readable schema to generate SQL against — no complex multi-table JOINs in every query.

   ```sql
   CREATE VIEW vw_erp_inventory_flat AS
   SELECT wim.id AS inventory_id, wim.serial_number, wim.imei_1,
          wim.lot_num, wim.item_status, wim.bin_location,
          wim.inward_grade, wim.outward_grade,
          wim.inward_item_cost, wim.outward_sales_price,
          wm.model_name, wm.model_code,
          wb.brand_name,
          wa_color.attribute_value AS color,
          wa_ram.attribute_value AS ram,
          wa_rom.attribute_value AS storage,
          mc.vendor_name AS vendor,
          wim.cr_dateTime AS received_date,
          wim.final_order_id,
          wim.used_flag, wim.ewaste_flag
   FROM wh_inv_master wim
   LEFT JOIN web_model_master wm ON wim.model_id = wm.id
   LEFT JOIN web_brand_master wb ON wim.brand_id = wb.id
   LEFT JOIN web_attribute_master wa_color ON wim.color_id = wa_color.id
   LEFT JOIN web_attribute_master wa_ram ON wim.ram_id = wa_ram.id
   LEFT JOIN web_attribute_master wa_rom ON wim.rom_id = wa_rom.id
   LEFT JOIN master_clients mc ON wim.vendor_code = mc.id;
   ```

2. **MySQL connection from EC2** — Use `PyMySQL` or `mysql-connector-python` from the existing Flask app. The EC2 IP must be whitelisted on the MySQL host's firewall.

3. **Schema prompt for Claude** — Provide the VIEW column definitions (or the flat table schema) as context, same pattern as the existing chatbot. Claude generates MySQL-dialect SQL instead of T-SQL.

4. **Workshop pipeline view (optional)** — A second VIEW joining `workshop_master` → `workshop_iqc` → `workshop_device_repairs` → `workshop_oqc` for pipeline-specific questions.

**Dependencies:**
- MySQL host firewall must allow inbound connections from the Linux EC2
- ERP must be live and populated with data
- `PyMySQL` or `mysql-connector-python` installed in `~/chatbot-env`

**Relationship to Phase 1A:**
- Phase 1A (existing chatbot) continues to run against SQL Server during the migration period
- Phase 1E can run as a separate route/mode in the same Flask app (e.g., `/erp-chat`)
- Once the ERP migration is complete and validated, Phase 1E replaces 1A as the primary inventory chatbot

---

## Phase 2 — CRM & Sales Pipeline

### 2A. CRM Platform — HubSpot
**Status: Planned — Phase 2**
**Recommendation: HubSpot Free/Starter (not custom-built)**

**Why HubSpot over building in-house:**
- Building a CRM on EC2 introduces reliability risk — that instance already runs the chatbot and ecommerce pipeline
- A CRM requires contacts, deals, pipeline UI, notifications, email integration, and mobile access — weeks of custom development
- HubSpot Free covers all MVP requirements out of the box
- HubSpot's **Breeze AI** layer adds native AI features (deal scoring, email drafting, buyer intent) at no extra cost on paid tiers

**HubSpot Free covers:**
- Contact management (unlimited contacts)
- Deal pipeline and opportunity tracking
- Sales activity logging (calls, emails, meetings)
- Email integration (Gmail/Outlook)
- Mobile app
- Basic automation

**HubSpot Breeze AI (Starter and above) adds:**
- AI-generated email copy and follow-ups based on deal context
- Buyer intent scoring — flags companies showing purchase signals
- Automatic CRM data enrichment (fills in company size, industry, revenue)
- AI deal summaries — catch up on a deal in seconds

**ERP Integration Note:**
The new ERP (`gadgetkg_bwqa_main`) has its own `master_clients` table with vendor/client records, addresses, and billing info. HubSpot and the ERP serve different purposes — HubSpot manages the sales pipeline, the ERP manages operational client records. To keep them connected:
- Create a mapping table (or HubSpot custom property) that links each HubSpot Company/Contact ID to the corresponding `master_clients.id` in the ERP
- Plan this mapping from day one — retrofitting it later creates data integrity headaches
- The mapping enables Phase 2B (inventory visibility) and Phase 2C (warehouse handoff) to look up the correct ERP client when a HubSpot deal progresses

---

### 2B. Inventory Visibility Inside HubSpot
**Status: Planned — Phase 2**

Management should be able to view relevant inventory data directly on a HubSpot deal record — without switching to the chatbot.

**Data source:** The new ERP's MySQL database (`gadgetkg_bwqa_main`), specifically the `vw_erp_inventory_flat` VIEW created in Phase 1E (or equivalent denormalized query against `wh_inv_master` + master tables).

**Approach:**
- Use HubSpot's **Custom Properties** to sync key inventory metrics (e.g., available stock by model) from the ERP via a lightweight daily API sync script
- Or embed a filtered view of the chatbot as a **Custom Card** on deal records using HubSpot's CRM Card API
- The sync script connects to MySQL using `PyMySQL` (same driver as Phase 1E) and pushes aggregated stock counts to HubSpot via the HubSpot API

**What the sync provides on a deal record:**
- Available stock count by brand/model/grade relevant to the deal
- Current `item_status` breakdown (e.g., "85 Ready, 12 in IQC, 3 in Repair")
- Last refresh timestamp

**Technical notes:**
- The sync script runs on the Linux EC2, same as the chatbot — requires MySQL connectivity to the ERP host (firewall whitelisting from Phase 1E)
- Uses the HubSpot ↔ `master_clients.id` mapping established in Phase 2A to associate inventory with the correct HubSpot deal/company
- MySQL dialect — queries use `wh_inv_master.item_status` to determine availability (replaces the old `Version = '000'` filter from SQL Server)

This gives sales staff context like "we have 120 A-Grade iPhone 15s in Ready status" while they're working a deal — without leaving HubSpot.

---

### 2C. Warehouse Handoff Automation
**Status: Planned — Phase 2**

When a deal is marked "Closed Won" in HubSpot, an automated workflow triggers order creation directly in the ERP — so the warehouse team sees the order natively in their system.

**Flow:**
```
HubSpot Deal → "Closed Won"
        ↓
HubSpot Workflow triggers webhook
        ↓
Python script receives webhook on Linux EC2
        ↓
Script uses HubSpot ↔ master_clients.id mapping to resolve ERP client
        ↓
Creates records in ERP MySQL database:
  1. bw_sales_invoice_header  (order header — client, date, totals)
  2. bw_sales_invoice_items   (line items — serial, model, grade, pricing)
  3. Updates wh_inv_master.item_status → "Allocated" for each device
  4. Updates wh_inv_master.final_order_id with the new invoice ID
        ↓
Warehouse sees the order natively in the ERP UI
        ↓
(Optional) shipment_header record created when warehouse ships
```

**Why ERP-native instead of email/Slack:**
- The warehouse team will be working inside the ERP daily — orders should appear there, not in a separate notification channel
- Creating proper `bw_sales_invoice` records means the order is tracked, auditable, and feeds into the ERP's invoicing and shipment workflows
- `wh_inv_master.item_status` update prevents the same device from being sold twice (inventory reservation)

**Key implementation question:**
Does the ERP have an API layer, or will the webhook script write directly to MySQL? Writing directly is simpler but bypasses any application-level validation. If the ERP vendor provides an API, use that instead of raw SQL inserts.

**Dependencies:**
- Phase 2A (HubSpot live + client ID mapping in place)
- MySQL write access from Linux EC2 to the ERP database (or ERP API credentials)
- Agreement on which `item_status` values represent "Allocated" vs "Ready" vs "Shipped"

This eliminates manual handoff between sales and warehouse, and keeps the ERP as the single source of truth for order fulfillment.

---

## Phase 3 — Financial Intelligence (QuickBooks)

### 3A. QuickBooks Flat Table
**Status: Planned — Phase 3**

Using the QuickBooks Online API, extract key financial data into a flat SQL table on the existing SQL Server:

**Suggested columns:**
- Invoice number, customer name, amount, due date, status (paid/overdue/draft)
- Expense category, vendor, amount, date
- Revenue by month, project, customer
- Outstanding receivables, aged payables

Refresh: Daily (nightly at 2am via SQL Server Agent Job)

---

### 3B. QuickBooks AI Chatbot
**Status: Planned — Phase 3**

Extend the existing chatbot to answer financial questions:

- "What is our outstanding accounts receivable this month?"
- "Which customers have invoices overdue by more than 30 days?"
- "What were our total expenses in February by category?"
- "How does this month's revenue compare to last month?"

This uses the same Claude API + flat table pattern already built for inventory — no new infrastructure required.

---

### 3C. QuickBooks Financial Alerts
**Status: Planned — Phase 3**

Extend the alerts module (Phase 1C) with financial alert rules:

| Alert | Condition | Recipient | Channel |
|---|---|---|---|
| Overdue Invoice | Invoice overdue > 30 days | Finance / Management | Email |
| Large Expense | Single expense > $X threshold | Management | Slack |
| Low Cash | Cash balance drops below threshold | Management | Email |
| Payment Received | Invoice marked paid | Sales rep | Slack |

---

## Phase 4 — Unified AI Assistant

**Status: Planned — Phase 4**

Expand the single chatbot into a unified assistant that can answer questions across all three data domains:

| Domain | Data Source |
|---|---|
| Inventory | New ERP `vw_erp_inventory_flat` on MySQL (+ legacy SQL Server flat tables during migration) |
| CRM | HubSpot API or synced flat table |
| Financial | QuickBooks flat table |

**How it works:**
Claude receives the user's question along with a combined schema context for all three data sources. It determines which table(s) to query, generates the appropriate SQL or API call, and returns a unified answer.

**Example unified queries:**
- "How many A-Grade devices do we have available for the MobileShop deal closing this week?"
- "What is the total value of inventory assigned to customers with overdue invoices?"
- "Show me all Telus deals in the pipeline and the current Telus stock levels"

**Infrastructure:** Same Linux EC2, same Flask app — just an expanded schema prompt and additional database connections.

---

## Phase 5 — Meeting & Productivity Intelligence

### 5A. Claude Cowork for Meeting Management
**Status: Planned — Phase 5 (can start independently at any time)**

Claude Cowork is available on Pro, Team, and Enterprise Claude plans. It gives Claude access to a designated folder on your computer and lets it work autonomously on files within it.

**For management meetings:**
1. Drop meeting transcript or audio-to-text output into a shared folder (Google Drive)
2. Cowork automatically:
   - Summarizes key discussion points
   - Extracts action items with owners and deadlines
   - Drafts follow-up emails to attendees
   - Creates a structured meeting notes document

**Enterprise connectors available:** Google Drive, Gmail, DocuSign, FactSet

**This can be activated immediately** — it is independent of all other phases and just requires a Claude Pro or Team subscription.

---

### 5B. Additional Productivity Recommendations

**AI Email Drafting:**
- HubSpot Breeze AI (included with Starter) drafts sales emails based on deal context
- Claude Cowork can draft internal communications and reports from folder data

**AI Document Generation:**
- Claude Cowork can generate weekly inventory summary reports from the flat table exports
- Can produce customer-facing documents (quotes, proposals) from deal data

---

## Additional AI Recommendations

Beyond the core phases above, the following AI initiatives are worth considering as the business scales:

---

### A. AI-Powered Device Grading Assistance
**Recommendation: Explore in 2026**

Computer vision models can assist warehouse staff in grading devices more consistently. A tablet or phone camera captures the device, and an AI model suggests a grade based on visual condition. This reduces grader-to-grader inconsistency and speeds up throughput.

**Tools to evaluate:** Claude's vision capabilities (already in stack), Google Cloud Vision API, AWS Rekognition, or a fine-tuned open-source model

---

### B. Demand Forecasting
**Recommendation: Phase 3/4**

With historical inventory data (received date, grade, model, project, sell-through time) accumulating in the flat tables, a lightweight forecasting model can predict:
- Which models will be in high demand next month
- Optimal stock levels by grade and model
- Which devices are aging and at risk of margin erosion

**Tools:** Python (scikit-learn or Prophet), feeds directly into the existing SQL Server

---

### C. Automated Customer Communication (Post-CRM)
**Recommendation: Phase 2/3**

Once HubSpot is in place, use HubSpot Workflows + AI to automate routine customer touchpoints:
- Automated follow-up sequences for cold leads
- AI-generated check-in emails for deals that have gone quiet
- Post-sale satisfaction surveys triggered on deal close
- Shipment notifications triggered by warehouse handoff (Phase 2C)

---

### D. AI-Assisted Pricing
**Recommendation: Phase 4**

Combine inventory data (grade, model, age, volume) with market pricing data (via web scraping or a pricing API) to suggest optimal sell prices per device. Claude can be prompted to generate a pricing recommendation narrative for the sales team.

> **Note:** Phase 1D already implements competitive price scanning for ecommerce listings. This recommendation extends that capability to bulk/B2B pricing decisions beyond marketplace listings.

---

### E. Internal Knowledge Base Assistant
**Recommendation: Phase 3/4**

As processes, SOPs, and documents accumulate, a Claude-powered internal knowledge base assistant can answer staff questions like:
- "What is the grading criteria for a B-Grade device?"
- "What is the warehouse process for Telus returns?"
- "How do I create a new project in the system?"

**Tools:** Claude API with document retrieval (RAG), documents stored in Google Drive (via Cowork connector)

---

### F. Carrier/Client Portal (Long-Term)
**Recommendation: Long-term**

A client-facing portal where carriers (Telus, MobileShop, OSL) can log in and see their own inventory status, grading results, and shipment readiness — powered by the project-specific flat tables already being built in Phase 1B. This reduces inbound inquiry volume significantly.

---

## Infrastructure Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              AWS Cloud                                    │
│                                                                          │
│  ┌──────────────────────┐    ┌──────────────────────────┐               │
│  │  Windows EC2 (Legacy) │    │      Linux EC2            │               │
│  │  SQL Server           │    │      Ubuntu 24.04         │               │
│  │                       │    │      t2.medium             │               │
│  │  • ReportingInventory │◄───│  • Flask Chatbot (5000)  │               │
│  │    Flat (hourly)      │    │  • Ecommerce Pipeline     │               │
│  │  • Telus Flat (wkly)  │    │  • Inventory Alerts       │               │
│  │  • MobileShop (wkly)  │    │  • Gunicorn (prod)        │               │
│  │  • OSL Flat (wkly)    │    │  • Python 3.12            │               │
│  │  • QB Flat (daily)    │    │  • chatbot-env venv       │               │
│  │  • EcommListingsLog   │    │  • PyMySQL (ERP conn)     │               │
│  │  • EcommProductCat    │    │                           │               │
│  │  • SQL Agent Jobs     │    └──────────┬───────────────┘               │
│  │                       │               │                                │
│  │  (Phased out after    │               │                                │
│  │   ERP migration)      │               │                                │
│  └──────────────────────┘               │                                │
│                                         │                                │
└─────────────────────────────────────────┼────────────────────────────────┘
                                          │
          ┌───────────────────────────────┼──────────────────────────────┐
          │                               │                              │
          │  ┌──────────────────┐         │     External Services        │
          │  │  New ERP (MySQL)  │◄────────┤                              │
          │  │  gadgetkg_bwqa_   │         │                              │
          │  │  main             │         │                              │
          │  │                   │         │                              │
          │  │  • wh_inv_master  │         │                              │
          │  │  • workshop_*     │         │                              │
          │  │  • bw_sales_*     │         │                              │
          │  │  • master_clients │         │                              │
          │  │  • shipment_hdr   │         │                              │
          │  │  • vw_erp_inv_    │         │                              │
          │  │    flat (Phase 1E)│         │                              │
          │  └──────────────────┘         │                              │
          │                               │                              │
          │  ┌──────────────┐             │                              │
          │  │ Claude API   │◄────────────┘                              │
          │  │ (Anthropic)  │                                            │
          │  └──────────────┘                                            │
          │  ┌──────────────┐                                            │
          │  │ Claude Code  │  (Dev + Alerts)                            │
          │  └──────────────┘                                            │
          │  ┌──────────────┐                                            │
          │  │ Amazon SP-API│  (Phase 1D)                                │
          │  │ eBay APIs    │                                            │
          │  └──────────────┘                                            │
          │  ┌──────────────┐                                            │
          │  │  HubSpot     │  (Phase 2)                                 │
          │  │  CRM API     │                                            │
          │  └──────────────┘                                            │
          │  ┌──────────────┐                                            │
          │  │  QuickBooks  │  (Phase 3)                                 │
          │  │  Online API  │                                            │
          │  └──────────────┘                                            │
          │  ┌──────────────┐                                            │
          │  │  Slack API   │  (Alerts)                                  │
          │  │  Email/SMTP  │                                            │
          │  └──────────────┘                                            │
          └──────────────────────────────────────────────────────────────┘
```

---

## Phasing & Timeline Summary

| Phase | Initiative | Key Deliverable | Status | Dependencies |
|---|---|---|---|---|
| **Phase 1** | 1A — Chatbot (Legacy) | Live chatbot for inventory queries (SQL Server) | **Live** | None |
| **Phase 1** | 1A — Production setup | Gunicorn systemd service, chatbot always-on | **Pending** | None |
| **Phase 1** | 1B — Additional flat tables | Telus, MobileShop, OSL tables + weekly jobs | **Planned** | SQL Server access |
| **Phase 1** | 1C — Inventory alerts | Python alert scripts, Grading/Function Test alerts | **Planned** | Phase 1B flat tables |
| **Phase 1** | 1D — Ecommerce pipeline | Daily price scan, approval email, auto-listing | **Code Complete** | Credentials + DB tables (see Ecommerce_AI_Plan.md) |
| **Phase 1** | 1E — ERP Chatbot | Inventory chatbot querying new MySQL ERP | **Planned** | ERP live + MySQL connectivity from EC2 |
| **Phase 2** | 2A — HubSpot CRM | Contacts, deals, pipeline live + ERP client ID mapping | **Planned** | None (independent) |
| **Phase 2** | 2B — Inventory in HubSpot | Stock visibility on deal records (from ERP MySQL) | **Planned** | Phase 1E + 2A |
| **Phase 2** | 2C — Warehouse handoff | ERP-native order creation on Closed Won | **Planned** | Phase 2A + ERP MySQL write access |
| **Phase 3** | 3A — QB flat table | Financial data in SQL Server | **Planned** | QuickBooks API access |
| **Phase 3** | 3B — QB chatbot | Financial Q&A in chatbot | **Planned** | Phase 3A |
| **Phase 3** | 3C — QB alerts | Overdue invoice, cash flow alerts | **Planned** | Phase 3A + alerts module |
| **Phase 4** | Unified chatbot | Single assistant for inventory (ERP) + CRM + QB | **Planned** | Phases 1–3 |
| **Anytime** | Phase 5 — Claude Cowork | Meeting summaries, action items | **Planned** | Claude Pro/Team plan |

---

## Investment Overview

| Item | Type | Estimated Cost |
|---|---|---|
| Claude API (chatbot + listing copy + alerts) | Pay per use | ~$20–50/mo depending on query volume |
| Claude Pro/Team (Cowork) | Subscription | $20/user/mo (Pro) or $30/user/mo (Team) |
| Claude Code (Max plan) | Subscription | $100/mo (or usage-based) |
| HubSpot Free | Free | $0 (upgrade to Starter ~$20/mo for AI features) |
| QuickBooks Online | Existing subscription | No additional cost (API access included) |
| Linux EC2 (t2.medium) | Existing | Already running |
| SQL Server (Windows EC2) | Existing (Legacy) | Already running — phased out after ERP migration |
| New ERP (MySQL) | Existing / Migration | Hosted externally — no additional infrastructure cost |
| PyMySQL / mysql-connector-python | Free / open source | $0 |

---

*This document should be reviewed and updated at the start of each phase. For ecommerce pipeline details, see `Ecommerce_AI_Plan.md`. For technical setup, refer to the `README.md` in the `inventory-chatbot` repository.*

---

**Sources & Further Reading:**
- [Claude Code — Anthropic](https://docs.anthropic.com/en/docs/claude-code)
- [Claude Cowork — Anthropic](https://claude.com/blog/cowork-research-preview)
- [Get Started with Cowork — Claude Help Center](https://support.claude.com/en/articles/13345190-get-started-with-cowork)
- [HubSpot AI CRM](https://www.hubspot.com/products/crm/ai-crm)
- [HubSpot Breeze AI Guide](https://www.eesel.ai/blog/hubspot-breeze-ai-capabilities)
- [QuickBooks Online API Integration Guide](https://www.getknit.dev/blog/quickbooks-online-api-integration-guide-in-depth)
