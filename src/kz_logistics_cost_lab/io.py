"""Strict, lossless CSV parsing. Caller supplies bytes, never upload paths."""
import csv
import hashlib
from io import StringIO
from collections.abc import Mapping

from .domain import Inputs, Issue, RawTable

SHIPMENT_COLUMNS = tuple("shipment_id,order_id,customer_id,destination_id,zone,ready_at,dispatch_at,promised_delivery_date,current_service_id,handling_class,consolidation_allowed".split(","))
PACKAGE_COLUMNS = tuple("package_id,shipment_id,actual_weight_kg,length_cm,width_cm,height_cm".split(","))
TARIFF_COLUMNS = tuple("tariff_id,service_id,zone,valid_from,valid_to,currency,fixed_fee_eur,per_kg_eur,volumetric_divisor_cm3_per_kg,billing_increment_kg,fuel_pct,max_package_weight_kg,max_package_longest_side_cm,max_shipment_actual_weight_kg,max_packages,transit_business_days,cutoff_local_time".split(","))
SCHEMAS = (("shipments.csv", SHIPMENT_COLUMNS), ("packages.csv", PACKAGE_COLUMNS), ("tariffs.csv", TARIFF_COLUMNS))
FORMAT_HELP = "Richiesti UTF-8, virgola separatrice, punto decimale e quoting CSV standard; esportazioni con punto e virgola o virgola decimale vanno convertite esplicitamente."


def _check_quotes(text: str) -> None:
    # csv.reader(strict=True) still accepts bare quotes inside unquoted fields.
    # This small lexical check closes that gap, including multiline quoted cells.
    state = "start"
    for char in text:
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed":
            if char == '"':
                state = "quoted"
            elif char in ",\r\n":
                state = "start"
            else:
                raise ValueError("Caratteri dopo la chiusura delle virgolette.")
        elif char == '"':
            if state != "start":
                raise ValueError("Virgolette in un campo non quotato.")
            state = "quoted"
        elif char in ",\r\n":
            state = "start"
        else:
            state = "plain"
    if state == "quoted":
        raise ValueError("Campo quotato non chiuso.")


def load_inputs(files: Mapping[str, bytes]) -> Inputs:
    tables, hashes, issues = [], [], []
    for name, required in SCHEMAS:
        if name not in files or not isinstance(files[name], bytes):
            issues.append(Issue("BLOCK", "MISSING_FILE", "File mancante o illeggibile.", name))
            continue
        raw = files[name]
        hashes.append((name, hashlib.sha256(raw).hexdigest()))
        try:
            decoded = raw.decode("utf-8-sig")
            if "\x00" in decoded:
                raise ValueError("Carattere NUL non ammesso.")
            _check_quotes(decoded)
            reader = csv.reader(StringIO(decoded, newline=""), strict=True)
            columns = tuple(next(reader, []))
            if not columns or any(not c.strip() for c in columns) or len(set(columns)) != len(columns):
                issues.append(Issue("BLOCK", "INVALID_HEADER", "Intestazione vuota o duplicata. " + FORMAT_HELP, name, 1))
                continue
            missing = sorted(set(required) - set(columns))
            if missing:
                issues.append(Issue("BLOCK", "MISSING_COLUMNS", "Colonne mancanti: " + ", ".join(missing) + ". " + FORMAT_HELP, name, 1))
                continue
            extra = sorted(set(columns) - set(required))
            if extra:
                issues.append(Issue("INFO", "EXTRA_COLUMNS", "Colonne ignorate dal motore e conservate nell'export: " + ", ".join(extra), name, 1))
            rows, numbers = [], []
            for record in reader:
                if record == []:  # Only truly empty physical records are ignored.
                    continue
                if len(record) != len(columns):
                    issues.append(Issue("BLOCK", "FIELD_COUNT", f"Attesi {len(columns)} campi, trovati {len(record)}. " + FORMAT_HELP, name, reader.line_num))
                else:
                    rows.append(tuple(record))
                    numbers.append(reader.line_num)
            tables.append(RawTable(name, columns, tuple(rows), tuple(numbers)))
        except (UnicodeError, csv.Error, ValueError) as exc:
            issues.append(Issue("BLOCK", "INVALID_CSV", str(exc) + " " + FORMAT_HELP, name))
    unexpected = sorted(set(files) - {name for name, _ in SCHEMAS})
    if unexpected:
        issues.append(Issue("BLOCK", "UNEXPECTED_FILE", "File inattesi: " + ", ".join(unexpected)))
    return Inputs(tuple(tables), tuple(hashes), tuple(issues))
