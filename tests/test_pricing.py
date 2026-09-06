from dataclasses import replace
from datetime import date, datetime, time, timezone
from decimal import Decimal as D, getcontext, localcontext
import pytest
from kz_logistics_cost_lab.calendar import arrival_date
from kz_logistics_cost_lab.domain import ModelConfig
from kz_logistics_cost_lab.pricing import price, evaluate


def test_golden_price_and_volumetric(data, config):
    tariff = data.tariffs[0]
    assert price(data.packages, tariff, config).total_cost_eur == D("14.00")
    assert [price((p,), tariff, config).total_cost_eur for p in data.packages] == [D("10.80"), D("9.20")]
    p = replace(data.packages[0], actual_weight_kg=D(2), length_cm=D(60), width_cm=D(40), height_cm=D(40))
    trace = price((p,), tariff, config)
    assert trace.packages[0].volumetric_weight_kg == D("19.2")
    assert trace.total_billable_weight_kg == D(20)
    assert trace.total_cost_eur == D("14.00") and trace.total_cents == 1400


def test_per_package_maximum_and_increment(data, config):
    p = replace(data.packages[0], actual_weight_kg=D(2), length_cm=D(60), width_cm=D(40), height_cm=D(40))
    q = replace(data.packages[1], actual_weight_kg=D(30), length_cm=D(1), width_cm=D(1), height_cm=D(1))
    assert price((p, q), data.tariffs[0], config).total_billable_weight_kg == D(50)
    tariff = replace(data.tariffs[0], billing_increment_kg=D("0.5"))
    assert price((p,), tariff, config).total_billable_weight_kg == D("19.5")


def test_fuel_half_up_single_rounding_and_context(data, config):
    tariff = replace(data.tariffs[0], fixed_fee_eur=D("0.01"), per_kg_eur=D("0.0001"), fuel_pct=D("50"))
    before = getcontext().copy()
    with localcontext() as context:
        context.prec = 3
        trace = price(data.packages, tariff, config)
    assert trace.base_cost_eur == D("0.012")
    assert trace.fuel_eur == D("0.006")
    assert trace.total_cost_eur == D("0.02")
    assert getcontext().prec == before.prec
    assert price(data.packages, replace(tariff, per_kg_eur=D(0)), config).total_cost_eur == D("0.02")


def test_precise_ceiling_boundary(data, config):
    p = replace(data.packages[0], actual_weight_kg=D("12.000000000000000000000000000001"))
    assert price((p,), data.tariffs[0], config).total_billable_weight_kg == D(13)


def test_calendar_weekends_holidays_zero(config):
    assert arrival_date(date(2026, 9, 4), 1, config) == date(2026, 9, 7)
    holiday = ModelConfig(nonworking_dates=frozenset({date(2026, 9, 7)}))
    assert arrival_date(date(2026, 9, 4), 1, holiday) == date(2026, 9, 8)
    assert arrival_date(date(2026, 9, 4), 0, config) == date(2026, 9, 4)


def test_cutoff_and_exact_limits(data, config):
    s = replace(data.shipments[0], dispatch_at=datetime.fromisoformat("2026-09-01T12:00:00+02:00"))
    t = replace(data.tariffs[0], max_package_weight_kg=D(12), max_shipment_actual_weight_kg=D(12), max_package_longest_side_cm=D(40), max_packages=1)
    assert evaluate((s,), data.packages[:1], t, config).feasible
    late = replace(s, dispatch_at=datetime.fromisoformat("2026-09-01T12:00:00.000001+02:00"))
    assert any("CUTOFF" in r for r in evaluate((late,), data.packages[:1], t, config).reasons)
    too_heavy = replace(data.packages[0], actual_weight_kg=D("12.001"))
    assert not evaluate((s,), (too_heavy,), t, config).feasible


def test_winter_offset_and_local_date(data, config):
    s = replace(data.shipments[0], ready_at=datetime.fromisoformat("2026-01-05T00:00:00Z"), dispatch_at=datetime.fromisoformat("2026-01-05T11:00:00Z"), promised_delivery_date=date(2026, 1, 6))
    assert evaluate((s,), data.packages[:1], data.tariffs[0], config).feasible
    s = replace(s, dispatch_at=datetime.fromisoformat("2026-01-05T11:01:00Z"))
    assert not evaluate((s,), data.packages[:1], data.tariffs[0], config).feasible


def test_departure_holiday_weekend_and_deadline(data, config):
    assert not evaluate(data.shipments, data.packages, data.tariffs[0], ModelConfig(nonworking_dates={date(2026, 9, 1)})).feasible
    assert not evaluate(data.shipments, data.packages, replace(data.tariffs[0], transit_business_days=2), config).feasible
    s = replace(data.shipments[0], dispatch_at=datetime.fromisoformat("2026-09-05T09:00:00+02:00"), promised_delivery_date=date(2026, 9, 8))
    assert any("NONWORKING_DISPATCH" in r for r in evaluate((s,), data.packages[:1], data.tariffs[0], config).reasons)


@pytest.mark.parametrize("field,value,reason", [("max_packages", 1, "MAX_PACKAGES"), ("max_shipment_actual_weight_kg", D("19.999"), "SHIPMENT_WEIGHT"), ("max_package_longest_side_cm", D("39.999"), "PACKAGE_SIDE"), ("max_package_weight_kg", D("11.999"), "PACKAGE_WEIGHT")])
def test_each_service_limit_rejects_with_reason(data, config, field, value, reason):
    result = evaluate(data.shipments, data.packages, replace(data.tariffs[0], **{field: value}), config)
    assert not result.feasible and any(reason in r for r in result.reasons)
