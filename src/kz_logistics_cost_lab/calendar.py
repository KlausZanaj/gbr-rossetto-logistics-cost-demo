"""Calendar uses explicit inputs; it never consults the wall clock."""
from datetime import date, timedelta

from .domain import ModelConfig


def is_working_day(day: date, config: ModelConfig) -> bool:
    return day.weekday() < 5 and day not in config.nonworking_dates


def arrival_date(dispatch_day: date, days: int, config: ModelConfig) -> date:
    if days < 0:
        raise ValueError("Transito negativo.")
    current = dispatch_day
    remaining = days
    while remaining:
        current += timedelta(days=1)
        if is_working_day(current, config):
            remaining -= 1
    return current
