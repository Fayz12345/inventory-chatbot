# User Story: OSL Flat Reporting Table

## 1B.4 — OSL Billing Flat Table

**As a** manager,
**I want** a `ReportingInventoryFlat_OSL` table that includes all OSL-tagged devices (all versions),
**so that** I can generate monthly billing reports with the same attributes used in the OSL Billing spreadsheet.

**Filter condition:** `ProjectTag = 'OSL'` (all versions — no `Version = '000'` filter)

**Columns (matching OSL Billing "Data" tab):**

| Column | Source |
|---|---|
| ProjectName | Project.Name |
| QTY | Count / literal 1 per ESN |
| Version | ReceiveDetail.Version |
| SwappedESN | ReceiveDetail.SwappedESN (or equivalent field) |
| ManufacturerVerb | Option.OptionText (Manufacturer question) |
| Model | Option.OptionText (Model question) |
| ColourVerb | Option.OptionText (Colour question) |
| ML_Device_Handset | Option.OptionText (device type/category question) |
| Shipping_OSL_Created | ReceiveDetailProcessLog.CreateDate for Shipping process |
| Receive_OSL_Created | ReceiveDetailProcessLog.CreateDate for Receive process |
| QC_Assessment_Created | ReceiveDetailProcessLog.CreateDate for QC Assessment process |
| ProjectTag | ReceiveDetail.ProjectTag |
| LastRefreshed | GETDATE() at refresh time |

**Refresh schedule:** Monthly, 1st of every month at 2:00 AM (SQL Server Agent Job)

---

## Steps to Accomplish

### 1. Identify source fields in Brains DB

Confirm the exact Question names and Process names that map to:
- `ManufacturerVerb` — which Question name?
- `ColourVerb` — which Question name?
- `ML_Device_Handset` — which Question name maps to device type/category?
- `Shipping_OSL_Created` — which Process name?
- `Receive_OSL_Created` — which Process name?
- `QC_Assessment_Created` — which Process name?

Run exploratory queries against the `Question`, `Process`, and `Option` tables to confirm.

### 2. Create the table on SQL Server

```sql
CREATE TABLE ReportingInventoryFlat_OSL (
    ProjectName NVARCHAR(255),
    QTY INT DEFAULT 1,
    Version NVARCHAR(10),
    SwappedESN NVARCHAR(50),
    ManufacturerVerb NVARCHAR(255),
    Model NVARCHAR(255),
    ColourVerb NVARCHAR(255),
    ML_Device_Handset NVARCHAR(255),
    Shipping_OSL_Created DATETIME,
    Receive_OSL_Created DATETIME,
    QC_Assessment_Created DATETIME,
    ProjectTag NVARCHAR(50),
    LastRefreshed DATETIME
);
```

Add indexes on `ProjectTag`, `Model`, `ManufacturerVerb`.

### 3. Write the stored procedure

Create `RefreshReportingInventoryFlat_OSL`:
- Same pattern as `RefreshReportingInventoryFlat` (truncate + rebuild)
- Filter: `WHERE rd.ProjectTag = 'OSL'` (no Version filter)
- `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`
- Join process log dates for the 3 timestamp columns (Shipping, Receive, QC Assessment)

### 4. Create SQL Server Agent Job

- Schedule: Monthly, Day 1, 2:00 AM
- Step: Execute `RefreshReportingInventoryFlat_OSL`

### 5. Validate

- Run the SP manually
- Compare row counts and sample data against the OSL Billing spreadsheet
- Confirm all 12 attributes are populated correctly

---

## Acceptance Criteria

- [ ] Stored procedure created filtering `ProjectTag = 'OSL'` with all version codes
- [ ] SQL Server Agent Job scheduled for 1st of month at 2:00 AM
- [ ] Table populated and row counts validated against source
- [ ] Column values match the format/content of the OSL Billing "Data" tab
- [ ] `LastRefreshed` timestamp updates on each run
