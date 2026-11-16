"""Daily household summaries with explicit source resolution and quality."""
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, time, timedelta
from math import isfinite
from statistics import mean, median

from event_detection.schemas import SeriesPoint

FUELS = ('electricity_kwh', 'gas_m3')
MIN_DAYS = 30
MIN_COVERAGE = 0.8


def valid(row: SeriesPoint, fuel: str):
    count, full = ('n_elec_intervals', 96) if fuel == 'electricity_kwh' else ('n_gas_hours', 24)
    value = getattr(row, fuel)
    return (row.interval_minutes == 1440 and row.quality_flag in ('ok', 'partial')
            and getattr(row, count) == full and value is not None
            and isfinite(value) and value >= 0)


def daily_points(rows: Sequence[SeriesPoint]) -> list[SeriesPoint]:
    """Aggregate complete calendar days without filling or scaling missing values.

    Source timestamps are naive local time. Require the nominal 24h grid; unusual
    clock-change days remain incomplete until the source provides timezone offsets.
    """
    if not rows:
        return []
    resolutions = {r.interval_minutes for r in rows}
    if len(resolutions) != 1 or not resolutions <= {15, 60, 1440}:
        raise ValueError('Profile requires one supported resolution: 15, 60 or 1440 minutes')
    step = rows[0].interval_minutes
    seen = set()
    days = defaultdict(list)
    for row in rows:
        stamp = row.timestamp
        if stamp.tzinfo is not None or stamp.second or stamp.microsecond or (stamp.hour*60+stamp.minute) % step:
            raise ValueError('Profile requires aligned, timezone-naive source timestamps')
        if stamp in seen:
            raise ValueError(f'Duplicate profile timestamp: {stamp.isoformat()}')
        seen.add(stamp)
        days[stamp.date()].append(row)
    if step == 1440:
        return sorted(rows, key=lambda r: r.timestamp)
    daily = []
    for day, points in sorted(days.items()):
        values, counts = {}, {}
        for fuel in FUELS:
            def usable(p):
                value = getattr(p, fuel)
                if p.quality_flag == 'missing' or value is None or not isfinite(value) or value < 0:
                    return False
                if fuel == 'gas_m3':
                    return step == 60 and p.n_gas_hours == 1
                if step == 60:
                    return p.n_elec_intervals == 4
                # The quarter-hour export has no per-fuel count; its flag is authoritative.
                return p.quality_flag == 'ok'
            good = [p for p in points if usable(p)]
            full = len(good) == 1440 // step
            values[fuel] = sum(getattr(p, fuel) for p in good) if full else None
            counts[fuel] = len(good) * (step//15 if fuel == 'electricity_kwh' else 1)
        temps = [p.temp_mean_c for p in points if p.temp_mean_c is not None and isfinite(p.temp_mean_c)]
        temperature = mean(temps) if len(temps) == 1440//step else None
        flag = 'ok' if all(v is not None for v in values.values()) else 'partial'
        if not any(counts.values()):
            flag = 'missing'
        daily.append(SeriesPoint(
            timestamp=datetime.combine(day, time()), quality_flag=flag,
            **values, n_elec_intervals=counts['electricity_kwh'], n_gas_hours=counts['gas_m3'],
            temp_mean_c=temperature, hdd18=max(0, 18-temperature) if temperature is not None else None,
        ))
    return daily


def build_profile(rows: Sequence[SeriesPoint], household_id: str, home=None):
    selected = daily_points(rows)
    if not selected:
        raise ValueError(f'No history for {household_id}')
    start, end = selected[0].timestamp.date(), selected[-1].timestamp.date()
    span = (end-start).days+1
    by_date = {r.timestamp.date(): r for r in selected}
    quality = []
    quality_fuels = ('electricity_kwh',) if rows[0].interval_minutes == 15 else FUELS
    for offset in range(span):
        day = start + timedelta(days=offset)
        row = by_date.get(day)
        affected = [f for f in quality_fuels if row is None or not valid(row, f)]
        if affected:
            quality.append({'date': str(day), 'status': 'gap' if row is None else row.quality_flag,
                            'fuels': affected})
    fuels = {}
    for fuel in FUELS:
        good = [r for r in selected if valid(r, fuel)]
        available = any(getattr(r, fuel) is not None for r in rows)
        weekdays = {str(day): mean(values) if values else None for day in range(7)
                    for values in [[getattr(r, fuel) for r in good if r.timestamp.weekday() == day]]}
        highest = max((v for v in weekdays.values() if v is not None), default=None)
        coverage = len(good)/span
        status = ('unavailable' if not available else 'ready'
                  if len(good) >= MIN_DAYS and coverage >= MIN_COVERAGE else 'insufficient_history')
        fuels[fuel] = {
            'mean_daily': mean(getattr(r, fuel) for r in good) if good else None,
            'median_daily': median(getattr(r, fuel) for r in good) if good else None,
            'valid_days': len(good), 'coverage': coverage, 'status': status,
            'by_weekday': weekdays,
            'weekday_samples': {str(day): sum(r.timestamp.weekday() == day for r in good) for day in range(7)},
            'highest_usage_weekdays': [int(day) for day, value in weekdays.items()
                                       if value is not None and value == highest],
            'peak_hour': None, 'night_usage': None,
        }
    metadata, conflicts = {}, []
    for key in ('woning_type', 'bouwjaar_band', 'gezinssituatie'):
        values = {getattr(r, key) for r in rows if getattr(r, key)}
        metadata[key] = next(iter(values)) if len(values) == 1 else None
        if len(values) > 1:
            conflicts.append(key)
    temperatures = [r.temp_mean_c for r in selected if r.temp_mean_c is not None and isfinite(r.temp_mean_c)]
    seasons = ('winter', 'spring', 'summer', 'autumn')
    return {
        'schema_version': '0.2.0', 'household_id': household_id,
        'period': {'start': str(start), 'end': str(end), 'calendar_days': span, 'observed_days': len(selected)},
        'status': 'ready' if any(f['status'] == 'ready' for f in fuels.values()) else 'insufficient_history',
        'fuels': fuels, 'home': {**metadata, **(home or {})}, 'metadata_conflicts': conflicts,
        'data_quality': quality,
        'weather': {'mean_temperature_c': mean(temperatures) if temperatures else None,
                    'valid_days': len(temperatures)},
        'seasons': sorted({seasons[(r.timestamp.month % 12) // 3] for r in selected}),
        'resolution': 'daily', 'source_interval_minutes': rows[0].interval_minutes,
        'readiness_policy': {'minimum_valid_days': MIN_DAYS, 'minimum_coverage': MIN_COVERAGE, 'validated': False},
        'limitations': ['Daily summaries do not identify appliances or occupancy.',
                        'Readiness is data sufficiency, not validated prediction accuracy.',
                        'Peak hours and night use are not implemented.',
                        'No annualisation, monetary savings or comfort assessment.'],
    }
