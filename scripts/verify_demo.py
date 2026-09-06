"""Repeatable demo/golden/XLSX verification; generated outputs stay ignored."""
from io import BytesIO
from pathlib import Path
import json
from decimal import Decimal
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from kz_logistics_cost_lab.domain import ModelConfig
from kz_logistics_cost_lab.excel import make_workbook, SHEETS
from kz_logistics_cost_lab.io import load_inputs
from kz_logistics_cost_lab.optimization import analyze, verify_invariants
from kz_logistics_cost_lab.reporting import summary
from kz_logistics_cost_lab.sample_data import read_sample, check_samples
from kz_logistics_cost_lab.validation import validate


def main():
    if check_samples():
        raise SystemExit("Sample diversi: eseguire --check e indagare senza rigenerazione automatica.")
    config = ModelConfig()
    report = {}
    for name in ("demo", "CONSOLIDATION_SAVING"):
        result = analyze(validate(load_inputs(read_sample(name)), config), config)
        if result.data.blocked:
            raise AssertionError(result.issues)
        verify_invariants(result)
        report[name] = summary(result)
        if name == "CONSOLIDATION_SAVING":
            assert tuple(report[name][k] for k in ("c0_cents", "c1_cents", "c2_cents", "saving_cents", "comparable", "groups", "packages")) == (2000, 2000, 1400, 600, 2, 1, 2)
        else:
            blob = make_workbook(result)
            ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            with ZipFile(BytesIO(blob)) as archive:
                assert archive.testzip() is None
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                assert [s.attrib["name"] for s in workbook.findall("m:sheets/m:sheet", ns)] == list(SHEETS)
                sheet = ET.fromstring(archive.read("xl/worksheets/sheet6.xml"))
                for ref, key in (("B2", "c0_eur"), ("B3", "c1_eur"), ("B4", "c2_eur")):
                    cell = sheet.find(f".//m:c[@r='{ref}']", ns)
                    assert Decimal(cell.findtext("m:v", namespaces=ns)) == report[name][key]
                    assert cell.find("m:f", ns) is not None
            output = Path(__file__).resolve().parents[1] / "outputs"
            output.mkdir(exist_ok=True)
            (output / "kz-logistics-report.xlsx").write_bytes(blob)
    (output / "verification.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")
    print(json.dumps(report, default=str, indent=2))
    print("XLSX: 8 fogli, ZIP integro, formule cached C0/C1/C2 riconciliate con il motore.")


if __name__ == "__main__":
    main()
