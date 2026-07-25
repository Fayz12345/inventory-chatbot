import datetime

from billing import osl


def _rows():
    return [
        {"manufacturer": "Apple", "model": "iPhone 14", "category": "Handset",
         "receive": 10, "qc": 10, "shipping": 8, "touch": 10},
        {"manufacturer": "Dell", "model": "XPS 13", "category": "Laptop",
         "receive": 5, "qc": 5, "shipping": 5, "touch": 5},
        {"manufacturer": "Anker", "model": "PowerCore", "category": "Charger",
         "receive": 3, "qc": 3, "shipping": 3, "touch": 4},
    ]


def _section(report, name):
    for s in report["sections"]:
        if s["name"] == name:
            return s
    raise AssertionError(f"section not found: {name}")


def test_assemble_baseline_charges_and_unmapped():
    rep = osl.assemble_from_breakdown(_rows(), datetime.date(2026, 3, 1))
    assert rep["period_label"] == "March 2026"
    mp = _section(rep, "Mobile Phones")
    # Receive 10*2.50, QC 10*6.00, Shipping 8*1.50 = 25 + 60 + 12
    assert [li["units"] for li in mp["line_items"]] == [10, 10, 8]
    assert round(mp["section_total"], 2) == 97.0
    # Laptops: 5*2.50 + 5*13.50 + 5*1.50
    assert round(_section(rep, "Laptops")["section_total"], 2) == 87.5
    # Charger has no billable section -> counted via `touch` in the diagnostic
    assert rep["diagnostics"]["unmapped_in_month"] == 4
    assert round(rep["grand_total_auto"], 2) == 184.5


def test_override_unmapped_into_a_section():
    ovr = [{"manufacturer": "Anker", "model": "PowerCore", "category": "Tablet"}]
    rep = osl.assemble_from_breakdown(_rows(), datetime.date(2026, 3, 1), overrides=ovr)
    twb = _section(rep, "Tablets, Wearables, Buds")
    # 3*2.50 + 3*6.00 + 3*1.50 = 30
    assert round(twb["section_total"], 2) == 30.0
    assert rep["diagnostics"]["unmapped_in_month"] == 0


def test_override_mapped_to_none_removes_charges():
    ovr = [{"manufacturer": "Apple", "model": "iPhone 14", "category": ""}]
    rep = osl.assemble_from_breakdown(_rows(), datetime.date(2026, 3, 1), overrides=ovr)
    assert round(_section(rep, "Mobile Phones")["section_total"], 2) == 0.0
    # phone touch (10) + charger touch (4)
    assert rep["diagnostics"]["unmapped_in_month"] == 14


def test_accessories_section_is_manual_only():
    rep = osl.assemble_from_breakdown(_rows(), datetime.date(2026, 3, 1))
    acc = _section(rep, "Accessories")
    assert all(li["mode"] == "manual" for li in acc["line_items"])
    assert all(li["units"] is None for li in acc["line_items"])


class _Cur:
    description = [("ManufacturerVerb",), ("Model",), ("Device_Handset",),
                   ("receive_ct",), ("qc_ct",), ("shipping_ct",), ("touch_ct",)]

    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, sql, params):
        self.sql, self.params = sql, params

    def fetchall(self):
        return [("Apple", "iPhone 14", "Handset", 2, 2, 1, 2)]


class _Conn:
    def __init__(self):
        self.cur = _Cur()

    def cursor(self):
        return self.cur

    def close(self):
        pass


def test_breakdown_sql_placeholders_balanced_and_grouped():
    conn = _Conn()
    rows = osl.get_model_breakdown(2026, 3, conn_factory=lambda: conn)
    assert conn.cur.sql.count("?") == len(conn.cur.params) == 18
    assert "GROUP BY f.ManufacturerVerb, f.Model, mcl.Device_Handset" in conn.cur.sql
    assert "READ UNCOMMITTED" in conn.cur.sql
    assert rows == [{"manufacturer": "Apple", "model": "iPhone 14",
                     "category": "Handset", "receive": 2, "qc": 2,
                     "shipping": 1, "touch": 2}]


def test_generate_with_cached_models_skips_db():
    rows = _rows()

    def _boom():
        raise AssertionError("DB should not be hit when models are provided")

    result = osl.generate(2026, 3, overrides=[], models=rows, conn_factory=_boom)
    assert result["models"] is rows
    assert round(result["report"]["grand_total_auto"], 2) == 184.5
