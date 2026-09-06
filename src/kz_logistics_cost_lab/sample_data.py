"""Deterministic synthetic samples. --check compares; it never rewrites files."""
import argparse
import csv
from io import StringIO
from pathlib import Path

from .io import SHIPMENT_COLUMNS, PACKAGE_COLUMNS, TARIFF_COLUMNS

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "data" / "sample"
CASE_NAMES = ("CONSOLIDATION_SAVING", "DEADLINE_GUARD", "VOLUMETRIC_WEIGHT", "MISSING_DIMENSION", "NO_SAVING", "INCOMPATIBLE", "SERVICE_CHANGE")


def csv_bytes(columns, rows) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def encode(shipments, packages, tariffs) -> dict[str, bytes]:
    return {"shipments.csv": csv_bytes(SHIPMENT_COLUMNS, shipments),
            "packages.csv": csv_bytes(PACKAGE_COLUMNS, packages),
            "tariffs.csv": csv_bytes(TARIFF_COLUMNS, tariffs)}


def shipment(sid="0001", **changes):
    row = dict(zip(SHIPMENT_COLUMNS, (sid, "ORD-" + sid, "C-001", "D-001", "NORD", "2026-09-01T08:00:00+02:00", "2026-09-01T09:00:00+02:00", "2026-09-02", "LINEA", "standard", "true"), strict=True))
    return row | changes


def package(pid="P-0001", sid="0001", **changes):
    return dict(zip(PACKAGE_COLUMNS, (pid, sid, "12", "40", "30", "20"), strict=True)) | changes


def tariff(tid="T-LINEA", service="LINEA", **changes):
    return dict(zip(TARIFF_COLUMNS, (tid, service, "NORD", "2026-01-01", "2026-12-31", "EUR", "6.00", "0.4000", "5000", "1", "0", "100", "200", "500", "50", "1", "12:00"), strict=True)) | changes


def micro_rows(name):
    shipments = [shipment(), shipment("0002")]
    packages = [package(), package("P-0002", "0002", actual_weight_kg="8")]
    tariffs = [tariff()]
    if name == "DEADLINE_GUARD":
        tariffs.append(tariff("T-LENTO", "LENTO", fixed_fee_eur="1.00", per_kg_eur="0.1000", transit_business_days="2"))
    elif name == "VOLUMETRIC_WEIGHT":
        shipments = shipments[:1]
        packages = [package(actual_weight_kg="2", length_cm="60", width_cm="40", height_cm="40")]
    elif name == "MISSING_DIMENSION":
        packages[1]["height_cm"] = ""
    elif name == "NO_SAVING":
        tariffs[0]["fixed_fee_eur"] = "0.00"
    elif name == "INCOMPATIBLE":
        shipments += [shipment("0003", consolidation_allowed="false"), shipment("0004", handling_class="bulky")]
        shipments[1]["destination_id"] = "D-002"
        packages += [package("P-0003", "0003"), package("P-0004", "0004")]
    elif name == "SERVICE_CHANGE":
        for row in shipments:
            row["current_service_id"] = "PREMIUM"
        tariffs.append(tariff("T-PREMIUM", "PREMIUM", fixed_fee_eur="10.00", per_kg_eur="0.5000"))
    elif name != "CONSOLIDATION_SAVING":
        raise ValueError("Microcaso sconosciuto: " + name)
    return shipments, packages, tariffs


def demo_rows():
    shipments, packages, tariffs = [], [], []
    days = ("2026-09-01", "2026-09-02", "2026-09-03", "2026-09-08")
    for i in range(200):
        key = i // 5
        sid = f"S-{i + 1:04d}"
        day = days[key % 4]
        promise = {"2026-09-01": "2026-09-02", "2026-09-02": "2026-09-03", "2026-09-03": "2026-09-04", "2026-09-08": "2026-09-09"}[day] if key % 3 == 0 else {"2026-09-01": "2026-09-04", "2026-09-02": "2026-09-07", "2026-09-03": "2026-09-08", "2026-09-08": "2026-09-11"}[day]
        row = shipment(sid, order_id=f"O-{i // 2 + 1:04d}", customer_id=f"C-{key // 2 + 1:03d}", destination_id=f"D-{key + 1:03d}",
                       zone=("NORD", "CENTRO")[key % 2], ready_at=day + "T08:00:00+02:00", dispatch_at=day + "T09:00:00+02:00",
                       promised_delivery_date=promise, current_service_id=("RAPIDO", "LINEA", "ECONOMIA")[i % 3],
                       consolidation_allowed="false" if i % 11 == 0 else "true")
        if i % 37 == 0:
            row["handling_class"] = "bulky"
        if i % 67 == 1:
            row["current_service_id"] = "NON_COPERTO"
        shipments.append(row)
        for j in range(1 + (i % 4 < 3)):
            p = package(f"P-{i + 1:04d}-{j + 1}", sid, actual_weight_kg=str(2 + (i * 7 + j * 3) % 19),
                        length_cm=str(30 + (i % 4) * 10), width_cm="30", height_cm=str(20 + (i % 3) * 10))
            if i % 53 == 2 and j == 0:
                p["height_cm"] = ""
            packages.append(p)
    for zone in ("NORD", "CENTRO"):
        for service, fixed, rate, days, cutoff, max_packages in (("LINEA", "6.00", "0.4000", "1", "12:00", "12"),
                                                               ("ECONOMIA", "3.00", "0.2500", "2", "12:00", "6"),
                                                               ("RAPIDO", "9.00", "0.6000", "0", "16:00", "12")):
            tariffs.append(tariff(f"T-{service}-{zone}", service, zone=zone, fixed_fee_eur=fixed, per_kg_eur=rate,
                                  fuel_pct="5.0000" if zone == "CENTRO" else "0", max_package_weight_kg="50", max_package_longest_side_cm="120",
                                  max_shipment_actual_weight_kg="120", max_packages=max_packages, transit_business_days=days, cutoff_local_time=cutoff))
    return shipments, packages, tariffs


def generated_samples():
    result = {"demo": encode(*demo_rows())}
    result.update({name: encode(*micro_rows(name)) for name in CASE_NAMES})
    return result


def read_sample(name="demo") -> dict[str, bytes]:
    if name not in ("demo", *CASE_NAMES):
        raise ValueError("Sample sconosciuto.")
    return {file: (SAMPLE_ROOT / name / file).read_bytes() for file in ("shipments.csv", "packages.csv", "tariffs.csv")}


def check_samples(root: Path = SAMPLE_ROOT) -> tuple[str, ...]:
    differences = []
    for name, files in generated_samples().items():
        for filename, expected in files.items():
            path = root / name / filename
            if not path.exists() or path.read_bytes().replace(b"\r\n", b"\n") != expected:
                differences.append(f"{name}/{filename}")
    return tuple(differences)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--generate", action="store_true")
    args = parser.parse_args()
    if args.check:
        differences = check_samples()
        if differences:
            print("Sample diversi o mancanti: " + ", ".join(differences))
            raise SystemExit(1)
        print("Sample verificati senza riscritture: demo + 7 microcasi.")
    else:
        for name, files in generated_samples().items():
            directory = SAMPLE_ROOT / name
            directory.mkdir(parents=True, exist_ok=True)
            for filename, content in files.items():
                (directory / filename).write_bytes(content)
        print("Generati esclusivamente sample sintetici in data/sample.")


if __name__ == "__main__":
    main()
