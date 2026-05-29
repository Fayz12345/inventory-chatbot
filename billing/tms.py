"""TMS billing engine — read-only aggregation over ReportingInventoryFlat_TMS.

Splits into pure functions (testable without a DB) plus generate_report()
which wires the connection. No DDL/INSERT/UPDATE — SELECT only.
"""
import calendar
import datetime

import pyodbc

from billing import config, schedule

TABLE = "dbo.ReportingInventoryFlat_TMS"


def get_db_connection():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


def _count_items():
    """Flatten schedule to the ordered list of 'count' items."""
    items = []
    for section in schedule.TMS_FEE_SCHEDULE:
        for item in section["items"]:
            if item["mode"] == "count":
                items.append(item)
    return items


def _repair_item():
    for section in schedule.TMS_FEE_SCHEDULE:
        for item in section["items"]:
            if item["mode"] == "sum_repair_fee":
                return item
    return None


def _build_count_select(period_start, period_end):
    """Return (sql, params) for one round-trip aggregate query.

    One SUM(CASE...) AS item_<i> per count line item, plus repair_fee_sum.
    Column names come only from schedule.COUNT_COLUMNS (allowlisted);
    all literal values are parameterized.
    """
    exprs = []
    params = []
    for i, item in enumerate(_count_items()):
        col = item["column"]
        if col not in schedule.COUNT_COLUMNS:
            raise ValueError(f"column not allowlisted: {col}")
        clauses = [f"{col} >= ? AND {col} < ?"]
        params.extend([period_start, period_end])
        rt = item["receipt_type"]
        if isinstance(rt, list):
            placeholders = ",".join(["?"] * len(rt))
            clauses.append(f"Receipt_Type IN ({placeholders})")
            params.extend(rt)
        elif rt:
            clauses.append("Receipt_Type = ?")
            params.append(rt)
        if item["manufacturer"] is not None:
            clauses.append(f"ManufacturerVerb {item['manufacturer_op']} ?")
            params.append(item["manufacturer"])
        exprs.append(
            f"SUM(CASE WHEN {' AND '.join(clauses)} THEN 1 ELSE 0 END) AS item_{i}"
        )

    # Out-of-warranty repair: SUM(Repair_Fee) where Lab_Billing_Created in period.
    repair = _repair_item()
    if repair is not None:
        exprs.append(
            "SUM(CASE WHEN Lab_Billing_Created >= ? AND Lab_Billing_Created < ? "
            "THEN Repair_Fee ELSE 0 END) AS repair_fee_sum"
        )
        params.extend([period_start, period_end])

    sql = (
        "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;\n"
        "SELECT\n  " + ",\n  ".join(exprs) + f"\nFROM {TABLE};"
    )
    return sql, params


def _assemble_report(raw, period_start):
    """Build the structured report from the aggregate row dict `raw`.

    raw: {'item_0': int, ..., 'repair_fee_sum': float}
    Returns: {period_label, sections:[{name, line_items:[...], section_total}],
              grand_total_auto}
    Manual items: units=None, charge=0 (filled in by the browser).
    """
    repair_sum = float(raw.get("repair_fee_sum") or 0)
    sections_out = []
    grand_total_auto = 0.0
    count_idx = 0

    for section in schedule.TMS_FEE_SCHEDULE:
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
            elif mode == "sum_repair_fee":
                line_items.append({
                    "label": item["label"], "units": None,
                    "fee": None, "charge": repair_sum, "mode": mode,
                })
                section_total += repair_sum
                grand_total_auto += repair_sum
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
