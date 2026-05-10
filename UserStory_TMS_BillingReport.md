# User Story: TMS Billing Report Generator

## 1B.6 — TMS Billing Report Web Page

**As a** manager,
**I want** a web page with a "Generate Billing Report" button that produces the TMS monthly billing summary from the `ReportingInventoryFlat_TMS` flat table,
**so that** I no longer need to manually calculate billing line items in Excel each month.

**Depends on:** 1B.5 (TMS Flat Table must be built and populated first)

---

## Billing Report Structure

The report mirrors the existing TMS Billing Excel "Summary" tab. Each line item counts devices from the flat table where a specific process timestamp falls within the selected billing month, filtered by `Receipt_Type`.

### Section: In Warranty Rx

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'In Warranty'` | $2.75 |
| Handle Repair at MSC | Count of `MSC_Repair_Handling_Created` in billing month | $2.75 |
| Return Device to Store | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type = 'In Warranty'` | $2.75 |

### Section: Out of Warranty

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Repair | Count of `Repair_Fee` where `Lab_Billing_Created` in billing month. **Fee = SUM of `Repair_Fee`** (not fixed) | Variable |

### Section: DOA

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'DOA'` | $3.30 |
| Create RMA Where applicable | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type = 'DOA'` | $5.23 |
| Data Wipe | Count of `QC_Assessment_Created` in billing month, `Receipt_Type = 'DOA'` | $3.85 |

### Section: Buyer's Remorse

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'Buyer''s Remorse'` | $3.30 |
| QC | Count of `QC_Assessment_Created` in billing month, `Receipt_Type = 'Buyer''s Remorse'` | $3.85 |

### Section: Inventory

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'Inventory'` | $3.85 |
| Ship | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type = 'Inventory'` | $2.75 |

### Section: Loaner Processing

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'Loaner'` | $2.75 |
| Data Wipe / QC | Count of `QC_Assessment_Created` in billing month, `Receipt_Type = 'Loaner'` | $3.85 |
| Ship | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type = 'Loaner'` | $3.30 |

### Section: Demo

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receive | Count of `ReceiveDate` in billing month, `Receipt_Type = 'Demo'` | $2.75 |
| Wipe and QC | Count of `QC_Assessment_Created` in billing month, `Receipt_Type = 'Demo'` | $3.85 |
| Ship | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type = 'Demo'` | $1.65 |

### Section: Accessories

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | $1.38 |

### Section: Discrepancies

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Per Item | Count of `Discrepancy_Created` in billing month | $7.70 |

### Section: RQ4 SKU Transfer

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Transactions | Count of `SKU_Transfer_Created` in billing month | $3.30 |

### Section: RQ4 SKU Change

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Transactions | Count of `RQ4_SKU_Change_Created` in billing month | $1.10 |

### Section: Open Box Transfer

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Package as per requirements | Count of `Shipping_TMS_Created` in billing month, `Receipt_Type IN ('Buyer''s Remorse', 'Rejected')` | $3.30 |

### Section: RMA

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Receiving | Count of `ReceiveDate` in billing month, `Receipt_Type = 'RMA'` | $3.85 |
| Shipping to store | No formula in spreadsheet — manual entry | $2.75 |
| Shipping to carriers | No formula in spreadsheet — manual entry | $1.65 |

### Section: Kitting

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Accessories Added | No formula in spreadsheet — manual entry | $11.00 |

### Section: Subsidy Check

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Subsidy Check | Count of `Subsidy_Created` in billing month | $1.10 |

### Section: Bridge Fulfillment Service

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | $28.60 |

### Section: Accessories Receive (Fulfillment)

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | $0.55 |

### Section: Sim Card Receive (Fulfillment)

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | $0.11 |

### Section: Android Device Enrollment

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| Other (non-Samsung) | Count of `Device_Enrollment_Created` in billing month, `ManufacturerVerb != 'Samsung'` | $6.60 |
| Samsung | Count of `Subsidy_Created` in billing month, `ManufacturerVerb = 'Samsung'` | $7.70 |

### Section: TMS Inventory Tasks Management

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | TBD |

### Section: Buffing Services

| Line Item | Units/Hours Logic | Fee |
|---|---|---|
| (No formula in spreadsheet) | Manual entry | TBD |

### Calculations

- **Charge (Column D)** = Units x Fee (except "Out of Warranty Repair" where Charge = SUM of `Repair_Fee`)
- **Section Total (Column E)** = SUM of Charge for all line items in the section
- **Grand Total** = SUM of all Section Totals

---

## Steps to Accomplish

### 1. Define the billing config as structured data

Create a Python data structure (list of sections, each with line items) that encodes:
- Section name
- Line item name
- Which flat table column to COUNT
- Receipt_Type filter (if any)
- Manufacturer filter (if any)
- Fixed fee per unit
- Special rules (e.g., "Out of Warranty Repair" uses SUM of `Repair_Fee` instead of count x fee)

This config makes it easy to update fees or add line items without changing query logic.

### 2. Create the billing query module

A new module (e.g., `billing/tms.py`) that:
- Accepts a billing month (year + month)
- Queries `ReportingInventoryFlat_TMS` for each line item's count
- Applies the fee x count calculation
- Computes section totals and grand total
- Returns a structured result (sections -> line items -> units, fee, charge)

### 3. Create the Flask Blueprint and route

A new Blueprint (e.g., `billing/routes.py`) registered in `app.py`:
- `GET /billing/tms` — renders the billing page with a month selector and "Generate" button
- `POST /billing/tms/generate` — runs the queries for the selected month, returns the billing summary as JSON
- The page renders the report in a table matching the Excel Summary layout

### 4. Build the frontend

An HTML page (Jinja2 template or inline HTML served by the Blueprint) with:
- Month/year picker (default: previous month)
- "Generate Billing Report" button
- Results table rendered via JavaScript after the AJAX call
- Section headers, line items, fees, charges, section totals, and grand total
- Export option (e.g., "Download as Excel" or "Copy to clipboard")

### 5. Handle manual-entry line items

Several line items have no formula in the spreadsheet (Accessories, Kitting, Fulfillment, Buffing, RMA Shipping). Options:
- Make these editable fields on the report page so the user can fill them in manually
- Or leave them as $0.00 with a note, to be filled in post-export
- **Decision needed from user**

### 6. Deploy

- Register the new Blueprint in `app.py`
- Ensure the route is accessible on the EC2 instance
- Test with March 2026 data and compare against the existing Excel report

---

## Acceptance Criteria

- [ ] Web page at `/billing/tms` with month selector and "Generate" button
- [ ] Clicking "Generate" queries `ReportingInventoryFlat_TMS` and displays the full billing summary
- [ ] All automatable line items (19 of ~26) match the Excel formulas exactly
- [ ] Manual-entry line items are clearly marked (approach decided in Step 5)
- [ ] Section totals and grand total calculate correctly
- [ ] Fee amounts are configurable (not hardcoded in SQL)
- [ ] Report can be exported or copied for delivery to TMS
- [ ] March 2026 output validated against the existing Excel billing report

---

## Open Questions

1. **Manual line items** — Should Accessories, Kitting, Fulfillment, Buffing, and RMA Shipping rows be editable on the web page, or handled outside this tool?
2. **RMA "Shipping to store"** (Row 40) — No formula was provided. What is the logic for this count?
3. **RMA "Shipping to carriers"** (Row 41) — No formula was provided. What is the logic for this count?
4. **Fee updates** — How often do fees change? Should there be an admin UI for updating fees, or is a config file sufficient?
