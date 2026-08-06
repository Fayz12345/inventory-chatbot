-- dbo.RefreshReportingInventoryFlat_OSL — GATED version (2026-07-15)
--
-- Fix: do not bill process events that occurred while a device was in the
-- 'Bridge Product' project. A device received under OSL can be project-
-- transferred in place (ReceiveDetail.ProjectID changed, ProjectTag stays
-- 'OSL'); Bridge then re-touches it — most visibly re-shipping it under the
-- generic 'Shipping' process — and those Bridge events were being billed to
-- OSL. The transfer is dated in dbo.ReceiveDetailProjectLog, so for each
-- process-log event we look up the project as-of that event's CreateDate (the
-- latest log entry on/before it) and only keep the event if that project was
-- not 'Bridge Product'.
--
-- Mirrors the gate applied to dbo.RefreshReportingInventoryFlat_TMS
-- (2026-06-21). Impact measured at deploy (all OSL-tagged devices, all-time):
-- removes 5,936 Bridge 'Shipping' events and 6 Bridge 'QC Assessment' events
-- from OSL billing; Receive is unaffected (0 Bridge events).

ALTER PROCEDURE dbo.RefreshReportingInventoryFlat_OSL
AS
BEGIN
    SET NOCOUNT ON;
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

    TRUNCATE TABLE dbo.ReportingInventoryFlat_OSL;

    INSERT INTO dbo.ReportingInventoryFlat_OSL
    (
        ProjectName, QTY, [Version], ESN, SwappedESN, ProjectTag,
        ManufacturerVerb, Model, ColourVerb, ML_Device_Handset,
        Shipping_OSL_Created, Receive_OSL_Created, QC_Assessment_Created,
        LastRefreshed
    )
    SELECT
        LTRIM(RTRIM(p.Name))                                                               AS ProjectName,
        1                                                                                   AS QTY,
        rd.[Version],
        rd.ESN,
        sw.SwappedESN,
        rd.ProjectTag,

        MAX(CASE WHEN q.Name = 'Manufacturer' THEN o.OptionText END)                        AS ManufacturerVerb,
        MAX(CASE WHEN q.Name = 'Model'        THEN o.OptionText END)                        AS Model,
        MAX(CASE WHEN q.Name = 'Colour'       THEN o.OptionText END)                        AS ColourVerb,
        MAX(CASE WHEN q.Name = 'TMSCATEGORY'  THEN o.OptionText END)                        AS ML_Device_Handset,

        -- Process events gated by project-at-event <> 'Bridge Product'.
        MAX(CASE WHEN pr.Name IN ('Shipping','Shipping OSL') AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END)  AS Shipping_OSL_Created,
        MAX(CASE WHEN pr.Name IN ('Receive','Receive OSL')   AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END)  AS Receive_OSL_Created,
        MAX(CASE WHEN pr.Name = 'QC Assessment'              AND (pae.ProjAtEvent IS NULL OR pae.ProjAtEvent <> 'Bridge Product') THEN rdpl.CreateDate END)  AS QC_Assessment_Created,

        GETDATE()                                                                           AS LastRefreshed
    FROM dbo.ReceiveDetail rd
    LEFT JOIN dbo.Project p
        ON p.ProjectID = rd.ProjectID
    LEFT JOIN (
        SELECT l.ReceiveDetailID, l.IMEISwappedOut AS SwappedESN
        FROM dbo.ReceiveDetailIMEISwappedLog l
        JOIN (
            SELECT ReceiveDetailID, MAX(CreateDate) AS MaxCD
            FROM dbo.ReceiveDetailIMEISwappedLog
            GROUP BY ReceiveDetailID
        ) m ON m.ReceiveDetailID = l.ReceiveDetailID AND m.MaxCD = l.CreateDate
    ) sw ON sw.ReceiveDetailID = rd.ReceiveDetailID
    LEFT JOIN dbo.ReceiveDetailItem rdi
        ON rdi.ReceiveDetailID = rd.ReceiveDetailID
       AND rdi.[Version] = 0
    LEFT JOIN dbo.[Option] o
        ON o.OptionID = rdi.OptionID
    LEFT JOIN dbo.Question q
        ON q.QuestionID = o.QuestionID
       AND q.Name IN ('Manufacturer', 'Model', 'Colour', 'TMSCATEGORY')
    LEFT JOIN dbo.ReceiveDetailProcessLog rdpl
        ON rdpl.ReceiveDetailID = rd.ReceiveDetailID
    LEFT JOIN dbo.Process pr
        ON pr.ProcessID = rdpl.ProcessID
       AND pr.Name IN ('Shipping', 'Shipping OSL', 'Receive', 'Receive OSL', 'QC Assessment')
    -- Project the device belonged to AT THE TIME of each process-log event:
    -- the most recent ReceiveDetailProjectLog entry on or before the event.
    OUTER APPLY (
        SELECT TOP 1 LTRIM(RTRIM(pl.ProjectName)) AS ProjAtEvent
        FROM dbo.ReceiveDetailProjectLog pl
        WHERE pl.ReceiveDetailID = rdpl.ReceiveDetailID
          AND pl.CreateDate <= rdpl.CreateDate
        ORDER BY pl.CreateDate DESC
    ) pae
    WHERE rd.ProjectTag = 'OSL'
    GROUP BY rd.ReceiveDetailID, p.Name, rd.[Version], rd.ESN, sw.SwappedESN, rd.ProjectTag;
END
