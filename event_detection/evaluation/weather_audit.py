"""Check whether daily and hourly Zonnedael weather/gas data reconcile."""

from collections import defaultdict
from statistics import mean

from event_detection.data import get_series


def audit_weather_linkage(household: str = "Klant 34") -> dict[str, object]:
    """Return reproducible weather coverage and hourly/daily reconciliation metrics."""
    daily = get_series("zonnedael", household)
    hourly = get_series("zonnedael_hourly", household)
    hourly_by_day: dict[object, list] = defaultdict(list)
    for point in hourly:
        hourly_by_day[point.timestamp.date()].append(point)

    temperature_values = [point.temp_mean_c for point in hourly if point.temp_mean_c is not None]
    daily_temperature_days = sum(point.temp_mean_c is not None for point in daily)
    daily_temperature_differences: list[float] = []
    gas_differences: list[float] = []
    comparable_gas_days = 0
    all_day_matches = 0
    complete_weather_days = 0
    complete_gas_hours = 0
    gas_hours_expected = 0

    for daily_point in daily:
        intervals = hourly_by_day.get(daily_point.timestamp.date(), [])
        if intervals:
            all_day_matches += 1
        hourly_temperatures = [point.temp_mean_c for point in intervals if point.temp_mean_c is not None]
        if hourly_temperatures:
            complete_weather_days += 1
            if daily_point.temp_mean_c is not None:
                daily_temperature_differences.append(
                    abs(daily_point.temp_mean_c - mean(hourly_temperatures))
                )
        valid_gas = [point.gas_m3 for point in intervals if point.gas_m3 is not None]
        gas_hours_expected += 24
        complete_gas_hours += len(valid_gas)
        if daily_point.quality_flag == "ok" and daily_point.gas_m3 is not None and len(valid_gas) == 24:
            comparable_gas_days += 1
            gas_differences.append(abs(daily_point.gas_m3 - sum(valid_gas)))

    max_gas_difference = max(gas_differences, default=0.0)
    gas_reconciled_days = sum(difference <= 0.001 for difference in gas_differences)
    weather_coverage = len(temperature_values) / len(hourly) if hourly else 0.0
    daily_weather_coverage = daily_temperature_days / len(daily) if daily else 0.0
    date_alignment = all_day_matches / len(daily) if daily else 0.0
    reconciliation_ratio = gas_reconciled_days / comparable_gas_days if comparable_gas_days else 0.0
    enabled = (
        weather_coverage >= 0.99
        and daily_weather_coverage >= 0.99
        and (complete_gas_hours / gas_hours_expected if gas_hours_expected else 0.0) >= 0.99
        and date_alignment >= 0.99
        and reconciliation_ratio >= 0.99
    )
    return {
        "household": household,
        "status": "ready" if enabled else "limited",
        "weather_gas_enabled": enabled,
        "weather_source_note": "KNMI De Bilt is used as a proxy; the true Zonnedael location is unknown.",
        "daily_points": len(daily),
        "hourly_points": len(hourly),
        "hourly_temperature_coverage": round(weather_coverage, 6),
        "daily_temperature_coverage": round(daily_weather_coverage, 6),
        "matched_days": all_day_matches,
        "date_alignment": round(date_alignment, 6),
        "weather_complete_days": complete_weather_days,
        "mean_daily_vs_hourly_temperature_difference_c": round(mean(daily_temperature_differences), 4)
        if daily_temperature_differences else None,
        "max_daily_vs_hourly_temperature_difference_c": round(max(daily_temperature_differences), 4)
        if daily_temperature_differences else None,
        "hourly_gas_coverage": round(complete_gas_hours / gas_hours_expected, 6)
        if gas_hours_expected else 0.0,
        "gas_reconciliation_days": comparable_gas_days,
        "gas_days_within_0_001_m3": gas_reconciled_days,
        "gas_reconciliation_ratio": round(reconciliation_ratio, 6),
        "max_daily_vs_hourly_gas_difference_m3": round(max_gas_difference, 6),
        "notes": [
            "Daily and hourly temperature aggregates may differ slightly; each resolution keeps its own source values.",
            "Weather-conditioned gas scenarios are controlled tests, not evidence about the household's true local weather.",
        ],
    }