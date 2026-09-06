from dataclasses import replace
import pytest
from kz_logistics_cost_lab.io import load_inputs
from kz_logistics_cost_lab.sample_data import encode, shipment
from kz_logistics_cost_lab.validation import validate


def check(rows, config):
    return validate(load_inputs(encode(*rows)), config)


def test_quoted_bom_newlines_and_ids(rows, config):
    rows[0][0]["order_id"] = 'N/A, "null"'
    files = {k: b"\xef\xbb\xbf" + v.replace(b"\n", b"\r\n") for k, v in encode(*rows).items()}
    data = validate(load_inputs(files), config)
    assert not data.blocked
    assert data.shipments[0].shipment_id == "0001"
    assert data.shipments[0].order_id == 'N/A, "null"'


@pytest.mark.parametrize("bad", [b"\xff", b'a,b\n"unclosed', b'a,b\na"b,c', b'a,b\n"x"z,c'])
def test_invalid_encoding_and_quotes(rows, config, bad):
    files = encode(*rows) | {"shipments.csv": bad}
    assert validate(load_inputs(files), config).blocked


@pytest.mark.parametrize("mutation", ["missing_file", "missing_column", "duplicate_column", "empty_column", "extra_field", "short_record", "semicolon", "space_column"])
def test_structural_csv(rows, config, mutation):
    files = encode(*rows)
    content = files["shipments.csv"]
    if mutation == "missing_file":
        del files["shipments.csv"]
    else:
        header, rest = content.split(b"\n", 1)
        if mutation == "missing_column":
            header = header.replace(b"shipment_id", b"wrong")
        elif mutation == "duplicate_column":
            header = header.replace(b"order_id", b"shipment_id")
        elif mutation == "empty_column":
            header = header.replace(b"order_id", b"")
        elif mutation == "extra_field":
            rest = rest.replace(b"\n", b",extra\n", 1)
        elif mutation == "short_record":
            rest = b"onlyone\n"
        elif mutation == "semicolon":
            header = header.replace(b",", b";")
        elif mutation == "space_column":
            header = header.replace(b"order_id", b" order_id")
        files["shipments.csv"] = header + b"\n" + rest
    assert validate(load_inputs(files), config).blocked


def test_extra_column_is_preserved(rows, config):
    files = encode(*rows)
    lines = files["shipments.csv"].decode().splitlines()
    files["shipments.csv"] = (lines[0] + ",note\n" + "\n".join(line + ",=1+1" for line in lines[1:]) + "\n").encode()
    data = validate(load_inputs(files), config)
    assert not data.blocked
    assert data.inputs.table("shipments.csv").records()[0]["note"] == "=1+1"
    assert any(i.code == "EXTRA_COLUMNS" for i in data.issues)


@pytest.mark.parametrize("table,key", [(0, "shipment_id"), (1, "package_id"), (2, "tariff_id")])
def test_primary_duplicates_and_missing(rows, config, table, key):
    rows[table].append(dict(rows[table][0]))
    assert check(rows, config).blocked
    rows[table].pop()
    rows[table][0][key] = ""
    assert check(rows, config).blocked


def test_orphan_destination_conflict_and_no_packages(rows, config):
    rows[1][0]["shipment_id"] = "absent"
    assert check(rows, config).blocked
    rows[1][0]["shipment_id"] = "0001"
    rows[0][1]["customer_id"] = "different"
    assert check(rows, config).blocked
    rows[0][1]["customer_id"] = "C-001"
    rows[1].pop()
    data = check(rows, config)
    assert not data.blocked and "0002" in data.invalid_shipments


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "1e2", "1,2", " 1", "0", "-1", "null"])
def test_bad_package_values_exclude_parent(rows, config, value):
    rows[1][0]["length_cm"] = value
    data = check(rows, config)
    assert not data.blocked and data.invalid_shipments == {"0001"}


@pytest.mark.parametrize("field,value", [("fixed_fee_eur", "1.001"), ("per_kg_eur", "0.12345"), ("fuel_pct", "101"), ("max_packages", "1.0"), ("transit_business_days", "-1"), ("currency", "USD"), ("valid_to", "2025-01-01"), ("cutoff_local_time", "24:00"), ("billing_increment_kg", "0")])
def test_bad_tariffs_block(rows, config, field, value):
    rows[2][0][field] = value
    assert check(rows, config).blocked


def test_inclusive_period_overlap(rows, config):
    rows[2][0]["valid_to"] = "2026-09-01"
    rows[2].append(rows[2][0] | {"tariff_id": "second", "valid_from": "2026-09-01", "valid_to": "2026-12-31"})
    assert check(rows, config).blocked
    rows[2][1]["valid_from"] = "2026-09-02"
    assert not check(rows, config).blocked


@pytest.mark.parametrize("field,value", [("ready_at", "2026-09-01T09:01:00+02:00"), ("dispatch_at", "2026-09-01T09:00:00"), ("promised_delivery_date", "2026-08-31"), ("consolidation_allowed", "TRUE"), ("handling_class", "unknown"), ("order_id", " ORD")])
def test_bad_shipment_value_excludes(rows, config, field, value):
    rows[0][0][field] = value
    assert "0001" in check(rows, config).invalid_shipments


def test_empty_tables_are_valid(config):
    data = validate(load_inputs(encode([], [], [])), config)
    assert not data.blocked and not data.shipments
