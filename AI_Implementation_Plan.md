# AI Implementation Plan
### Internal Document — Management Team

**Prepared:** March 2026
**Status:** Active — Phase 1 In Progress

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

The foundation has already been laid: a live AI chatbot is operational for inventory queries. This plan builds on that foundation systematically, ending with a unified AI assistant that can answer questions across inventory, CRM, and financial data simultaneously.

**Core Principles:**
- Build on existing infrastructure where possible (SQL Server, EC2)
- Prefer proven off-the-shelf tools over custom builds for non-core systems
- Each phase delivers standalone value before the next begins
- Security and access control are non-negotiable at every phase

---

## Current State

### What We Have Today

| System | Status | Details |
|---|---|---|
| Inventory AI Chatbot | **Live** | Flask app on Linux EC2, powered by Claude API, queries `ReportingInventoryFlat` |
| Flat Reporting Table | **Live** | `ReportingInventoryFlat` — ~41,277 in-stock devices, refreshes hourly |
| SQL Server | **Live** | Windows EC2, hosts all inventory data |
| Linux EC2 | **Live** | Ubuntu 24.04, t2.micro, hosts chatbot |
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
| **Anthropic Claude API** | Text-to-SQL, answer formatting, all AI generation | Pay per token |
| **Claude Cowork** | Meeting summaries, action items, document generation | Included in Pro/Team/Enterprise |
| **OpenClaw** | Autonomous data alerts, Slack/Email/WhatsApp notifications | Open source, self-hosted |
| **HubSpot (Free/Starter)** | CRM — contacts, deals, pipeline | Free tier available |
| **Python Flask** | Chatbot backend | Free / open source |
| **SQL Server Agent** | Scheduled flat table refreshes | Already licensed |

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

### 1C. Inventory Data Alerts via OpenClaw
**Status: Planned — Phase 1**

Deploy OpenClaw on the existing Linux EC2 to monitor the flat table and send automated alerts.

**How it works:**
1. OpenClaw connects to SQL Server via the existing ODBC Driver 18 connection
2. Scheduled AgentSkill runs SQL queries on a defined interval (e.g., every 2 hours)
3. If a condition is met, OpenClaw sends an alert via Email, Slack, or WhatsApp

**Initial Alert Rules:**

| Alert | Condition | Recipient | Channel |
|---|---|---|---|
| Grading Backlog | Device in Grading > 48 hours | Warehouse Manager | Email + Slack |
| Telus Grading Backlog | Telus device in Grading > 48 hours | Warehouse Manager | WhatsApp |
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

> **Security note:** OpenClaw will be granted read-only database access and run under a limited Linux user account — not root.

---

## Phase 2 — CRM & Sales Pipeline

### 2A. CRM Platform — HubSpot
**Status: Planned — Phase 2**
**Recommendation: HubSpot Free/Starter (not custom-built)**

**Why HubSpot over building in-house:**
- Building a CRM on a t2.micro EC2 introduces reliability risk — that instance already runs the chatbot
- A CRM requires contacts, deals, pipeline UI, notifications, email integration, and mobile access — weeks of custom development
- HubSpot Free covers all MVP requirements out of the box
- HubSpot's **Breeze AI** layer adds native AI features (deal scoring, email drafting, buyer intent) at no extra cost on paid tiers

**HubSpot Free covers:**
- ✅ Contact management (unlimited contacts)
- ✅ Deal pipeline and opportunity tracking
- ✅ Sales activity logging (calls, emails, meetings)
- ✅ Email integration (Gmail/Outlook)
- ✅ Mobile app
- ✅ Basic automation

**HubSpot Breeze AI (Starter and above) adds:**
- AI-generated email copy and follow-ups based on deal context
- Buyer intent scoring — flags companies showing purchase signals
- Automatic CRM data enrichment (fills in company size, industry, revenue)
- AI deal summaries — catch up on a deal in seconds

---

### 2B. Inventory Visibility Inside HubSpot
**Status: Planned — Phase 2**

Management should be able to view relevant inventory data directly on a HubSpot deal record — without switching to the chatbot.

**Approach:**
- Use HubSpot's **Custom Properties** to sync key inventory metrics (e.g., available stock by model) from the flat table via a lightweight daily API sync script
- Or embed a filtered view of the chatbot as a **Custom Card** on deal records using HubSpot's CRM Card API

This gives sales staff context like "we have 120 A-Grade iPhone 15s available" while they're working a deal — without leaving HubSpot.

---

### 2C. Warehouse Handoff Automation
**Status: Planned — Phase 2**

When a deal is marked "Closed Won" in HubSpot, an automated workflow triggers a warehouse packing/processing notification.

**Flow:**
```
HubSpot Deal → "Closed Won"
        ↓
HubSpot Workflow triggers webhook
        ↓
Python script receives webhook on Linux EC2
        ↓
Inserts order into SQL Server (or sends formatted email/Slack to warehouse)
        ↓
Warehouse receives packing instructions
```

This eliminates manual handoff between sales and warehouse.

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

### 3C. QuickBooks Financial Alerts via OpenClaw
**Status: Planned — Phase 3**

Extend the existing OpenClaw setup with financial alert rules:

| Alert | Condition | Recipient | Channel |
|---|---|---|---|
| Overdue Invoice | Invoice overdue > 30 days | Finance / Management | Email |
| Large Expense | Single expense > $X threshold | Management | Slack |
| Low Cash | Cash balance drops below threshold | Management | Email + WhatsApp |
| Payment Received | Invoice marked paid | Sales rep | Slack |

---

## Phase 4 — Unified AI Assistant

**Status: Planned — Phase 4**

Expand the single chatbot into a unified assistant that can answer questions across all three data domains:

| Domain | Data Source |
|---|---|
| Inventory | `ReportingInventoryFlat` (+ Telus, MobileShop, OSL tables) |
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

Claude Cowork is available now on Pro, Team, and Enterprise Claude plans. It gives Claude access to a designated folder on your computer and lets it work autonomously on files within it.

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

**Tools to evaluate:** Google Cloud Vision API, AWS Rekognition, or a fine-tuned open-source model

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
┌─────────────────────────────────────────────────────────────┐
│                        AWS Cloud                            │
│                                                             │
│  ┌──────────────────────┐    ┌──────────────────────────┐  │
│  │   Windows EC2         │    │      Linux EC2            │  │
│  │   SQL Server          │    │      Ubuntu 24.04         │  │
│  │                       │    │      t2.micro             │  │
│  │  • ReportingInventory │◄───│  • Flask Chatbot (5000)  │  │
│  │    Flat (hourly)      │    │  • OpenClaw Alerts        │  │
│  │  • Telus Flat (wkly)  │    │  • Gunicorn (prod)        │  │
│  │  • MobileShop (wkly)  │    │  • Python 3.12            │  │
│  │  • OSL Flat (wkly)    │    │  • chatbot-env venv       │  │
│  │  • QB Flat (daily)    │    │                           │  │
│  │  • SQL Agent Jobs     │    └──────────┬───────────────┘  │
│  └──────────────────────┘               │                   │
│                                         │                   │
└─────────────────────────────────────────┼───────────────────┘
                                          │
                    ┌─────────────────────┼──────────────────┐
                    │                     │  External APIs    │
                    │  ┌──────────────┐   │                  │
                    │  │ Claude API   │◄──┘                  │
                    │  │ (Anthropic)  │                       │
                    │  └──────────────┘                       │
                    │  ┌──────────────┐                       │
                    │  │  HubSpot     │  (Phase 2)            │
                    │  │  CRM API     │                       │
                    │  └──────────────┘                       │
                    │  ┌──────────────┐                       │
                    │  │  QuickBooks  │  (Phase 3)            │
                    │  │  Online API  │                       │
                    │  └──────────────┘                       │
                    │  ┌──────────────┐                       │
                    │  │  Slack API   │  (OpenClaw alerts)    │
                    │  │  Email/WA    │                       │
                    │  └──────────────┘                       │
                    └───────────────────────────────────────-─┘
```

---

## Phasing & Timeline Summary

| Phase | Initiative | Key Deliverable | Dependencies |
|---|---|---|---|
| **Now** | 1A — Chatbot production setup | Gunicorn systemd service, chatbot always-on | None |
| **Phase 1** | 1B — Additional flat tables | Telus, MobileShop, OSL tables + weekly jobs | SQL Server access |
| **Phase 1** | 1C — Inventory alerts | OpenClaw on EC2, Grading/Function Test alerts | Phase 1B flat tables |
| **Phase 2** | 2A — HubSpot CRM | Contacts, deals, pipeline live | None (independent) |
| **Phase 2** | 2B — Inventory in HubSpot | Stock visibility on deal records | Phase 1A + 2A |
| **Phase 2** | 2C — Warehouse handoff | Automated packing trigger on Closed Won | Phase 2A |
| **Phase 3** | 3A — QB flat table | Financial data in SQL Server | QuickBooks API access |
| **Phase 3** | 3B — QB chatbot | Financial Q&A in chatbot | Phase 3A |
| **Phase 3** | 3C — QB alerts | Overdue invoice, cash flow alerts | Phase 3A + OpenClaw |
| **Phase 4** | Unified chatbot | Single assistant for inventory + CRM + QB | Phases 1–3 |
| **Anytime** | Phase 5 — Claude Cowork | Meeting summaries, action items | Claude Pro/Team plan |

---

## Investment Overview

| Item | Type | Estimated Cost |
|---|---|---|
| Claude API (chatbot + alerts) | Pay per use | ~$20–50/mo depending on query volume |
| Claude Pro/Team (Cowork) | Subscription | $20/user/mo (Pro) or $30/user/mo (Team) |
| HubSpot Free | Free | $0 (upgrade to Starter ~$20/mo for AI features) |
| OpenClaw | Open source, self-hosted | $0 (runs on existing EC2) |
| QuickBooks Online | Existing subscription | No additional cost (API access included) |
| Linux EC2 (t2.micro) | Existing | Already running |
| SQL Server (Windows EC2) | Existing | Already running |

> **Note:** As query volume and alert frequency grow, the Linux EC2 t2.micro may need to be upgraded to a t3.small or t3.medium. This is a low-cost change (~$5–10/mo difference) and can be done with zero downtime via AWS instance type change.

---

*This document should be reviewed and updated at the start of each phase. For technical questions, refer to the `README.md` in the `inventory-chatbot` repository.*

---

**Sources & Further Reading:**
- [Claude Cowork — Anthropic](https://claude.com/blog/cowork-research-preview)
- [Get Started with Cowork — Claude Help Center](https://support.claude.com/en/articles/13345190-get-started-with-cowork)
- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [OpenClaw Business Use Cases — Contabo](https://contabo.com/blog/openclaw-use-cases-for-business-in-2026/)
- [OpenClaw SQL/Database Integration — Stormap](https://stormap.ai/post/how-to-connect-openclaw-to-local-databases-with-mcp-in-2026)
- [HubSpot AI CRM](https://www.hubspot.com/products/crm/ai-crm)
- [HubSpot Breeze AI Guide](https://www.eesel.ai/blog/hubspot-breeze-ai-capabilities)
- [QuickBooks Online API Integration Guide](https://www.getknit.dev/blog/quickbooks-online-api-integration-guide-in-depth)
- [OpenClaw vs Eigent vs Claude Cowork — AI Journal](https://aijourn.com/openclaw-vs-eigent-vs-claude-cowork-the-best-open-source-ai-cowork-platform-in-2026/)
