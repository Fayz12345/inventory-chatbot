# User Story: TMS Flat Reporting Table

## 1B.5 — TMS Billing Flat Table

**As a** manager,
**I want** a `ReportingInventoryFlat_TMS` table that includes all TMS-tagged devices (all versions),
**so that** I can generate monthly billing reports with the same attributes used in the TMS Billing spreadsheet.

**Filter condition:** `ProjectTag = 'TMS'` (all versions — no `Version = '000'` filter)

**Columns (matching TMS Billing "Data" tab):**

| Column | Source |
|---|---|
| ESN | ReceiveDetail.ESN |
| Version | ReceiveDetail.Version |
| ReceiveDate | ReceiveDetail.CreateDate |
| ManufacturerVerb | Option.OptionText (Manufacturer question) |
| ModelVerb | Option.OptionText (Model question) |
| ColourVerb | Option.OptionText (Colour question) |
| Receipt_Type | Option.OptionText (Receipt Type question) |
| Repair_Fee | ReceiveDetailItem.Value (Numeric — Repair Fee question) |
| Repair_Level | Option.OptionText (Repair Level question) |
| RQ4_SKU_Change | Option.OptionText (RQ4 SKU Change question) |
| ShipTo | ReceiveDetailItem.Value or Option.OptionText (ShipTo question) |
| MSC_Repair_Handling_Created | ReceiveDetailProcessLog.CreateDate (MSC Repair Handling process) |
| QC_Assessment_Created | ReceiveDetailProcessLog.CreateDate (QC Assessment process) |
| Discrepancy_Created | ReceiveDetailProcessLog.CreateDate (Discrepancy process) |
| QC_Created | ReceiveDetailProcessLog.CreateDate (QC process) |
| Shipping_TMS_Created | ReceiveDetailProcessLog.CreateDate (Shipping TMS process) |
| Kitting_Created | ReceiveDetailProcessLog.CreateDate (Kitting process) |
| SKU_Transfer_Created | ReceiveDetailProcessLog.CreateDate (SKU Transfer process) |
| Subsidy_Created | ReceiveDetailProcessLog.CreateDate (Subsidy process) |
| RQ4_SKU_Change_Created | ReceiveDetailProcessLog.CreateDate (RQ4 SKU Change process) |
| Lab_Billing_Created | ReceiveDetailProcessLog.CreateDate (Lab Billing process) |
| SKU_Change_Created | ReceiveDetailProcessLog.CreateDate (SKU Change process) |
| Device_Enrollment_Created | ReceiveDetailProcessLog.CreateDate (Device Enrollment process) |
| Shipping_to_carriers | ReceiveDetailItem.Value or Option.OptionText (Shipping to carriers question) |
| LastRefreshed | GETDATE() at refresh time |

**Refresh schedule:** Monthly, 1st of every month at 2:00 AM (SQL Server Agent Job)

---

## Steps to Accomplish

### 1. Identify source fields in Brains DB

Confirm the exact Question names and Process names that map to each column. Run exploratory queries:

**Questions to confirm (for DropDown/Numeric joins):**
- `ManufacturerVerb` — Question name?
- `ModelVerb` — Question name?
- `ColourVerb` — Question name?
- `Receipt_Type` — Question name?
- `Repair_Fee` — Question name? (likely Numeric type)
- `Repair_Level` — Question name?
- `RQ4_SKU_Change` — Question name?
- `ShipTo` — Question name? (numeric value in sample data, could be a location ID)
- `Shipping_to_carriers` — Question name? (numeric value in sample data, matches ShipTo)

**Processes to confirm (for timestamp joins):**
- MSC Repair Handling
- QC Assessment
- Discrepancy
- QC
- Shipping TMS
- Kitting
- SKU Transfer
- Subsidy
- RQ4 SKU Change
- Lab Billing
- SKU Change
- Device Enrollment

### 2. Create the table on SQL Server

```sql
CREATE TABLE ReportingInventoryFlat_TMS (
    ESN NVARCHAR(50),
    Version NVARCHAR(10),
    ReceiveDate DATETIME,
    ManufacturerVerb NVARCHAR(255),
    ModelVerb NVARCHAR(255),
    ColourVerb NVARCHAR(255),
    Receipt_Type NVARCHAR(255),
    Repair_Fee DECIMAL(10,2),
    Repair_Level NVARCHAR(255),
    RQ4_SKU_Change NVARCHAR(255),
    ShipTo NVARCHAR(255),
    MSC_Repair_Handling_Created DATETIME,
    QC_Assessment_Created DATETIME,
    Discrepancy_Created DATETIME,
    QC_Created DATETIME,
    Shipping_TMS_Created DATETIME,
    Kitting_Created DATETIME,
    SKU_Transfer_Created DATETIME,
    Subsidy_Created DATETIME,
    RQ4_SKU_Change_Created DATETIME,
    Lab_Billing_Created DATETIME,
    SKU_Change_Created DATETIME,
    Device_Enrollment_Created DATETIME,
    Shipping_to_carriers NVARCHAR(255),
    LastRefreshed DATETIME
);
```

Add indexes on `ESN`, `ModelVerb`, `ManufacturerVerb`, `ReceiveDate`.

### 3. Write the stored procedure

Create `RefreshReportingInventoryFlat_TMS`:
- Same pattern as `RefreshReportingInventoryFlat` (truncate + rebuild)
- Filter: `WHERE rd.ProjectTag = 'TMS'` (no Version filter)
- `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`
- Join ReceiveDetailItem for Question-based columns (DropDown → Option.OptionText, Numeric → Value)
- Join ReceiveDetailProcessLog for all 12 process timestamp columns

### 4. Create SQL Server Agent Job

- Schedule: Monthly, Day 1, 2:00 AM
- Step: Execute `RefreshReportingInventoryFlat_TMS`

### 5. Validate

- Run the SP manually
- Compare row counts and sample data against the TMS Billing spreadsheet
- Confirm all 24 attributes are populated correctly
- Verify that `ShipTo` and `Shipping_to_carriers` values match the numeric IDs in the spreadsheet

---

## Acceptance Criteria

- [ ] Stored procedure created filtering `ProjectTag = 'TMS'` with all version codes
- [ ] SQL Server Agent Job scheduled for 1st of month at 2:00 AM
- [ ] Table populated and row counts validated against source
- [ ] Column values match the format/content of the TMS Billing "Data" tab
- [ ] All 12 process timestamp columns correctly joined
- [ ] `LastRefreshed` timestamp updates on each run
