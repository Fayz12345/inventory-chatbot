"""TMS billing fee schedule — sections -> line items, as structured data.

Verified against dbo.ReportingInventoryFlat_TMS on 2026-05-29.
Receipt_Type values use REAL DB spellings (e.g. 'Buyers Remorse', no apostrophe).

Item fields:
  label            : str  — line item name shown in the report
  column           : str|None — flat-table datetime column to count (None for manual)
  receipt_type     : str|list[str]|None — Receipt_Type filter
  manufacturer     : str|None — ManufacturerVerb filter value
  manufacturer_op  : '='|'<>' — comparison for manufacturer (ignored if manufacturer is None)
  fee              : float|None — $ per unit (None = editable/TBD manual item)
  mode             : 'count' | 'sum_repair_fee' | 'manual'
"""

# Datetime columns we are allowed to COUNT over (defense-in-depth allowlist;
# values are developer-controlled, never user input).
COUNT_COLUMNS = {
    "ReceiveDate",
    "MSC_Repair_Handling_Created",
    "Shipping_TMS_Created",
    "QC_Assessment_Created",
    "Discrepancy_Created",
    "SKU_Transfer_Created",
    "RQ4_SKU_Change_Created",
    "Subsidy_Created",
    "Device_Enrollment_Created",
    "Lab_Billing_Created",
}


def _count(label, column, fee, receipt_type=None, manufacturer=None,
           manufacturer_op="="):
    return {
        "label": label, "column": column, "receipt_type": receipt_type,
        "manufacturer": manufacturer, "manufacturer_op": manufacturer_op,
        "fee": float(fee), "mode": "count",
    }


def _manual(label, fee):
    return {
        "label": label, "column": None, "receipt_type": None,
        "manufacturer": None, "manufacturer_op": "=",
        "fee": None if fee is None else float(fee), "mode": "manual",
    }


def _repair(label):
    return {
        "label": label, "column": "Lab_Billing_Created", "receipt_type": None,
        "manufacturer": None, "manufacturer_op": "=",
        "fee": None, "mode": "sum_repair_fee",
    }


TMS_FEE_SCHEDULE = [
    {"name": "In Warranty Rx", "items": [
        _count("Receive", "ReceiveDate", 2.75, receipt_type="In Warranty"),
        _count("Handle Repair at MSC", "MSC_Repair_Handling_Created", 2.75),
        _count("Return Device to Store", "Shipping_TMS_Created", 2.75,
               receipt_type="In Warranty"),
    ]},
    {"name": "Out of Warranty", "items": [
        _repair("Repair (SUM of Repair_Fee)"),
    ]},
    {"name": "DOA", "items": [
        _count("Receive", "ReceiveDate", 3.30, receipt_type="DOA"),
        _count("Create RMA Where applicable", "Shipping_TMS_Created", 5.23,
               receipt_type="DOA"),
        _count("Data Wipe", "QC_Assessment_Created", 3.85, receipt_type="DOA"),
    ]},
    {"name": "Buyers Remorse", "items": [
        _count("Receive", "ReceiveDate", 3.30, receipt_type="Buyers Remorse"),
        _count("QC", "QC_Assessment_Created", 3.85, receipt_type="Buyers Remorse"),
    ]},
    {"name": "Inventory", "items": [
        _count("Receive", "ReceiveDate", 3.85, receipt_type="Inventory"),
        _count("Ship", "Shipping_TMS_Created", 2.75, receipt_type="Inventory"),
    ]},
    {"name": "Loaner Processing", "items": [
        _count("Receive", "ReceiveDate", 2.75, receipt_type="Loaner"),
        _count("Data Wipe / QC", "QC_Assessment_Created", 3.85, receipt_type="Loaner"),
        _count("Ship", "Shipping_TMS_Created", 3.30, receipt_type="Loaner"),
    ]},
    {"name": "Demo", "items": [
        _count("Receive", "ReceiveDate", 2.75, receipt_type="Demo"),
        _count("Wipe and QC", "QC_Assessment_Created", 3.85, receipt_type="Demo"),
        _count("Ship", "Shipping_TMS_Created", 1.65, receipt_type="Demo"),
    ]},
    {"name": "Accessories", "items": [
        _manual("Accessories", 1.38),
    ]},
    {"name": "Discrepancies", "items": [
        _count("Per Item", "Discrepancy_Created", 7.70),
    ]},
    {"name": "RQ4 SKU Transfer", "items": [
        _count("Transactions", "SKU_Transfer_Created", 3.30),
    ]},
    {"name": "RQ4 SKU Change", "items": [
        _count("Transactions", "RQ4_SKU_Change_Created", 1.10),
    ]},
    {"name": "Open Box Transfer", "items": [
        # Excel's "Rejected" criterion is a wildcard that also catches "Rejected RMA".
        _count("Package as per requirements", "Shipping_TMS_Created", 3.30,
               receipt_type=["Buyers Remorse", "Rejected", "Rejected RMA"]),
    ]},
    {"name": "RMA", "items": [
        _count("Receiving", "ReceiveDate", 3.85, receipt_type="RMA"),
        _manual("Shipping to store", 2.75),
        _manual("Shipping to carriers", 1.65),
    ]},
    {"name": "Kitting", "items": [
        _manual("Accessories Added", 11.00),
    ]},
    {"name": "Subsidy Check", "items": [
        _count("Subsidy Check", "Subsidy_Created", 1.10),
    ]},
    {"name": "Bridge Fulfillment Service", "items": [
        _manual("Bridge Fulfillment Service", 28.60),
    ]},
    {"name": "Accessories Receive (Fulfillment)", "items": [
        _manual("Accessories Receive", 0.55),
    ]},
    {"name": "Sim Card Receive (Fulfillment)", "items": [
        _manual("Sim Card Receive", 0.11),
    ]},
    {"name": "Android Device Enrollment", "items": [
        _count("Other (non-Samsung)", "Device_Enrollment_Created", 6.60,
               manufacturer="Samsung", manufacturer_op="<>"),
        _count("Samsung", "Subsidy_Created", 7.70,
               manufacturer="Samsung", manufacturer_op="="),
    ]},
    {"name": "TMS Inventory Tasks Management", "items": [
        _manual("TMS Inventory Tasks", None),
    ]},
    {"name": "Buffing Services", "items": [
        _manual("Buffing", None),
    ]},
]
