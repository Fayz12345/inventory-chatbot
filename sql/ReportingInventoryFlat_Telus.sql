/* =============================================================================
   1B.1 — Telus Flat Table  (ADO #122)
   Full Telus project history: ALL projects matching ProjectName LIKE '%Telus%',
   ALL versions (including shipped). Mirrors the base ReportingInventoryFlat
   columns + a Version column, using the staging+swap refresh pattern so the
   live table is never empty mid-refresh.

   Run order on the `bridge` DB:
     1) CREATE TABLE + indexes   (section 1)
     2) CREATE OR ALTER proc      (section 2)
     3) EXEC dbo.RefreshReportingInventoryFlat_Telus;   (initial load)
     4) Validation queries        (section 4)
     5) SQL Agent job             (section 5 — Sunday 02:00 weekly)
   ============================================================================= */

/* ----------------------------------------------------------------------------
   SECTION 1 — Table + indexes  (guarded; will not drop existing data)
   ---------------------------------------------------------------------------- */
IF OBJECT_ID('dbo.ReportingInventoryFlat_Telus', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ReportingInventoryFlat_Telus
    (
        ESN                   nvarchar(50)   NULL,
        [Version]             nchar(3)       NULL,   -- '000' = in-stock; '8xx'/other = shipped/historical
        ProjectName           nvarchar(50)   NULL,
        ProjectTag            nvarchar(50)   NULL,
        ReceiveDate           datetime       NULL,
        Product_Place         nvarchar(500)  NULL,
        Manufacturer          nvarchar(50)   NULL,
        Model                 nvarchar(50)   NULL,
        Colour                nvarchar(50)   NULL,
        Grade                 nvarchar(500)  NULL,
        Received_Grade        nvarchar(500)  NULL,
        DeviceCost            decimal(10,2)  NULL,
        Function_Test_Created nvarchar(20)   NULL,   -- mirrors base table (string-formatted datetime)
        Grading_Created       nvarchar(20)   NULL,
        LastRefreshed         datetime       NULL
    );

    CREATE NONCLUSTERED INDEX IX_RIF_Telus_ProjectName  ON dbo.ReportingInventoryFlat_Telus(ProjectName);
    CREATE NONCLUSTERED INDEX IX_RIF_Telus_Model         ON dbo.ReportingInventoryFlat_Telus(Model);
    CREATE NONCLUSTERED INDEX IX_RIF_Telus_Manufacturer  ON dbo.ReportingInventoryFlat_Telus(Manufacturer);
    CREATE NONCLUSTERED INDEX IX_RIF_Telus_Version       ON dbo.ReportingInventoryFlat_Telus([Version]);
END
GO

/* ----------------------------------------------------------------------------
   SECTION 2 — Refresh proc  (staging+swap; all Telus projects, all versions)
   ---------------------------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.RefreshReportingInventoryFlat_Telus
AS
BEGIN
    SET NOCOUNT ON;
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

    DECLARE @rows INT = 0;

    IF OBJECT_ID('dbo.ReportingInventoryFlat_Telus_Staging') IS NOT NULL
        DROP TABLE dbo.ReportingInventoryFlat_Telus_Staging;

    -- Build the full result set into staging FIRST (heavy work, outside the txn).
    SELECT
        rd.ESN,
        rd.[Version],
        p.Name                                                                              AS ProjectName,
        rd.ProjectTag                                                                       AS ProjectTag,
        rd.CreateDate                                                                       AS ReceiveDate,
        MAX(CASE WHEN q.Name = 'Product Place'   THEN o.OptionText END)                     AS Product_Place,
        MAX(CASE WHEN q.Name = 'Manufacturer'    THEN o.OptionText END)                     AS Manufacturer,
        MAX(CASE WHEN q.Name = 'Model'           THEN o.OptionText END)                     AS Model,
        MAX(CASE WHEN q.Name = 'Colour'          THEN o.OptionText END)                     AS Colour,
        MAX(CASE WHEN q.Name = 'Grade'           THEN o.OptionText END)                     AS Grade,
        MAX(CASE WHEN q.Name = 'Received Grade'  THEN o.OptionText END)                     AS Received_Grade,
        TRY_CAST(MAX(CASE WHEN q.Name = 'DeviceCost' THEN rdi.Value END) AS decimal(10,2))  AS DeviceCost,
        MAX(CASE WHEN pr.Name = 'Function Test'  THEN rdpl.CreateDate END)                  AS Function_Test_Created,
        MAX(CASE WHEN pr.Name = 'Grading'        THEN rdpl.CreateDate END)                  AS Grading_Created,
        GETDATE()                                                                           AS LastRefreshed
    INTO dbo.ReportingInventoryFlat_Telus_Staging
    FROM dbo.ReceiveDetail rd
    JOIN dbo.Project p
        ON p.ProjectID = rd.ProjectID
       AND p.Name LIKE '%Telus%'
    LEFT JOIN dbo.ReceiveDetailItem rdi
        ON rdi.ReceiveDetailID = rd.ReceiveDetailID
       AND rdi.[Version] = 0
    LEFT JOIN dbo.[Option] o
        ON o.OptionID = rdi.OptionID
    LEFT JOIN dbo.Question q
        ON q.QuestionID = o.QuestionID
       AND q.Name IN ('Product Place','Manufacturer','Model','Colour','Grade','Received Grade','DeviceCost')
    LEFT JOIN dbo.ReceiveDetailProcessLog rdpl
        ON rdpl.ReceiveDetailID = rd.ReceiveDetailID
    LEFT JOIN dbo.Process pr
        ON pr.ProcessID = rdpl.ProcessID
       AND pr.Name IN ('Function Test','Grading')
    -- NOTE: no rd.Version filter => ALL versions, including shipped (1B.1 intent).
    GROUP BY rd.ReceiveDetailID, rd.ESN, rd.[Version], p.Name, rd.ProjectTag, rd.CreateDate;

    BEGIN TRY
        BEGIN TRANSACTION;
            TRUNCATE TABLE dbo.ReportingInventoryFlat_Telus;
            INSERT INTO dbo.ReportingInventoryFlat_Telus (
                ESN, [Version], ProjectName, ProjectTag, ReceiveDate,
                Product_Place, Manufacturer, Model, Colour,
                Grade, Received_Grade, DeviceCost,
                Function_Test_Created, Grading_Created, LastRefreshed
            )
            SELECT
                ESN, [Version], ProjectName, ProjectTag, ReceiveDate,
                Product_Place, Manufacturer, Model, Colour,
                Grade, Received_Grade, DeviceCost,
                Function_Test_Created, Grading_Created, LastRefreshed
            FROM dbo.ReportingInventoryFlat_Telus_Staging;

            SET @rows = @@ROWCOUNT;   -- capture BEFORE the DROP resets it
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH;

    DROP TABLE dbo.ReportingInventoryFlat_Telus_Staging;

    SELECT CAST(@rows AS varchar) + ' rows loaded' AS Result;
END
GO

/* ----------------------------------------------------------------------------
   SECTION 3 — Initial load
   ---------------------------------------------------------------------------- */
-- EXEC dbo.RefreshReportingInventoryFlat_Telus;

/* ----------------------------------------------------------------------------
   SECTION 4 — Validation
   ---------------------------------------------------------------------------- */
-- Expected (all Telus projects, all versions) vs loaded:
-- SELECT COUNT(*) AS expected_all_versions
-- FROM dbo.ReceiveDetail rd JOIN dbo.Project p ON p.ProjectID = rd.ProjectID
-- WHERE p.Name LIKE '%Telus%';
-- SELECT COUNT(*) AS loaded FROM dbo.ReportingInventoryFlat_Telus;
--
-- Per-project breakdown (should list all 12 Telus projects):
-- SELECT ProjectName, COUNT(*) AS rows,
--        SUM(CASE WHEN [Version]='000' THEN 1 ELSE 0 END) AS instock
-- FROM dbo.ReportingInventoryFlat_Telus GROUP BY ProjectName ORDER BY rows DESC;

/* ----------------------------------------------------------------------------
   SECTION 5 — SQL Server Agent job: Sunday 02:00 weekly
   Matches the existing "Refresh ... Flat Table" jobs (TSQL / bridge / owner sa).
   NOTE: distinct from the existing "Refresh Telus Flat Table - Nightly" job,
   which runs the OLD RefreshReportingTelusFlat (different table).
   Run the whole block in the context of msdb. Idempotent: drops same-named job first.
   ---------------------------------------------------------------------------- */
USE msdb;
GO
DECLARE @job_name sysname = N'Refresh Telus (All Projects) Flat Table - Weekly';

IF EXISTS (SELECT 1 FROM msdb.dbo.sysjobs WHERE name = @job_name)
    EXEC dbo.sp_delete_job @job_name = @job_name;

EXEC dbo.sp_add_job
     @job_name = @job_name,
     @owner_login_name = N'sa',
     @description = N'Weekly full refresh of dbo.ReportingInventoryFlat_Telus (all Telus projects, all versions). ADO #122 / 1B.1.';

EXEC dbo.sp_add_jobstep
     @job_name      = @job_name,
     @step_name     = N'Run RefreshReportingInventoryFlat_Telus',
     @subsystem     = N'TSQL',
     @database_name = N'bridge',
     @command       = N'EXEC dbo.RefreshReportingInventoryFlat_Telus;';

EXEC dbo.sp_add_schedule
     @schedule_name = N'Weekly_Sunday_0200_Telus',
     @freq_type = 8,                 -- weekly
     @freq_interval = 1,             -- Sunday (Sun=1, Mon=2, Tue=4, ... Sat=64)
     @freq_recurrence_factor = 1,    -- every 1 week
     @active_start_time = 020000;    -- 02:00:00

EXEC dbo.sp_attach_schedule
     @job_name = @job_name,
     @schedule_name = N'Weekly_Sunday_0200_Telus';

EXEC dbo.sp_add_jobserver
     @job_name = @job_name;          -- target local Agent server
GO
