#!/usr/bin/env python3
"""
Bridge ERP — read-only DB discovery for the reverse-logistics ERP plan.

WHAT THIS IS
------------
A strictly READ-ONLY introspection of the live `bridge` SQL Server. It answers the
open questions in ERP_IMPLEMENTATION_PLAN.md that need live data:
  * the DBML(224)-vs-live(237) table delta + real row counts (biggest tables)
  * which of the ~722 stored procs encode MVP logic (receiving / allocation / sales)
  * the real ReportingInventoryFlat refresh logic (attribute/receiving joins)
  * the true field-type catalog, process catalog, status vocab, and key FKs

PRODUCTION-SAFETY (this is a live system written to hourly)
----------------------------------------------------------
  * READ UNCOMMITTED isolation -> takes no shared locks (same as your refresh proc).
  * Row counts come from sys.dm_db_partition_stats (metadata) -> NO table scans.
  * Only SELECT / catalog views / OBJECT_DEFINITION are issued. No INSERT/UPDATE/
    DELETE/DDL/EXEC. A guard rejects any non-SELECT text before execution.
  * Results are bounded (TOP N). Full proc bodies limited to a short curated list.
  * Tier-2 aggregate queries (which do read data) are OFF by default; enable with
    `--aggregates` and ideally run them off-peak.

HOW TO RUN (on the Linux EC2, in ~/inventory-chatbot, venv active)
------------------------------------------------------------------
    python db_discovery.py                 # safe metadata-only run
    python db_discovery.py --aggregates    # + a few light GROUP BYs (NOLOCK), off-peak
    python db_discovery.py > discovery.txt 2>&1   # capture to a file to send back

It reads DB creds from your existing config.py (DB_SERVER/DB_NAME/DB_USER/DB_PASSWORD),
or from the same-named environment variables. No secrets are printed.
"""

import sys
import os
import textwrap

# ---- connection settings from existing config.py, or env vars -------------
def _load_settings():
    s = {}
    try:
        import config  # your gitignored config.py at repo root
        for k in ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            s[k] = getattr(config, k)
    except Exception:
        for k in ("DB_SERVER", "DB_NAME", "DB_USER", "DB_PASSWORD"):
            s[k] = os.environ.get(k)
    missing = [k for k, v in s.items() if not v]
    if missing:
        sys.exit(f"Missing DB settings: {', '.join(missing)} "
                 f"(provide via config.py or environment).")
    return s


def _connect():
    import pyodbc
    s = _load_settings()
    conn = pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={s['DB_SERVER']};DATABASE={s['DB_NAME']};"
        f"UID={s['DB_USER']};PWD={s['DB_PASSWORD']};"
        "TrustServerCertificate=yes;",
        timeout=15,
    )
    # No shared locks on a live system.
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;")
    return conn


# ---- read-only guard + pretty printer -------------------------------------
def _guard(sql: str):
    lowered = sql.strip().lower()
    if not (lowered.startswith("select") or lowered.startswith("with")
            or lowered.startswith("set transaction")):
        raise RuntimeError(f"Refused non-SELECT statement: {sql[:60]!r}")
    for bad in (" insert ", " update ", " delete ", " drop ", " alter ",
                " truncate ", " exec ", " execute ", " merge ", " grant "):
        if bad in f" {lowered} ":
            raise RuntimeError(f"Refused statement containing {bad.strip()!r}")


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def run(cur, title, sql, limit=500):
    section(title)
    _guard(sql)
    try:
        cur.execute(sql)
        cols = [c[0] for c in cur.description]
        print(" | ".join(cols))
        print("-" * 78)
        for i, row in enumerate(cur.fetchall()):
            if i >= limit:
                print(f"... (truncated at {limit} rows)")
                break
            print(" | ".join("" if v is None else str(v) for v in row))
    except Exception as e:
        print(f"[query failed: {e}]")


# ---- Tier 1: metadata only (safe anytime) ---------------------------------
def tier1(cur):
    run(cur, "SERVER / DATABASE", """
        SELECT @@VERSION AS version, DB_NAME() AS current_db,
               (SELECT CAST(SUM(size)*8.0/1024/1024 AS DECIMAL(10,2))
                  FROM sys.master_files WHERE database_id = DB_ID()) AS total_gb
    """)

    run(cur, "OBJECT COUNTS BY TYPE", """
        SELECT type_desc, COUNT(*) AS n
        FROM sys.objects
        WHERE is_ms_shipped = 0
        GROUP BY type_desc ORDER BY n DESC
    """)

    run(cur, "ALL BASE TABLES WITH ROW COUNTS (metadata, no scans) — DBML delta + big tables", """
        SELECT t.name AS table_name,
               SUM(CASE WHEN p.index_id IN (0,1) THEN p.row_count ELSE 0 END) AS rows,
               CAST(SUM(a.total_pages)*8.0/1024 AS DECIMAL(12,1)) AS size_mb
        FROM sys.tables t
        JOIN sys.dm_db_partition_stats p ON p.object_id = t.object_id
        JOIN sys.allocation_units a ON a.container_id = p.partition_id
        GROUP BY t.name
        ORDER BY rows DESC
    """, limit=400)

    run(cur, "ALL VIEWS", """
        SELECT name FROM sys.views WHERE is_ms_shipped = 0 ORDER BY name
    """, limit=400)

    run(cur, "STORED PROCS / FUNCTIONS RELEVANT TO MVP (name + size, not body)", """
        SELECT o.type_desc, o.name,
               LEN(OBJECT_DEFINITION(o.object_id)) AS def_len,
               o.modify_date
        FROM sys.objects o
        WHERE o.type IN ('P','FN','IF','TF','V')
          AND (o.name LIKE '%Receive%' OR o.name LIKE '%Reserv%'
            OR o.name LIKE '%Allocat%' OR o.name LIKE '%Pick%'
            OR o.name LIKE '%Pack%'    OR o.name LIKE '%Ship%'
            OR o.name LIKE '%SO[_]%'   OR o.name LIKE '%Sales%'
            OR o.name LIKE '%Grade%'   OR o.name LIKE '%Test%'
            OR o.name LIKE '%Repair%'  OR o.name LIKE '%Inventory%'
            OR o.name LIKE '%Bin%'     OR o.name LIKE '%Location%'
            OR o.name LIKE '%Reporting%')
        ORDER BY o.name
    """, limit=500)

    key_tables = [
        'ReceiveHeader','ReceiveDetail','ReceiveDetailItem','Option','Question',
        'QuestionType','Process','ProjectProcess','ProcessQuestion','SOHeader',
        'SODetail','SODetailReceiveDetail','ReservedAvailableStock',
        'ReportingInventoryFlat','BinLocation','Client','Project',
        'OrderHeader','OrderDetail','SOPickListHeader','SOPickListDetail',
    ]
    inlist = ",".join(f"'{t}'" for t in key_tables)
    run(cur, "COLUMNS FOR KEY TABLES (live schema, incl. anything added since the DBML)", f"""
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE,
               CHARACTER_MAXIMUM_LENGTH AS len, IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME IN ({inlist})
        ORDER BY TABLE_NAME, ORDINAL_POSITION
    """, limit=1200)

    run(cur, "FOREIGN KEYS AMONG KEY TABLES (real relationships)", f"""
        SELECT OBJECT_NAME(fk.parent_object_id) AS from_table,
               cpa.name AS from_col,
               OBJECT_NAME(fk.referenced_object_id) AS to_table,
               cref.name AS to_col
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.columns cpa ON cpa.object_id = fk.parent_object_id
                             AND cpa.column_id = fkc.parent_column_id
        JOIN sys.columns cref ON cref.object_id = fk.referenced_object_id
                              AND cref.column_id = fkc.referenced_column_id
        WHERE OBJECT_NAME(fk.parent_object_id) IN ({inlist})
           OR OBJECT_NAME(fk.referenced_object_id) IN ({inlist})
        ORDER BY from_table, to_table
    """, limit=600)

    # Small reference tables — safe full reads, reveal the real vocab to seed the ERP
    run(cur, "FIELD-TYPE CATALOG (QuestionType)", "SELECT * FROM QuestionType ORDER BY QuestionTypeID")
    run(cur, "PROCESS CATALOG (Process)", """
        SELECT ProcessID, Name, Sequence, StatusID FROM Process ORDER BY Sequence, Name
    """, limit=300)
    for tbl, cols in [
        ("ReceiveDetailStatus", "*"),
        ("ProcessStatus", "*"),
        ("OrderStatus", "*"),
        ("ProjectStatus", "*"),
        ("ClientStatus", "*"),
    ]:
        run(cur, f"STATUS VOCAB — {tbl}", f"SELECT {cols} FROM {tbl}", limit=200)

    # The crown jewel: real refresh logic (definitions are a few KB — fine to print)
    section("REFRESH PROC DEFINITIONS (real attribute/receiving join logic)")
    for proc in ("RefreshReportingInventoryFlat",
                 "RefreshReportingInventoryFlat_TMS"):
        _guard("select 1")
        try:
            cur.execute("SELECT OBJECT_DEFINITION(OBJECT_ID(?))", proc)
            body = cur.fetchone()[0]
            print(f"\n----- {proc} -----")
            print(body if body else "[not found]")
        except Exception as e:
            print(f"[{proc}: {e}]")


# ---- Tier 2: light aggregates (READS DATA — off-peak, opt-in) --------------
def tier2(cur):
    section("TIER 2 — LIGHT AGGREGATES (NOLOCK). Run off-peak.")
    run(cur, "ReceiveDetail.Version distribution (lifecycle encoding)", """
        SELECT Version, COUNT_BIG(*) AS n
        FROM ReceiveDetail WITH (NOLOCK)
        GROUP BY Version ORDER BY n DESC
    """, limit=100)
    run(cur, "ReceiveDetail by StatusID", """
        SELECT StatusID, COUNT_BIG(*) AS n
        FROM ReceiveDetail WITH (NOLOCK)
        GROUP BY StatusID ORDER BY n DESC
    """, limit=100)
    run(cur, "SOHeader by Status", """
        SELECT Status, COUNT_BIG(*) AS n
        FROM SOHeader WITH (NOLOCK)
        GROUP BY Status ORDER BY n DESC
    """, limit=100)


def main():
    do_aggr = "--aggregates" in sys.argv
    print(textwrap.dedent("""\
        Bridge ERP DB discovery — READ ONLY.
        Metadata-first; no writes; no table scans in Tier 1.
    """))
    conn = _connect()
    cur = conn.cursor()
    try:
        tier1(cur)
        if do_aggr:
            tier2(cur)
        else:
            section("TIER 2 SKIPPED")
            print("Re-run with --aggregates (off-peak) to include Version/Status "
                  "distributions.")
    finally:
        conn.close()
    section("DONE")
    print("Paste this entire output back into the ERP planning chat.")


if __name__ == "__main__":
    main()
