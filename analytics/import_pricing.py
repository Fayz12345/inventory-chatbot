"""
One-time import: reads the 'DO NOT EDIT' sheet from the Telus pricing Excel
file and bulk-inserts rows into TelusWeeklyPricingMaster.

Usage:
    python -m analytics.import_pricing '/path/to/telus pricing Demo api.xlsm'
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import openpyxl
from analytics import db


def import_from_excel(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb['DO NOT EDIT']

    rows_imported = 0
    skipped = 0

    for row in ws.iter_rows(min_row=2, values_only=False):
        model = row[3].value    # column D
        grade_a = row[4].value  # column E
        grade_b = row[5].value  # column F
        grade_c = row[6].value  # column G
        defective = row[7].value  # column H
        frp = row[8].value      # column I
        device_type = row[11].value  # column L

        if not model or str(model).strip() == '':
            skipped += 1
            continue

        model = str(model).strip()
        grade_a = float(grade_a or 0)
        grade_b = float(grade_b or 0)
        grade_c = float(grade_c or 0)
        defective = float(defective or 0)
        frp = float(frp or 0)
        device_type = str(device_type or 'Phone').strip()

        try:
            db.insert_pricing_model(
                model, grade_a, grade_b, grade_c,
                defective, frp, device_type,
            )
            rows_imported += 1
        except Exception as e:
            if 'UNIQUE' in str(e).upper() or 'duplicate' in str(e).lower():
                skipped += 1
            else:
                print(f"Error inserting '{model}': {e}")
                skipped += 1

    wb.close()
    print(f"Import complete: {rows_imported} inserted, {skipped} skipped")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python -m analytics.import_pricing <path-to-xlsm>")
        sys.exit(1)
    import_pricing_path = sys.argv[1]
    if not os.path.exists(import_pricing_path):
        print(f"File not found: {import_pricing_path}")
        sys.exit(1)
    import_from_excel(import_pricing_path)
