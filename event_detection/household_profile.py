"""Prototype consumption and household context for tip selection (plan §1.6)."""
from statistics import mean
from math import isfinite
from collections.abc import Sequence
from event_detection.schemas import SeriesPoint


def valid(row: SeriesPoint, fuel: str):
    count, full = ('n_elec_intervals', 96) if fuel == 'electricity_kwh' else ('n_gas_hours', 24)
    return (row.quality_flag in ('ok', 'partial') and getattr(row, count) == full
            and getattr(row, fuel) is not None and isfinite(getattr(row, fuel)) and getattr(row, fuel) >= 0)


def build_profile(rows: Sequence[SeriesPoint], household_id: str, home=None):
    selected = sorted(rows, key=lambda r: r.timestamp)
    if not selected:
        raise ValueError(f'No history for {household_id}')
    fuels = {}
    for fuel in ('electricity_kwh', 'gas_m3'):
        good = [r for r in selected if valid(r, fuel)]
        weekdays = {str(day): mean(values) if values else None for day in range(7)
                    for values in [[getattr(r, fuel) for r in good if r.timestamp.date().weekday() == day]]}
        highest = max((v for v in weekdays.values() if v is not None), default=None)
        fuels[fuel] = {
            'mean_daily': mean(getattr(r, fuel) for r in good) if good else None,
            'valid_days': len(good),
            'by_weekday': weekdays,
            'highest_usage_weekdays': [int(day) for day, value in weekdays.items()
                                       if value is not None and value == highest],
            'peak_hour': None, 'night_usage': None,
        }
    metadata = {}
    for key in ('woning_type', 'bouwjaar_band', 'gezinssituatie'):
        values = {getattr(r, key) for r in selected if getattr(r, key)}
        metadata[key] = values.pop() if len(values) == 1 else None
    temperatures = [r.temp_mean_c for r in selected if r.temp_mean_c is not None and isfinite(r.temp_mean_c)]
    seasons = ('winter', 'spring', 'summer', 'autumn')
    return {
        'household_id': household_id,
        'period': {'start': str(selected[0].timestamp.date()), 'end': str(selected[-1].timestamp.date())},
        'fuels': fuels,
        'home': {**metadata, **(home or {})},
        'weather': {'mean_temperature_c': mean(temperatures) if temperatures else None},
        'seasons': sorted({seasons[(r.timestamp.date().month % 12) // 3] for r in selected}),
        'resolution': 'daily',
    }
