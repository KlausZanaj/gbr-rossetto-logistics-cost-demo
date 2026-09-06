"""Exact per-package billing with local Decimal precision and explicit rejection."""
from dataclasses import fields
from decimal import Decimal, localcontext, ROUND_CEILING

from .calendar import arrival_date, is_working_day
from .domain import D, Evaluation, ModelConfig, Package, PackageCharge, PriceTrace, Shipment, Tariff


def precision_for(*objects) -> int:
    # Includes digits and scale of every input. This also protects quotients close
    # to a billing boundary and products/sums with very different magnitudes.
    total = 0
    for obj in objects:
        values = (obj,) if isinstance(obj, Decimal) else (getattr(obj, f.name) for f in fields(obj))
        for value in values:
            if isinstance(value, Decimal):
                total += len(value.as_tuple().digits) + abs(value.as_tuple().exponent)
    return max(80, total * 2 + 40)


def price(packages: tuple[Package, ...], tariff: Tariff, config: ModelConfig) -> PriceTrace:
    if not packages:
        raise ValueError("Impossibile tariffare una spedizione senza colli.")
    with localcontext() as context:
        context.prec = precision_for(tariff, *packages)
        charges = []
        for package in sorted(packages, key=lambda p: p.package_id):
            volume = package.length_cm * package.width_cm * package.height_cm
            volumetric = volume / tariff.volumetric_divisor_cm3_per_kg
            unrounded = max(package.actual_weight_kg, volumetric)
            billable = (unrounded / tariff.billing_increment_kg).to_integral_value(rounding=ROUND_CEILING) * tariff.billing_increment_kg
            charges.append(PackageCharge(package.package_id, package.actual_weight_kg, volume, volumetric, unrounded, billable))
        actual = sum((p.actual_weight_kg for p in packages), D(0))
        billable = sum((p.billable_weight_kg for p in charges), D(0))
        component = tariff.per_kg_eur * billable
        base = tariff.fixed_fee_eur + component
        fuel = base * tariff.fuel_pct / D(100)
        total = (base * (D(1) + tariff.fuel_pct / D(100))).quantize(D("0.01"), rounding=config.money_rounding)
        return PriceTrace(tariff.tariff_id, tuple(charges), actual, billable, tariff.fixed_fee_eur,
                          component, base, tariff.fuel_pct, fuel, total, int(total * 100))


def evaluate(shipments: tuple[Shipment, ...], packages: tuple[Package, ...], tariff: Tariff, config: ModelConfig) -> Evaluation:
    if not shipments:
        raise ValueError("Gruppo vuoto.")
    reasons = []
    first = shipments[0]
    local = first.dispatch_at.astimezone(config.timezone)
    if len({s.dispatch_at for s in shipments}) > 1:
        reasons.append("DIFFERENT_DISPATCH: istanti di partenza diversi")
    if any(s.zone != tariff.zone for s in shipments):
        reasons.append("ZONE: zona non coperta")
    if any(s.ready_at > s.dispatch_at for s in shipments):
        reasons.append("NOT_READY: merce non pronta")
    if not tariff.valid_from <= local.date() <= tariff.valid_to:
        reasons.append("NO_VALID_TARIFF: tariffa non valida nel giorno locale")
    if not is_working_day(local.date(), config):
        reasons.append("NONWORKING_DISPATCH: partenza non lavorativa")
    if local.time() > tariff.cutoff_local_time:
        reasons.append("CUTOFF: partenza oltre il cut-off")
    if not packages:
        reasons.append("NO_PACKAGES: nessun collo")
    if len(packages) > tariff.max_packages:
        reasons.append("MAX_PACKAGES: numero colli oltre limite")
    with localcontext() as context:
        context.prec = precision_for(tariff, *packages)
        if sum((p.actual_weight_kg for p in packages), D(0)) > tariff.max_shipment_actual_weight_kg:
            reasons.append("SHIPMENT_WEIGHT: peso reale totale oltre limite")
    for package in packages:
        if package.actual_weight_kg > tariff.max_package_weight_kg:
            reasons.append(f"PACKAGE_WEIGHT: collo {package.package_id} oltre limite di peso reale")
        if max(package.length_cm, package.width_cm, package.height_cm) > tariff.max_package_longest_side_cm:
            reasons.append(f"PACKAGE_SIDE: collo {package.package_id} oltre limite sul lato lungo")
    try:
        expected = arrival_date(local.date(), tariff.transit_business_days, config)
        if any(expected > s.promised_delivery_date for s in shipments):
            reasons.append("DEADLINE: arrivo previsto oltre la promessa")
    except OverflowError:
        expected = None
        reasons.append("DATE_RANGE: arrivo oltre l'intervallo di date rappresentabile")
    trace = None if reasons else price(packages, tariff, config)
    return Evaluation(tariff.service_id, tariff.tariff_id, tuple(reasons), expected, trace)


def alternatives(shipments: tuple[Shipment, ...], packages: tuple[Package, ...], tariffs: tuple[Tariff, ...], config: ModelConfig) -> tuple[Evaluation, ...]:
    first = shipments[0]
    day = first.dispatch_at.astimezone(config.timezone).date()
    active = [t for t in tariffs if t.zone == first.zone and t.valid_from <= day <= t.valid_to]
    return tuple(evaluate(shipments, packages, t, config) for t in sorted(active, key=lambda t: (t.service_id, t.tariff_id)))


def cheapest(evaluations: tuple[Evaluation, ...], original: str | None = None) -> Evaluation | None:
    feasible = [e for e in evaluations if e.feasible]
    return min(feasible, key=lambda e: (e.cost, 0 if e.service_id == original else 1, e.service_id, e.tariff_id), default=None)
