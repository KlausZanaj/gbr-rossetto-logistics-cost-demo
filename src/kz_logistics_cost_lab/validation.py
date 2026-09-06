"""Data contract: structural failures block; other shipment failures exclude."""
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timezone
from decimal import Decimal

from .domain import Inputs, Issue, ModelConfig, Package, Shipment, Tariff, ValidatedData


def identifier(value: str) -> str:
    if not value or value != value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError("Identificativo richiesto, senza spazi iniziali/finali o caratteri di controllo; nessuna correzione automatica.")
    return value


def decimal_value(value: str, *, positive=False, places=None, maximum=None) -> Decimal:
    if not re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError("Richiesto decimale finito con punto; vietati NaN, Infinity, notazione scientifica e spazi.")
    result = Decimal(value)
    if result < 0 or (positive and result <= 0):
        raise ValueError("Valore strettamente positivo richiesto." if positive else "Valore non negativo richiesto.")
    if places is not None and -result.as_tuple().exponent > places:
        raise ValueError(f"Massimo {places} cifre decimali.")
    if maximum is not None and result > maximum:
        raise ValueError(f"Valore massimo {maximum}.")
    return result


def date_value(value: str) -> date:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Data richiesta in formato YYYY-MM-DD.")
    return date.fromisoformat(value)


def instant_value(value: str) -> datetime:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?(?:Z|[+-][0-9]{2}:[0-9]{2})", value):
        raise ValueError("Richiesto istante ISO 8601 con T e offset esplicito o Z (precisione massima microsecondi).")
    if value[-6:-5] in ("+", "-") and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
        raise ValueError("Offset non valido.")
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def time_value(value: str) -> time:
    if not re.fullmatch(r"[0-9]{2}:[0-9]{2}", value):
        raise ValueError("Ora richiesta in formato HH:MM.")
    return time.fromisoformat(value)


def integer_value(value: str, minimum: int) -> int:
    if not re.fullmatch(r"[0-9]+", value) or int(value) < minimum:
        raise ValueError(f"Richiesto intero >= {minimum}.")
    return int(value)


def enum_value(value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise ValueError("Valori ammessi: " + ", ".join(allowed))
    return value


def validate(inputs: Inputs, config: ModelConfig) -> ValidatedData:
    issues = list(inputs.issues)
    invalid: set[str] = set()
    shipments, packages, tariffs = [], [], []
    if any(i.severity == "BLOCK" for i in issues):
        return ValidatedData(inputs, (), (), (), tuple(issues), frozenset())
    shipment_table = inputs.table("shipments.csv")
    source_ids = {r["shipment_id"] for r in shipment_table.records()}
    for table, key in ((shipment_table, "shipment_id"), (inputs.table("packages.csv"), "package_id"), (inputs.table("tariffs.csv"), "tariff_id")):
        counts = Counter(r[key] for r in table.records())
        for row_number, record in zip(table.line_numbers, table.records(), strict=True):
            value = record[key]
            sid = record.get("shipment_id", "")
            if not value or not value.strip() or counts[value] > 1:
                issues.append(Issue("BLOCK", "PRIMARY_ID", "ID primario mancante o duplicato.", table.name, row_number, sid, key))
    destinations: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for r in shipment_table.records():
        if r["destination_id"]:
            destinations[r["destination_id"]].add((r["customer_id"], r["zone"]))
    for destination, owners in sorted(destinations.items()):
        if len(owners) > 1:
            issues.append(Issue("BLOCK", "DESTINATION_CONFLICT", f"Destinazione {destination} associata a clienti o zone diversi.", "shipments.csv", field="destination_id"))

    def parse(record, rules, filename, row_number, sid="", tariff=False):
        parsed = {}
        for field, parser in rules.items():
            try:
                parsed[field] = parser(record[field])
            except (ValueError, OverflowError) as exc:
                issues.append(Issue("BLOCK" if tariff else "EXCLUDE", "INVALID_VALUE", str(exc), filename, row_number, sid, field))
                if sid:
                    invalid.add(sid)
        return parsed if len(parsed) == len(rules) else None

    shipment_rules = {key: identifier for key in ("shipment_id", "order_id", "customer_id", "destination_id", "zone", "current_service_id")}
    shipment_rules.update(ready_at=instant_value, dispatch_at=instant_value, promised_delivery_date=date_value,
                          handling_class=lambda v: enum_value(v, ("standard", "bulky", "installation", "special")),
                          consolidation_allowed=lambda v: enum_value(v, ("true", "false")) == "true")
    for number, record in zip(shipment_table.line_numbers, shipment_table.records(), strict=True):
        sid = record["shipment_id"]
        values = parse(record, shipment_rules, shipment_table.name, number, sid)
        if values is not None:
            shipment = Shipment(**values)
            shipments.append(shipment)
            if shipment.ready_at > shipment.dispatch_at:
                invalid.add(sid)
                issues.append(Issue("EXCLUDE", "NOT_READY", "Merce pronta dopo la partenza.", shipment_table.name, number, sid, "ready_at"))
            try:
                local_dispatch_day = shipment.dispatch_at.astimezone(config.timezone).date()
            except OverflowError:
                invalid.add(sid)
                issues.append(Issue("EXCLUDE", "DATE_RANGE", "Partenza oltre l'intervallo di date locali rappresentabile.", shipment_table.name, number, sid, "dispatch_at"))
                continue
            if shipment.promised_delivery_date < local_dispatch_day:
                invalid.add(sid)
                issues.append(Issue("EXCLUDE", "INVALID_PROMISE", "Promessa precedente al giorno locale di partenza.", shipment_table.name, number, sid, "promised_delivery_date"))
        # Keep this reason even when another invalid cell prevents model construction.
        if record["handling_class"] in ("bulky", "installation", "special"):
            issues.append(Issue("EXCLUDE", "OUT_OF_SCOPE", "Gestione non standard fuori perimetro: " + record["handling_class"], shipment_table.name, number, sid, "handling_class"))

    package_table = inputs.table("packages.csv")
    package_counts = Counter(r["shipment_id"] for r in package_table.records())
    package_rules = {"package_id": identifier, "shipment_id": identifier}
    package_rules.update({key: lambda v: decimal_value(v, positive=True) for key in ("actual_weight_kg", "length_cm", "width_cm", "height_cm")})
    for number, record in zip(package_table.line_numbers, package_table.records(), strict=True):
        sid = record["shipment_id"]
        if sid not in source_ids:
            issues.append(Issue("BLOCK", "ORPHAN_PACKAGE", "Il collo non è collegabile a una spedizione esistente.", package_table.name, number, sid, "shipment_id"))
        values = parse(record, package_rules, package_table.name, number, sid)
        if values is not None:
            packages.append(Package(**values))
    for sid in sorted(source_ids):
        if not package_counts[sid]:
            invalid.add(sid)
            issues.append(Issue("EXCLUDE", "NO_PACKAGES", "Spedizione senza colli.", "shipments.csv", shipment_id=sid))

    tariff_rules = {key: identifier for key in ("tariff_id", "service_id", "zone")}
    tariff_rules.update(valid_from=date_value, valid_to=date_value, currency=lambda v: enum_value(v, ("EUR",)),
                        fixed_fee_eur=lambda v: decimal_value(v, places=2), per_kg_eur=lambda v: decimal_value(v, places=4),
                        fuel_pct=lambda v: decimal_value(v, places=4, maximum=Decimal(100)),
                        max_packages=lambda v: integer_value(v, 1), transit_business_days=lambda v: integer_value(v, 0),
                        cutoff_local_time=time_value)
    tariff_rules.update({key: lambda v: decimal_value(v, positive=True) for key in (
        "volumetric_divisor_cm3_per_kg", "billing_increment_kg", "max_package_weight_kg", "max_package_longest_side_cm", "max_shipment_actual_weight_kg")})
    tariff_table = inputs.table("tariffs.csv")
    for number, record in zip(tariff_table.line_numbers, tariff_table.records(), strict=True):
        values = parse(record, tariff_rules, tariff_table.name, number, tariff=True)
        if values is not None:
            tariff = Tariff(**values)
            tariffs.append(tariff)
            if tariff.valid_from > tariff.valid_to:
                issues.append(Issue("BLOCK", "INVALID_PERIOD", "Inizio validità successivo alla fine.", tariff_table.name, number, field="valid_from"))
    by_service = defaultdict(list)
    for tariff in tariffs:
        by_service[tariff.service_id, tariff.zone].append(tariff)
    for key, periods in sorted(by_service.items()):
        latest_end = None
        for tariff in sorted(periods, key=lambda t: (t.valid_from, t.valid_to, t.tariff_id)):
            if latest_end is not None and tariff.valid_from <= latest_end:
                issues.append(Issue("BLOCK", "OVERLAPPING_TARIFFS", f"Periodi inclusivi sovrapposti per {key}: {tariff.tariff_id}.", "tariffs.csv"))
            latest_end = max(latest_end or tariff.valid_to, tariff.valid_to)
    return ValidatedData(inputs, tuple(sorted(shipments, key=lambda s: s.shipment_id)), tuple(sorted(packages, key=lambda p: p.package_id)),
                         tuple(sorted(tariffs, key=lambda t: (t.service_id, t.tariff_id))), tuple(issues), frozenset(invalid))
