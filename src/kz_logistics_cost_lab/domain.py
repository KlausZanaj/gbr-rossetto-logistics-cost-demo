"""Immutable domain values. No UI, file access or binary floating point."""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

D = Decimal


@dataclass(frozen=True)
class ModelConfig:
    timezone_name: str = "Europe/Rome"
    nonworking_dates: frozenset[date] = field(default_factory=frozenset)
    money_rounding: str = ROUND_HALF_UP

    def __post_init__(self):
        if self.timezone_name != "Europe/Rome" or self.money_rounding != ROUND_HALF_UP:
            raise ValueError("Il modello 0.1.0 usa Europe/Rome e ROUND_HALF_UP.")
        if any(type(d) is not date for d in self.nonworking_dates):
            raise ValueError("Il calendario richiede date, senza orari.")
        object.__setattr__(self, "nonworking_dates", frozenset(self.nonworking_dates))

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    file: str = ""
    row: int | None = None
    shipment_id: str = ""
    field: str = ""


@dataclass(frozen=True)
class RawTable:
    name: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    line_numbers: tuple[int, ...]

    def records(self) -> tuple[dict[str, str], ...]:
        return tuple(dict(zip(self.columns, row, strict=True)) for row in self.rows)


@dataclass(frozen=True)
class Inputs:
    tables: tuple[RawTable, ...]
    hashes: tuple[tuple[str, str], ...]
    issues: tuple[Issue, ...] = ()

    def table(self, name: str) -> RawTable:
        return next(t for t in self.tables if t.name == name)


@dataclass(frozen=True)
class Shipment:
    shipment_id: str
    order_id: str
    customer_id: str
    destination_id: str
    zone: str
    ready_at: datetime
    dispatch_at: datetime
    promised_delivery_date: date
    current_service_id: str
    handling_class: str
    consolidation_allowed: bool


@dataclass(frozen=True)
class Package:
    package_id: str
    shipment_id: str
    actual_weight_kg: Decimal
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal


@dataclass(frozen=True)
class Tariff:
    tariff_id: str
    service_id: str
    zone: str
    valid_from: date
    valid_to: date
    currency: str
    fixed_fee_eur: Decimal
    per_kg_eur: Decimal
    volumetric_divisor_cm3_per_kg: Decimal
    billing_increment_kg: Decimal
    fuel_pct: Decimal
    max_package_weight_kg: Decimal
    max_package_longest_side_cm: Decimal
    max_shipment_actual_weight_kg: Decimal
    max_packages: int
    transit_business_days: int
    cutoff_local_time: time


@dataclass(frozen=True)
class ValidatedData:
    inputs: Inputs
    shipments: tuple[Shipment, ...]
    packages: tuple[Package, ...]
    tariffs: tuple[Tariff, ...]
    issues: tuple[Issue, ...]
    invalid_shipments: frozenset[str]

    @property
    def blocked(self) -> bool:
        return any(i.severity == "BLOCK" for i in self.issues)


@dataclass(frozen=True)
class PackageCharge:
    package_id: str
    actual_weight_kg: Decimal
    volume_cm3: Decimal
    volumetric_weight_kg: Decimal
    unrounded_billable_weight_kg: Decimal
    billable_weight_kg: Decimal


@dataclass(frozen=True)
class PriceTrace:
    tariff_id: str
    packages: tuple[PackageCharge, ...]
    total_actual_weight_kg: Decimal
    total_billable_weight_kg: Decimal
    fixed_fee_eur: Decimal
    weight_component_eur: Decimal
    base_cost_eur: Decimal
    fuel_pct: Decimal
    fuel_eur: Decimal
    total_cost_eur: Decimal
    total_cents: int


@dataclass(frozen=True)
class Evaluation:
    service_id: str
    tariff_id: str
    reasons: tuple[str, ...]
    expected_delivery_date: date | None = None
    trace: PriceTrace | None = None

    @property
    def feasible(self) -> bool:
        return not self.reasons and self.trace is not None

    @property
    def cost(self) -> Decimal:
        if not self.feasible:
            raise ValueError("Un servizio non ammissibile non ha un costo confrontabile.")
        return self.trace.total_cost_eur


@dataclass(frozen=True)
class Choice:
    shipment: Shipment
    baseline: Evaluation
    selected: Evaluation
    alternatives: tuple[Evaluation, ...]


@dataclass(frozen=True)
class Group:
    members: tuple[str, ...]
    proposal_id: str
    selected: Evaluation


@dataclass(frozen=True)
class Exclusion:
    shipment_id: str
    primary_cause: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisResult:
    data: ValidatedData
    config: ModelConfig
    signature: str
    choices: tuple[Choice, ...]
    groups: tuple[Group, ...]
    exclusions: tuple[Exclusion, ...]
    issues: tuple[Issue, ...]
