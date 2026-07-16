-- dbo.RefreshReportingInventoryFlat_OSL — ORIGINAL (un-gated) version.
-- Captured from the live SQL Server on 2026-07-15 before applying the
-- Bridge-Product gate. Kept for reference / rollback. Do not deploy this
-- version; see RefreshReportingInventoryFlat_OSL.sql for the current one.

CREATE PROCEDURE dbo.RefreshReportingInventoryFlat_OSL
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

        MAX(CASE WHEN pr.Name IN ('Shipping','Shipping OSL') THEN rdpl.CreateDate END)      AS Shipping_OSL_Created,
        MAX(CASE WHEN pr.Name IN ('Receive','Receive OSL')   THEN rdpl.CreateDate END)      AS Receive_OSL_Created,
        MAX(CASE WHEN pr.Name = 'QC Assessment'              THEN rdpl.CreateDate END)      AS QC_Assessment_Created,

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
    WHERE rd.ProjectTag = 'OSL'
    GROUP BY rd.ReceiveDetailID, p.Name, rd.[Version], rd.ESN, sw.SwappedESN, rd.ProjectTag;
END
