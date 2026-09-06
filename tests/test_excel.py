from io import BytesIO
from decimal import Decimal as D
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from xlsxwriter.utility import xl_col_to_name
import pytest

from kz_logistics_cost_lab.domain import ModelConfig
from kz_logistics_cost_lab.excel import make_workbook, SHEETS
from kz_logistics_cost_lab.io import load_inputs
from kz_logistics_cost_lab.optimization import analyze
from kz_logistics_cost_lab.reporting import summary, proposal_rows
from kz_logistics_cost_lab.sample_data import encode, micro_rows, demo_rows
from kz_logistics_cost_lab.validation import validate

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def result_for(rows):
    config = ModelConfig()
    return analyze(validate(load_inputs(encode(*rows)), config), config)


def contents(blob):
    archive = ZipFile(BytesIO(blob))
    strings = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    shared = ["".join(si.itertext()) for si in strings]
    sheets = {name: ET.fromstring(archive.read(f"xl/worksheets/sheet{index}.xml")) for index, name in enumerate(SHEETS, 1)}
    return archive, shared, sheets


def values(sheet, shared):
    cells = {}
    for cell in sheet.findall(".//m:sheetData/m:row/m:c", NS):
        value = cell.findtext("m:v", namespaces=NS)
        cells[cell.attrib["r"]] = shared[int(value)] if cell.attrib.get("t") == "s" else value
    return cells


def test_workbook_sheets_totals_cached_and_controlled_formulas():
    result = result_for(micro_rows("SERVICE_CHANGE"))
    archive, shared, sheets = contents(make_workbook(result))
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    assert [s.attrib["name"] for s in workbook.findall("m:sheets/m:sheet", NS)] == list(SHEETS)
    comparison = values(sheets["Confronto"], shared)
    assert {ref: D(comparison[ref]) for ref in ("B2", "B3", "B4", "B7", "B8", "B9", "B10", "B11")} == {
        "B2": D(30), "B3": D(20), "B4": D(14), "B7": D(10), "B8": D(6), "B9": D(16), "B10": D(16), "B11": D("0.5333333333333333")}
    assert comparison["F4"] == "14.0" and comparison["G4"] == "7.0"
    assert comparison["C2"] == "3000" and comparison["C4"] == "1400"
    assert values(sheets["Spedizioni"], shared)["A2"] == "0001"
    proposal = values(sheets["Proposte"], shared)
    assert D(proposal["Q2"]) == D(14) and proposal["W2"] == "1400"
    assert "xl/charts/chart1.xml" in archive.namelist()
    assert not any("externalLink" in name or "vbaProject" in name for name in archive.namelist())
    for name, sheet in sheets.items():
        assert sheet.find("m:autoFilter", NS) is not None
        assert sheet.find("m:sheetViews/m:sheetView/m:pane", NS) is not None
        assert not sheet.findall(".//m:c[@t='e']", NS)
        for cell in sheet.findall(".//m:c", NS):
            formula = cell.findtext("m:f", namespaces=NS)
            if formula is not None:
                assert name == "Confronto" and ";" not in formula and "[" not in formula
                assert cell.find("m:v", NS) is not None


@pytest.mark.parametrize("text", ["=1+1", "+SUM(1,2)", "-1+2", "@SUM(1)", "https://example.com", "N/A", "00001"])
def test_input_injection_remains_text(text):
    rows = micro_rows("CONSOLIDATION_SAVING")
    rows[0][0]["order_id"] = text
    archive, shared, sheets = contents(make_workbook(result_for(rows)))
    cell = sheets["Spedizioni"].find(".//m:c[@r='B2']", NS)
    assert cell.attrib["t"] == "s" and cell.find("m:f", NS) is None
    assert values(sheets["Spedizioni"], shared)["B2"] == text
    assert all(sheet.find("m:hyperlinks", NS) is None for sheet in sheets.values())


def test_demo_reconciles_engine_and_has_no_repeated_c2():
    result = result_for(demo_rows())
    archive, shared, sheets = contents(make_workbook(result))
    kpi = summary(result)
    values_c = values(sheets["Confronto"], shared)
    values_p = values(sheets["Proposte"], shared)
    for ref, key in (("B2", "c0_eur"), ("B3", "c1_eur"), ("B4", "c2_eur")):
        assert D(values_c[ref]) == kpi[key]
    cents = [int(value) for ref, value in values_p.items() if ref.startswith("W") and ref != "W1"]
    assert sum(cents) == kpi["c2_cents"] and len(cents) == len(result.groups)
    assert "C2_EUR" not in [value for ref, value in values_c.items() if ref.endswith("16")]
    for name, source in (("Spedizioni", "shipments.csv"), ("Colli", "packages.csv"), ("Tariffe", "tariffs.csv")):
        actual = values(sheets[name], shared)
        raw = result.data.inputs.table(source)
        for row_index, row in enumerate(raw.rows, 2):
            for col_index, expected in enumerate(row):
                ref = xl_col_to_name(col_index) + str(row_index)
                assert actual[ref] == expected, (name, ref)
                assert sheets[name].find(f".//m:c[@r='{ref}']", NS).attrib["t"] == "s"


@pytest.mark.parametrize("empty", [True, False])
def test_empty_or_free_do_not_have_fake_saving(empty):
    rows = ([], [], []) if empty else micro_rows("CONSOLIDATION_SAVING")
    if not empty:
        rows[2][0].update(fixed_fee_eur="0.00", per_kg_eur="0.0000")
    archive, shared, sheets = contents(make_workbook(result_for(rows)))
    cells = values(sheets["Confronto"], shared)
    assert cells["B11"] == "n.d."
    assert cells["B2"] == ("Non calcolabile" if empty else "0.0")
    assert cells["B9"] == ("n.d." if empty else "0.0")


def test_raw_extra_columns_and_configuration_hash():
    rows = micro_rows("CONSOLIDATION_SAVING")
    files = encode(*rows)
    lines = files["shipments.csv"].decode().splitlines()
    files["shipments.csv"] = (lines[0] + ",note\n" + "\n".join(s + ",=1+1" for s in lines[1:]) + "\n").encode()
    config = ModelConfig()
    result = analyze(validate(load_inputs(files), config), config)
    archive, shared, sheets = contents(make_workbook(result))
    assert values(sheets["Spedizioni"], shared)["L2"] == "=1+1"
    assert result.signature in shared
    assert all(digest in shared for name, digest in result.data.inputs.hashes)
