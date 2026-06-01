"""OSL billing engine — read-only aggregation over ReportingInventoryFlat_OSL
joined to MasterCarrierManufacturerLookup for device-category resolution.

Pure functions (testable without a DB) plus generate_report() which wires
the connection. No DDL/INSERT/UPDATE — SELECT only.
"""
import calendar
import datetime

import pyodbc

from billing import config, osl_schedule

TABLE = "dbo.ReportingInventoryFlat_OSL"
CATEGORY_LOOKUP = "dbo.MasterCarrierManufacturerLookup"


def get_db_connection():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


def _count_items_with_section():
    """Yield (section_name, item) for every count line item in order."""
    for section in osl_schedule.OSL_FEE_SCHEDULE:
        for item in section["items"]:
            if item["mode"] == "count":
                yield section["name"], item


def _build_count_select(period_start, period_end):
    """Return (sql, params) for one round-trip aggregate query.

    One SUM(CASE...) AS item_<i> per count line item + an unmapped diagnostic.
    Column names come only from osl_schedule.COUNT_COLUMNS (allowlisted);
    Device_Handset category lists come only from OSL_SECTION_CATEGORIES (also
    developer-controlled). All literal date values are parameterized.
    """
    exprs = []
    params = []
    for i, (section_name, item) in enumerate(_count_items_with_section()):
        col = item["column"]
        if col not in osl_schedule.COUNT_COLUMNS:
            raise ValueError(f"column not allowlisted: {col}")
        cats = osl_schedule.OSL_SECTION_CATEGORIES.get(section_name)
        if not cats:
            # Manual-only section (Accessories) — should not appear here.
            raise ValueError(f"count item in section without category: {section_name}")
        placeholders = ",".join(["?"] * len(cats))
        exprs.append(
            f"SUM(CASE WHEN f.{col} >= ? AND f.{col} < ? "
            f"AND mcl.Device_Handset IN ({placeholders}) "
            "THEN 1 ELSE 0 END) AS item_" + str(i)
        )
        params.append(period_start)
        params.append(period_end)
        params.extend(cats)

    # Unmapped diagnostic: count devices touching the month (any of the three
    # timestamps in window) whose Device_Handset isn't in any mapped section.
    mapped = osl_schedule.MAPPED_CATEGORIES
    placeholders = ",".join(["?"] * len(mapped))
    exprs.append(
        "SUM(CASE WHEN "
        "(f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ? "
        " OR f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ? "
        " OR f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ?) "
        f"AND (mcl.Device_Handset IS NULL OR LTRIM(RTRIM(mcl.Device_Handset)) NOT IN ({placeholders})) "
        "THEN 1 ELSE 0 END) AS unmapped_in_month"
    )
    params.extend([period_start, period_end] * 3)
    params.extend(mapped)

    # WHERE clause prunes rows that can't contribute to anything (optimization).
    where_clause = (
        "WHERE f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ?\n"
        "   OR f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ?\n"
        "   OR f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ?\n"
    )
    params.extend([period_start, period_end] * 3)

    sql = (
        "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;\n"
        "SELECT\n  " + ",\n  ".join(exprs) + "\n"
        f"FROM {TABLE} f\n"
        "OUTER APPLY (\n"
        f"    SELECT TOP 1 LTRIM(RTRIM(m.Device_Handset)) AS Device_Handset\n"
        f"    FROM {CATEGORY_LOOKUP} m\n"
        "    WHERE m.Manufacturer = f.ManufacturerVerb\n"
        "      AND m.Model        = f.Model\n"
        "    ORDER BY m.LastUpdateDate DESC\n"
        ") mcl\n"
        + where_clause + ";"
    )
    return sql, params


def _assemble_report(raw, period_start):
    """Build the structured report from the aggregate row dict `raw`."""
    sections_out = []
    grand_total_auto = 0.0
    count_idx = 0

    for section in osl_schedule.OSL_FEE_SCHEDULE:
        line_items = []
        section_total = 0.0
        for item in section["items"]:
            mode = item["mode"]
            if mode == "count":
                units = int(raw.get(f"item_{count_idx}") or 0)
                count_idx += 1
                charge = units * item["fee"]
                line_items.append({
                    "label": item["label"], "units": units,
                    "fee": item["fee"], "charge": charge, "mode": mode,
                })
                section_total += charge
                grand_total_auto += charge
            else:  # manual
                line_items.append({
                    "label": item["label"], "units": None,
                    "fee": item["fee"], "charge": 0, "mode": mode,
                })
        sections_out.append({
            "name": section["name"], "line_items": line_items,
            "section_total": section_total,
        })

    label = f"{calendar.month_name[period_start.month]} {period_start.year}"
    return {
        "period_label": label,
        "sections": sections_out,
        "grand_total_auto": grand_total_auto,
        "diagnostics": {
            "unmapped_in_month": int(raw.get("unmapped_in_month") or 0),
        },
    }


def _period_bounds(year, month):
    start = datetime.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime.date(year, month, last_day) + datetime.timedelta(days=1)
    return start, end


def generate_report(year, month, conn_factory=get_db_connection):
    """Run the aggregate query for the given month and assemble the report.

    conn_factory is injectable for testing. Read-only; closes the connection.
    """
    start, end = _period_bounds(int(year), int(month))
    sql, params = _build_count_select(start, end)
    conn = conn_factory()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        values = cursor.fetchone()
        raw = dict(zip(columns, values))
    finally:
        conn.close()
    return _assemble_report(raw, start)
