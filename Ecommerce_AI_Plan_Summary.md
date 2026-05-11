# Ecommerce AI Plan — Summary

**Status:** Phase 1D-ii (Preview & Approval Flow)
**Updated:** April 2026

---

## Goal

Automate the end-to-end ecommerce listing workflow: scan inventory flagged for ecommerce, research competitive prices across four Canadian marketplaces, recommend the best platform and price per SKU, and — upon human approval — generate and post listings automatically.

---

## Target Marketplaces

1. **Amazon Canada**
2. **eBay Canada**
3. **Best Buy Marketplace Canada**
4. **Reebelo Canada**

All four are scanned from day one using Apify cloud actors for price intelligence.

---

## How It Works

1. **Weekly scan** (Monday 6 AM EST) queries inventory for unlisted ecommerce SKUs (~200 SKUs).
2. **Apify cloud actors** scrape competitor prices across all four marketplaces with automatic proxy rotation.
3. **Deterministic pricing algorithm** picks the marketplace with the highest floor price — no AI needed for pricing.
4. **Recommendations** are persisted to SQL Server and displayed on a web dashboard (`/ecommerce/dashboard`).
5. **Human approver** reviews each SKU's recommended marketplace and price, then approves or rejects inline.
6. **On approval**, Claude AI generates listing copy (title, description, bullet points) displayed in a preview modal for manual copy-paste to the marketplace.

---

## Phased Rollout

| Phase | What It Delivers |
|---|---|
| **1D-i** (Complete) | Weekly price scanning + web dashboard with recommendations across all 4 marketplaces. |
| **1D-ii** (Current) | Approval flow + Claude-generated listing copy in a preview modal with copy-to-clipboard. Human lists manually. |
| **1D-iii** (Future) | Auto-listing via Amazon SP-API and eBay Inventory API — approve button posts directly to the marketplace. |

The phased approach builds confidence in pricing accuracy and listing quality before granting the system direct marketplace API access.

---

## Key Design Decisions

- **Apify over Octoparse** — Full API access on all plans ($29/mo vs $249/mo for Octoparse API access).
- **Claude API for listing copy** — Already integrated in the project; no need for a second AI provider.
- **Deterministic pricing** — Simple `max(floor prices)` algorithm; no LLM needed for price selection.
- **Weekly cadence** — Used device prices don't change hourly; weekly reduces scraping detection risk.
- **First page only** — Lightweight scraping jobs (~600 page loads/week total).

---

## Infrastructure

No new infrastructure required. Runs entirely on the existing Linux EC2, SQL Server, and Apify Cloud.

| Component | Role |
|---|---|
| Linux EC2 | Cron job + Flask dashboard |
| SQL Server | Inventory data, pricing batches, listings log |
| Apify Cloud | Remote scraping with proxy rotation |
| Claude API | Listing copy generation |

---

## Estimated Costs

| Item | Cost |
|---|---|
| Apify (Starter plan) | ~$29/month |
| Claude API (listing copy) | Minimal (~100 calls/week on approved SKUs only) |
| AWS S3 (eBay images, if needed) | ~$1-2/month |

---

*Full technical details in [Ecommerce_AI_Plan.md](Ecommerce_AI_Plan.md).*
