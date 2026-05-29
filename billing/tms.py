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
