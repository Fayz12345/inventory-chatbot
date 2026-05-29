from billing import schedule


def test_columns_allowlist_covers_all_count_items():
    """Every count line item must reference a column in COUNT_COLUMNS."""
    for section in schedule.TMS_FEE_SCHEDULE:
        for item in section["items"]:
            if item["mode"] == "count":
                assert item["column"] in schedule.COUNT_COLUMNS, (
                    f"{item['label']} uses unlisted column {item['column']}"
                )


def test_item_shape_is_valid():
    valid_modes = {"count", "sum_repair_fee", "manual"}
    valid_ops = {"=", "<>"}
    for section in schedule.TMS_FEE_SCHEDULE:
        assert section["name"]
        assert section["items"]
        for item in section["items"]:
            assert item["mode"] in valid_modes
            assert item["label"]
            if item["mode"] == "count":
                assert item["column"]
                assert isinstance(item["fee"], float)
                if item["manufacturer"] is not None:
                    assert item["manufacturer_op"] in valid_ops
            if item["mode"] == "sum_repair_fee":
                assert item["column"] == "Lab_Billing_Created"
            if item["mode"] == "manual":
                assert item["column"] is None
                # fee is float, or None for the two TBD items
                assert item["fee"] is None or isinstance(item["fee"], float)


def test_buyers_remorse_value_has_no_apostrophe():
    """Regression: the DB value is 'Buyers Remorse', not 'Buyer''s Remorse'."""
    receipt_values = []
    for section in schedule.TMS_FEE_SCHEDULE:
        for item in section["items"]:
            rt = item["receipt_type"]
            if isinstance(rt, list):
                receipt_values.extend(rt)
            elif rt:
                receipt_values.append(rt)
    assert "Buyers Remorse" in receipt_values
    assert "Buyer's Remorse" not in receipt_values


def test_open_box_transfer_uses_in_list():
    item = _find("Open Box Transfer", "Package as per requirements")
    assert item["receipt_type"] == ["Buyers Remorse", "Rejected"]


def test_android_enrollment_split():
    samsung = _find("Android Device Enrollment", "Samsung")
    other = _find("Android Device Enrollment", "Other (non-Samsung)")
    assert samsung["column"] == "Subsidy_Created"
    assert samsung["manufacturer"] == "Samsung" and samsung["manufacturer_op"] == "="
    assert other["column"] == "Device_Enrollment_Created"
    assert other["manufacturer"] == "Samsung" and other["manufacturer_op"] == "<>"


def _find(section_name, label):
    for section in schedule.TMS_FEE_SCHEDULE:
        if section["name"] == section_name:
            for item in section["items"]:
                if item["label"] == label:
                    return item
    raise AssertionError(f"not found: {section_name} / {label}")
