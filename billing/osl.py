"""OSL billing engine — per-model event breakdown over ReportingInventoryFlat_OSL
joined to MasterCarrierManufacturerLookup for device-category resolution.

A single breakdown query returns one row per Manufacturer+Model with Receive /
QC / Shipping event counts (and a device "touch" count) within the period. That
breakdown powers BOTH the billing report and the Category Review tab.

Categories can be overridden in-session: `assemble_from_breakdown` resolves each
model's effective category (override if present, else the ERP/lookup value),
maps it to a billing section, and sums the fees. Because the report is computed
from the same breakdown the Category Review tab displays, the two tabs always
agree — and an override moves the billing total. Read-only SQL (SELECT only).
"""
import calendar
import datetime

import pyodbc

from billing import config, osl_schedule

TABLE = "dbo.ReportingInventoryFlat_OSL"
CATEGORY_LOOKUP = "dbo.MasterCarrierManufacturerLookup"

# Maps each count line item's flat-table column to its breakdown event key.
_EVENT_BY_COLUMN = {
    "Receive_OSL_Created": "receive",
    "QC_Assessment_Created": "qc",
    "Shipping_OSL_Created": "shipping",
}


def get_db_connection():
    return pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


def _period_bounds(year, month):
    start = datetime.date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime.date(year, month, last_day) + datetime.timedelta(days=1)
    return start, end


def get_model_breakdown(year, month, conn_factory=get_db_connection):
    """Return per (manufacturer, model, category) event counts for the period.

    Each row: manufacturer, model, category (Device_Handset via the master-data
    lookup, TOP 1 by LastUpdateDate), plus receive/qc/shipping event counts and
    `touch` (number of device rows touching the month). Read-only.
    """
    start, end = _period_bounds(int(year), int(month))
    sql = (
        "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;\n"
        "SELECT\n"
        "    f.ManufacturerVerb,\n"
        "    f.Model,\n"
        "    mcl.Device_Handset,\n"
        "    SUM(CASE WHEN f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ? "
        "THEN 1 ELSE 0 END) AS receive_ct,\n"
        "    SUM(CASE WHEN f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ? "
        "THEN 1 ELSE 0 END) AS qc_ct,\n"
        "    SUM(CASE WHEN f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ? "
        "THEN 1 ELSE 0 END) AS shipping_ct,\n"
        "    SUM(CASE WHEN f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ?\n"
        "          OR f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ?\n"
        "          OR f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ? "
        "THEN 1 ELSE 0 END) AS touch_ct\n"
        f"FROM {TABLE} f\n"
        "OUTER APPLY (\n"
        f"    SELECT TOP 1 LTRIM(RTRIM(m.Device_Handset)) AS Device_Handset\n"
        f"    FROM {CATEGORY_LOOKUP} m\n"
        "    WHERE m.Manufacturer = f.ManufacturerVerb\n"
        "      AND m.Model        = f.Model\n"
        "    ORDER BY m.LastUpdateDate DESC\n"
        ") mcl\n"
        "WHERE f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ?\n"
        "   OR f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ?\n"
        "   OR f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ?\n"
        "GROUP BY f.ManufacturerVerb, f.Model, mcl.Device_Handset\n"
        "ORDER BY f.ManufacturerVerb, f.Model;\n"
    )
    # 3 SELECT windows (receive/qc/shipping) + 3 for the touch OR-clause + 3 WHERE
    params = [start, end] * 9
    conn = conn_factory()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [
            {
                "manufacturer": row[0] or "",
                "model": row[1] or "",
                "category": (row[2] or "").strip(),
                "receive": int(row[3] or 0),
                "qc": int(row[4] or 0),
                "shipping": int(row[5] or 0),
                "touch": int(row[6] or 0),
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def get_raw_rows(year, month, conn_factory=get_db_connection):
    """Return (columns, rows) of every flat-table device row touching the period.

    A row qualifies if any of the three OSL timestamps falls in the month. The
    resolved Device_Handset category (same OUTER APPLY as the billing query) is
    appended as a final `Resolved_Category` column for audit. Read-only.
    """
    start, end = _period_bounds(int(year), int(month))
    sql = (
        "SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;\n"
        "SELECT f.*, mcl.Device_Handset AS Resolved_Category\n"
        f"FROM {TABLE} f\n"
        "OUTER APPLY (\n"
        f"    SELECT TOP 1 LTRIM(RTRIM(m.Device_Handset)) AS Device_Handset\n"
        f"    FROM {CATEGORY_LOOKUP} m\n"
        "    WHERE m.Manufacturer = f.ManufacturerVerb\n"
        "      AND m.Model        = f.Model\n"
        "    ORDER BY m.LastUpdateDate DESC\n"
        ") mcl\n"
        "WHERE (f.Receive_OSL_Created >= ? AND f.Receive_OSL_Created < ?)\n"
        "   OR (f.QC_Assessment_Created >= ? AND f.QC_Assessment_Created < ?)\n"
        "   OR (f.Shipping_OSL_Created >= ? AND f.Shipping_OSL_Created < ?);"
    )
    params = [start, end] * 3
    conn = conn_factory()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = [list(r) for r in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()


def _category_to_section():
    """Reverse of OSL_SECTION_CATEGORIES: Device_Handset value -> section name."""
    mapping = {}
    for section_name, cats in osl_schedule.OSL_SECTION_CATEGORIES.items():
        for cat in cats:
            mapping[cat] = section_name
    return mapping


def _overrides_to_map(overrides):
    """Normalize the override list into {(manufacturer, model): category}."""
    out = {}
    for o in overrides or []:
        key = (o.get("manufacturer") or "", o.get("model") or "")
        out[key] = (o.get("category") or "").strip()
    return out


def assemble_from_breakdown(rows, period_start, overrides=None):
    """Build the billing report from breakdown `rows`, applying `overrides`.

    `overrides` is a list of {manufacturer, model, category}; an empty category
    means "no billable category" (falls to the unmapped diagnostic). Pure — no
    DB access — so it is unit-testable and reused for in-session recompute.
    """
    ovr = _overrides_to_map(overrides)
    cat_to_section = _category_to_section()

    # Sum event counts into each billable section using the effective category.
    section_events = {
        name: {"receive": 0, "qc": 0, "shipping": 0}
        for name in osl_schedule.OSL_SECTION_CATEGORIES
    }
    unmapped = 0
    for r in rows:
        key = (r.get("manufacturer") or "", r.get("model") or "")
        cat = ovr[key] if key in ovr else (r.get("category") or "").strip()
        section = cat_to_section.get(cat)
        if section is None:
            unmapped += int(r.get("touch") or 0)
            continue
        ev = section_events[section]
        ev["receive"] += int(r.get("receive") or 0)
        ev["qc"] += int(r.get("qc") or 0)
        ev["shipping"] += int(r.get("shipping") or 0)

    sections_out = []
    grand_total_auto = 0.0
    for section in osl_schedule.OSL_FEE_SCHEDULE:
        events = section_events.get(section["name"])
        line_items = []
        section_total = 0.0
        for item in section["items"]:
            if item["mode"] == "count":
                ev_key = _EVENT_BY_COLUMN[item["column"]]
                units = events[ev_key] if events else 0
                charge = units * item["fee"]
                line_items.append({
                    "label": item["label"], "units": units,
                    "fee": item["fee"], "charge": charge, "mode": "count",
                })
                section_total += charge
                grand_total_auto += charge
            else:  # manual
                line_items.append({
                    "label": item["label"], "units": None,
                    "fee": item["fee"], "charge": 0, "mode": "manual",
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
        "diagnostics": {"unmapped_in_month": unmapped},
    }


def generate(year, month, overrides=None, models=None, conn_factory=get_db_connection):
    """Return {'report', 'models'} for the period.

    On the initial call `models` is None and the breakdown is fetched from the
    DB. For in-session recompute the caller passes back the cached `models` plus
    `overrides`, so no DB round-trip is needed — assembly is pure Python.
    """
    start, _ = _period_bounds(int(year), int(month))
    if models is None:
        models = get_model_breakdown(year, month, conn_factory=conn_factory)
    report = assemble_from_breakdown(models, start, overrides)
    return {"report": report, "models": models}
