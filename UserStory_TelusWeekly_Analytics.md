# User Story: Telus Weekly Report & Analytics Module

## 2A — Home Page + Analytics Module (Telus Weekly Repair Assessment)

**As a** Telus Weekly team member,
**I want** a web page where I enter a ProjectTag and instantly get the full Repair & Resell pricing report with recommendations,
**so that** I no longer need to manually run the stored procedure, paste data into Excel, and rely on VLOOKUP formulas and macros to price devices.

**Depends on:** Stored procedure `GetReport_RepairAssessment_ByProjectTag` (already deployed on SQL Server)

---

## Home Page

After login, users now land on `/home` — a 3-card navigation hub:

| Card | Route | Description |
|------|-------|-------------|
| Inventory Chatbot | `/chat` | Ask questions about current inventory |
| Ecommerce | `/ecommerce/dashboard` | Pricing dashboard & marketplace listings |
| Analytics | `/analytics/` | Telus Weekly & repair assessment reports |

---

## Telus Weekly Report — What It Replaces

The existing workflow uses two Excel files:

1. **TW1626 Demo Pricing.xlsx** — "Data" tab (raw export from Brain), "Models" tab (model pivot), "Repair & Resell" tab (pricing + recommendations with blank formula columns)
2. **telus pricing Demo api.xlsm** — "TW" tab (formulas that fill blank columns via VLOOKUP), "DO NOT EDIT" tab (831-model pricing master), "Price Review" tab (macro-driven price editor)

The web app replaces all of this: stored proc → Python pricing engine → browser report + Excel export.

---

## Report Structure

### Input

- **ProjectTag** (required) — e.g., `TW1626`
- **Client Name** (optional) — filters by client

Devices always have `Version = '000'` and `ProjectName = 'Telus Weekly'`.

### Stored Procedure Output (20 columns)

| Column | Source | Type |
|--------|--------|------|
| ESN | ReceiveDetail.ESN | Device serial |
| Client | Client.CompanyName | Client name |
| ProjectName | Project.Name | Project |
| Vendor | Question = 'Vendor' | rdi.Value |
| ManufacturerVerb | Option (ManufacturerID) | Brand |
| ModelVerb | Option (ModelID) | Model (includes storage, e.g., "iPhone 14 Pro Max 128 GB") |
| Memory | Question = 'Memory' | Storage |
| Conditions | Question = 'Conditions' | Defective / FRP / Functional / NYT |
| Defects_1, _2, _3 | Questions = 'Defects 1/2/3' | Damage types |
| QC_Notes | Question = 'QC Notes' | Assessment notes |
| Received_Grade | Question = 'Received Grade' | A / B / C |
| T_Level_Cost | Question = 'T Level Cost' | Repair labour (NVARCHAR) |
| T_Part_Cost | Question = 'T Part Cost' | Repair parts (NVARCHAR) |
| Post-Repair_Grade | Question = 'Post-Repair Grade' | Grade after repair |
| Grade_Improvement | Question = 'Grade Improvement' | Yes / No |
| T_Level_Improved_Cos | Question = 'T Level Improved Cos' | Improvement labour (NVARCHAR) |
| T_Part_Improved_Cost | Question = 'T Part Improved Cost' | Improvement parts (NVARCHAR) |
| Post_Improved_Grade | Question = 'Post Improved Grade' | Grade after improvement |

### Computed Columns (Python pricing engine — replaces Excel VLOOKUP formulas)

Each device is looked up in the `TelusWeeklyPricingMaster` table by `ModelVerb`.

| Column | Excel Equivalent | Logic |
|--------|-----------------|-------|
| Unassessed Price | Col L | If device_type = "Modem" → $0; If Conditions = "Defective" → defective price; If Conditions = "FRP" → FRP price (or N/A if $0); Else → Grade C price |
| Assessed Price | Col N | If Modem → Grade C; If Defective → defective; If FRP → FRP; Else → price by Received Grade (A/B/C) |
| Total Repair Cost | Col U | T_Level_Cost + T_Part_Cost |
| Price After Repair | Col W | Price by Post-Repair Grade (A/B/C lookup) |
| Upside | Col X | If Defective/FRP → Price After Repair − Total Repair Cost − Unassessed Price; Else → N/A |
| Total Improvement Cost | Col AB | T_Level_Improved_Cos + T_Part_Improved_Cost |
| Total Repair + Improvement | Col AD | Total Repair Cost + Total Improvement Cost |
| Price After Improvement | Col AE | If Post Improved Grade = "A" → Grade A price; Else → $0 |
| Improvement Upside | Col AF | If Grade Improvement = "Yes" → Price After Improvement − Total Repair+Improvement − Unassessed Price; Else → N/A |
| Recommendation | Col AG | See decision logic below |
| Lot Value | Col AH | Best recovery value based on condition and profitability |

### Recommendation Decision Logic (Col AG)

| Condition | Rule |
|-----------|------|
| Defective or FRP | If Upside > $0 → **Sell After Repair**; Else → **Sell As Is** |
| Functional | If Improvement Upside > $0 → **Sell After Grade Improvement**; Else → **Sell As Functional** |
| NYT (Not Yet Tested) | Always → **Sell As Is** |

### Lot Value Logic (Col AH)

| Condition | Rule |
|-----------|------|
| Defective or FRP | If Upside > $0 → Price After Repair − Total Repair Cost; Else → Unassessed Price |
| Functional | If Improvement Upside > $0 → Price After Improvement − Total Repair+Improvement; Else → Assessed Price |
| NYT | Unassessed Price |

### Summary Bar

- Total devices
- Total lot value
- Conditions breakdown (Defective, FRP, Functional, NYT counts)
- Recommendation breakdown (Sell After Repair, Sell As Is, etc. counts)

---

## Pricing Master Table

Replaces the Excel "DO NOT EDIT" sheet (831 models).

### Database Table: `TelusWeeklyPricingMaster`

```sql
CREATE TABLE dbo.TelusWeeklyPricingMaster (
    ID              INT IDENTITY(1,1) PRIMARY KEY,
    Model           NVARCHAR(200) NOT NULL UNIQUE,
    GradeA_Price    DECIMAL(10,2) NOT NULL DEFAULT 0,
    GradeB_Price    DECIMAL(10,2) NOT NULL DEFAULT 0,
    GradeC_Price    DECIMAL(10,2) NOT NULL DEFAULT 0,
    Defective_Price DECIMAL(10,2) NOT NULL DEFAULT 0,
    FRP_Price       DECIMAL(10,2) NOT NULL DEFAULT 0,
    DeviceType      NVARCHAR(50)  NOT NULL DEFAULT 'Phone',
    UpdatedAt       DATETIME      NOT NULL DEFAULT GETDATE(),
    UpdatedBy       NVARCHAR(100) NULL
);
```

### Initial Data Load

One-time import from the existing Excel "DO NOT EDIT" sheet:

```bash
python -m analytics.import_pricing '/path/to/telus pricing Demo api.xlsm'
```

Reads columns: Model (D), Grade A (E), Grade B (F), Grade C (G), Defective (H), FRP (I), Device Type (L).

---

## Price Review Page

Replaces the Excel "Price Review" tab and macros. Available at `/analytics/price-review`.

| Feature | Description |
|---------|-------------|
| Search/Filter | Type to filter models by name |
| Inline Editing | All price cells are editable number inputs |
| Save Changes | AJAX POST — bulk updates changed rows, no page reload |
| Add New Model | Expandable row to insert a new model with prices |
| Device Type | Dropdown: Phone, Tablet, Watch, Modem |
| Audit Trail | `UpdatedAt` and `UpdatedBy` tracked on every save |

---

## Module Structure

```
analytics/
├── __init__.py            # Package init
├── config.py              # Re-exports root DB config (DB_SERVER, DB_NAME, etc.)
├── db.py                  # Stored proc call + TelusWeeklyPricingMaster CRUD
├── pricing.py             # Pure-Python pricing engine (replaces all Excel formulas)
├── routes.py              # Flask Blueprint at /analytics (7 routes)
├── templates.py           # Jinja2 HTML templates (index, TW form, report, price review)
└── import_pricing.py      # One-time script to seed pricing master from Excel
```

---

## Routes

| Route | Method | Purpose |
|-------|--------|---------|
| `/analytics/` | GET | Analytics index — list of available reports |
| `/analytics/telus-weekly` | GET | ProjectTag input form |
| `/analytics/telus-weekly/report` | POST | Run stored proc → apply pricing → render report |
| `/analytics/telus-weekly/export` | POST | Same pipeline → download as Excel (.xlsx) |
| `/analytics/price-review` | GET | View/edit pricing master table |
| `/analytics/price-review/save` | POST | AJAX: bulk update prices |
| `/analytics/price-review/add` | POST | AJAX: insert new model |

All routes are session-protected (require login).

---

## Data Flow

```
User enters ProjectTag on form
        │
        ▼
POST /analytics/telus-weekly/report
        │
        ▼
db.call_repair_assessment(project_tag)
  → EXEC GetReport_RepairAssessment_ByProjectTag @ProjectTag=?, @ClientName=?
  → Returns: list of device dicts (20 columns each)
        │
        ▼
db.get_pricing_map()
  → SELECT * FROM TelusWeeklyPricingMaster
  → Returns: {model_name: {grade_a, grade_b, grade_c, defective, frp, device_type}}
        │
        ▼
pricing.compute_report(devices, pricing_map)
  → For each device: lookup model, apply formulas, compute recommendation
  → Returns: enriched rows (31 columns) + summary stats
        │
        ▼
templates.render_telus_weekly_report(...)
  → Full HTML table with summary bar, color-coded recommendations
```

---

## Excel Export

The "Export to Excel" button generates a `.xlsx` file with 3 sheets:

| Sheet | Content |
|-------|---------|
| Repair & Resell | Full report — all 28 columns (stored proc + computed), styled headers |
| Models | Pivot of model names with device counts |
| Summary | Total devices, total lot value, recommendation breakdown, conditions breakdown |

Filename format: `TW_{ProjectTag}_{YYYYMMDD}.xlsx`

---

## Steps to Accomplish

### 1. Create `TelusWeeklyPricingMaster` table on SQL Server

Run the CREATE TABLE DDL above on the Bridge database.

### 2. Import pricing data from Excel

Run the import script to load the 831 models from the existing "DO NOT EDIT" sheet:

```bash
cd ~/inventory-chatbot
~/chatbot-env/bin/python -m analytics.import_pricing '/path/to/telus pricing Demo api.xlsm'
```

### 3. Install openpyxl dependency

```bash
~/chatbot-env/bin/pip install openpyxl
```

### 4. Deploy code

The following files have already been created:
- `analytics/__init__.py`, `config.py`, `db.py`, `pricing.py`, `routes.py`, `templates.py`, `import_pricing.py`
- `templates/home.html`
- Modified `app.py` (analytics blueprint registered, `/home` route added, login redirects to `/home`)

### 5. Validate

- Run a report with a known ProjectTag (e.g., `TW1626`)
- Compare computed prices against the existing Excel output for the same ProjectTag
- Verify recommendation logic matches Excel formulas
- Test Price Review: edit a price → save → re-run report → confirm updated price reflects
- Test Excel export: download → open in Excel → verify data matches browser view

---

## Key Technical Notes

1. **Model name matching** — `ModelVerb` from the stored proc matches `Model` in the pricing master. Both originate from Brain's `Option.OptionText`. Lookups use `LTRIM(RTRIM())` on the DB side and case-insensitive matching in Python. Devices with no match are flagged "Model not in pricing master".

2. **NVARCHAR cost columns** — `T_Level_Cost`, `T_Part_Cost`, `T_Level_Improved_Cos`, `T_Part_Improved_Cost` are returned as strings from `rdi.[Value]`. The `_safe_float()` helper handles None, empty, and non-numeric values gracefully.

3. **Modem exception** — The "Modem" check uses `DeviceType` from the pricing master (not the `Conditions` field). Modems get $0 unassessed price. This matches the Excel formula: `VLOOKUP(..., 'DO NOT EDIT'!D:L, 9)` checks column L (device type).

4. **Stored procedure** — `GetReport_RepairAssessment_ByProjectTag` is already deployed and validated. Uses EAV pivot pattern with `MAX(CASE WHEN...)`, `READ UNCOMMITTED` isolation, and parameterized inputs.

---

## Acceptance Criteria

- [ ] Login redirects to `/home` with 3 navigation cards (Chatbot, Ecommerce, Analytics)
- [ ] `/analytics/` shows analytics index with Telus Weekly and Price Review links
- [ ] Entering a valid ProjectTag generates the full Repair & Resell report in the browser
- [ ] All 11 computed columns match the Excel VLOOKUP/formula output for the same data
- [ ] Summary bar shows total devices, total lot value, conditions and recommendation breakdowns
- [ ] Recommendations are color-coded with badges (Sell After Repair, Sell As Is, etc.)
- [ ] "Export to Excel" downloads a `.xlsx` file with Repair & Resell, Models, and Summary sheets
- [ ] Price Review page loads all models from `TelusWeeklyPricingMaster`
- [ ] Search/filter works on model names
- [ ] Inline price edits + "Save Changes" persists to the database via AJAX
- [ ] "Add Model" inserts a new row into the pricing master
- [ ] Entering an invalid or empty ProjectTag shows an error message on the form
- [ ] All analytics routes require login (redirect to `/` if not authenticated)
- [ ] `TelusWeeklyPricingMaster` seeded with 831 models from the Excel import script
