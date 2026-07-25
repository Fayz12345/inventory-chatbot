-- dbo.RefreshReportingInventoryFlat_TMS — GATED version (2026-06-21)
--
-- Fix: do not bill process events that occurred while a device was in the
-- 'Bridge Product' project. A device received under TMS can be project-
-- transferred in place (ReceiveDetail.ProjectID changed, ProjectTag stays
-- 'TMS'); Bridge then re-touches it, re-stamping process-log dates. The
-- transfer is dated in dbo.ReceiveDetailProjectLog, so for each process-log
-- event we look up the project as-of that event's CreateDate (the latest log
-- entry on/before it) and only keep the event if that project was not
-- 'Bridge Product'. ReceiveDate (original receive) is left untouched.
--
-- 2026-07-06: added Buffing_Created (Process.Name = 'Buffing'), billed as a
-- new $10/unit category in the app. Physical column added below, idempotently.

-- Ensure the flat table has the Buffing_Created column (new billing category).
IF COL_LENGTH('dbo.ReportingInventoryFlat_TMS', 'Buffing_Created') IS NULL
    ALTER TABLE dbo.ReportingInventoryFlat_TMS ADD Buffing_Created DATETIME NULL;
GO

ALTER PROCEDURE dbo.RefreshReportingInventoryFlat_TMS
AS
BEGIN
    SET NOCOUNT ON;
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

    TRUNCATE TABLE dbo.ReportingInventoryFlat_TMS;

    INSERT INTO dbo.ReportingInventoryFlat_TMS
    (
        ESN, [Version], ReceiveDate, LastRefreshed,
        ManufacturerVerb, ModelVerb, ColourVerb,
        Receipt_Type, Repair_Fee, Repair_Level, RQ4_SKU_Change, ShipTo, Shipping_to_carriers,
        MSC_Repair_Handling_Created, QC_Assessment_Created, Discrepancy_Created, QC_Created,
        Shipping_TMS_Created, Kitting_Created, SKU_Transfer_Created, Subsidy_Created,
        RQ4_SKU_Change_Created, Lab_Billing_Created, SKU_Change_Created, Device_Enrollment_Created,
        Buffing_Created
    )
    SELECT
        rd.ESN,
        rd.[Version],
        rd.CreateDate                                                                        AS ReceiveDate,
        GETDATE()                                                                            AS LastRefreshed,

        MAX(CASE WHEN q.Name = 'Manufacturer'         THEN o.OptionText END)                 AS ManufacturerVerb,
        MAX(CASE WHEN q.Name = 'Model'                THEN o.OptionText END)                 AS ModelVerb,
        MAX(CASE WHEN q.Name = 'Colour'               THEN o.OptionText END)                 AS ColourVerb,
        MAX(CASE WHEN q.Name = 'Receipt Type'         THEN o.OptionText END)                 AS Receipt_Type,
        TRY_CAST(MAX(CASE WHEN q.Name = 'Repair Fee'  THEN rdi.Value END) AS DECIMAL(10,2))  AS Repair_Fee,
        MAX(CASE WHEN q.Name = 'Repair Level'         THEN o.OptionText END)                 AS Repair_Level,
        MAX(CASE WHEN q.Name = 'RQ4 SKU Change'       THEN o.OptionText END)                 AS RQ4_SKU_Change,
        MAX(CASE WHEN q.Name = 'ShipTo'               THEN rdi.Value END)                    AS ShipTo,
        MAX(CASE WHEN q.Name = 'Carrier'              THEN o.OptionText END)                 AS Shipping_to_carriers,

        -- Process events gated by project-at-event <> 'Bridge Product'.
        MAX(CASE WHEN pr.Name = 'MSC Repair Handling' AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS MSC_Repair_Handling_Created,
        MAX(CASE WHEN pr.Name = 'QC Assessment'       AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS QC_Assessment_Created,
        MAX(CASE WHEN pr.Name = 'Discrepancy'         AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Discrepancy_Created,
        MAX(CASE WHEN pr.Name = 'QC'                  AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS QC_Created,
        MAX(CASE WHEN pr.Name = 'Shipping TMS'        AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Shipping_TMS_Created,
        MAX(CASE WHEN pr.Name = 'Kitting'             AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Kitting_Created,
        MAX(CASE WHEN pr.Name = 'SKU Transfer'        AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS SKU_Transfer_Created,
        MAX(CASE WHEN pr.Name = 'Subsidy'             AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Subsidy_Created,
        MAX(CASE WHEN pr.Name = 'RQ4 SKU Change'      AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS RQ4_SKU_Change_Created,
        MAX(CASE WHEN pr.Name = 'Lab Billing'         AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Lab_Billing_Created,
        MAX(CASE WHEN pr.Name = 'SKU Change'          AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS SKU_Change_Created,
        MAX(CASE WHEN pr.Name = 'Device Enrollment'   AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Device_Enrollment_Created,
        MAX(CASE WHEN pr.Name = 'Buffing'             AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END) AS Buffing_Created
    FROM dbo.ReceiveDetail rd
    LEFT JOIN dbo.ReceiveDetailItem rdi
        ON rdi.ReceiveDetailID = rd.ReceiveDetailID
       AND rdi.[Version] = 0
    LEFT JOIN dbo.[Option] o
        ON o.OptionID = rdi.OptionID
    LEFT JOIN dbo.Question q
        ON q.QuestionID = o.QuestionID
       AND q.Name IN (
            'Manufacturer', 'Model', 'Colour',
            'Receipt Type', 'Repair Fee', 'Repair Level',
            'RQ4 SKU Change', 'ShipTo', 'Carrier'
       )
    LEFT JOIN dbo.ReceiveDetailProcessLog rdpl
        ON rdpl.ReceiveDetailID = rd.ReceiveDetailID
    LEFT JOIN dbo.Process pr
        ON pr.ProcessID = rdpl.ProcessID
       AND pr.Name IN (
            'MSC Repair Handling', 'QC Assessment', 'Discrepancy', 'QC',
            'Shipping TMS', 'Kitting', 'SKU Transfer', 'Subsidy',
            'RQ4 SKU Change', 'Lab Billing', 'SKU Change', 'Device Enrollment',
            'Buffing'
       )
    -- Project the device belonged to AT THE TIME of each process-log event:
    -- the most recent ReceiveDetailProjectLog entry on or before the event.
    OUTER APPLY (
        SELECT TOP 1 LTRIM(RTRIM(pl.ProjectName)) AS ProjAtEvent
        FROM dbo.ReceiveDetailProjectLog pl
        WHERE pl.ReceiveDetailID = rdpl.ReceiveDetailID
          AND pl.CreateDate <= rdpl.CreateDate
        ORDER BY pl.CreateDate DESC
    ) pae
    WHERE rd.ProjectTag = 'TMS'
    GROUP BY rd.ReceiveDetailID, rd.ESN, rd.[Version], rd.CreateDate;
END
