"""Build .xlsx downloads from query result sets (openpyxl).

Used by the billing raw-data download endpoints. Kept dependency-light: the
caller passes column names + row tuples straight from a cursor.
"""
import datetime
from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook


def _cell(value):
    """Coerce a DB value into something openpyxl can write."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value  # openpyxl writes these as native Excel dates
    return str(value)


def rows_to_xlsx(columns, rows, sheet_title="Data"):
    """Return .xlsx file bytes: a header row of `columns` then `rows`."""
    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_title or "Data")[:31]  # Excel sheet-name limit
    ws.append(list(columns))
    for row in rows:
        ws.append([_cell(v) for v in row])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()
