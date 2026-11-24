"""Annual usage and variable energy cost for the resident prototype."""

from calendar import isleap, monthrange
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta
from math import isfinite
from statistics import mean

from event_detection.household_profile import valid
from event_detection.schemas import SeriesPoint

# TODO: subtract montly advanced payement in annual bill, keep in mind that this doesnt cover fixed charges etc
class FinancialControl:
    def __init__(self, gas_rate: float = 1.35, electricity_rate: float = 0.35):
        self.gas_rate = gas_rate
        self.electricity_rate = electricity_rate

    def _estimate(self, gas, electricity, gas_days, electricity_days, year_days):
        return {
            "gas_m3": gas,
            "electricity_kwh": electricity,
            "annual_cost_eur": (
                round(gas * self.gas_rate + electricity * self.electricity_rate, 2)
                if gas is not None and electricity is not None else None
            ),
            "gas_rate": self.gas_rate,
            "electricity_rate": self.electricity_rate,
            "fixed_charges_included": False,
            "gas_days": gas_days,
            "electricity_days": electricity_days,
            "year_days": year_days,
        }

    def from_recent_meter_days(self, points: Sequence[SeriesPoint]):
        """Project the last 90 calendar days using a rolling year of weather."""
        by_day = {point.timestamp.date(): point for point in points}
        end = max(by_day)
        start = end - timedelta(days=89)
        year_days = 366 if isleap(end.year) else 365
        minimum_days = 60
        recent = [point for day, point in by_day.items() if start <= day <= end]
        electricity = [point.electricity_kwh for point in recent if valid(point, "electricity_kwh")]
        gas = [point for point in recent if valid(point, "gas_m3")]

        # Use the existing demo gas signature as a seasonal reference, with
        # historical weather. Consumption comes only from the recent window.
        reference_by_day = {
            day: 0.35 + 0.22 * max(0, 15.5 - point.temp_mean_c)
            for day, point in by_day.items()
            if point.temp_mean_c is not None and isfinite(point.temp_mean_c)
        }
        weather_start = end - timedelta(days=year_days - 1)
        month_days = Counter((weather_start + timedelta(days=offset)).month for offset in range(year_days))
        weather_by_month = {month: [] for month in month_days}
        for day, value in reference_by_day.items():
            if weather_start <= day <= end:
                weather_by_month[day.month].append(value)
        enough_weather = all(len(values) * 2 >= month_days[month] for month, values in weather_by_month.items())
        paired_gas = [point for point in gas if point.timestamp.date() in reference_by_day]
        annual_gas = None
        if len(paired_gas) >= minimum_days and enough_weather:
            annual_reference = sum(mean(values) * month_days[month] for month, values in weather_by_month.items())
            observed_reference = sum(reference_by_day[point.timestamp.date()] for point in paired_gas)
            annual_gas = sum(point.gas_m3 for point in paired_gas) * annual_reference / observed_reference
        annual_electricity = mean(electricity) * year_days if len(electricity) >= minimum_days else None

        return {
            **self._estimate(annual_gas, annual_electricity, len(paired_gas), len(electricity), year_days),
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "minimum_days": minimum_days,
            "weather_window_start": weather_start.isoformat(),
            "seasonal_weather_available": enough_weather,
        }

    def from_meter_year(self, points: Sequence[SeriesPoint], year: int):
        """Fill small gaps at each month's observed daily average, independently per fuel."""
        month_days = {month: monthrange(year, month)[1] for month in range(1, 13)}
        totals = {}
        counts = {}
        for fuel in ("gas_m3", "electricity_kwh"):
            by_month = {month: {} for month in month_days}
            for point in points:
                day = point.timestamp.date()
                if day.year == year and valid(point, fuel):
                    by_month[day.month][day] = getattr(point, fuel)
            counts[fuel] = sum(len(days) for days in by_month.values())
            totals[fuel] = None
            if all(len(days) * 2 >= month_days[month] for month, days in by_month.items()):
                totals[fuel] = sum(
                    mean(days.values()) * month_days[month] for month, days in by_month.items()
                )
        return {
            **self._estimate(
                totals["gas_m3"], totals["electricity_kwh"], counts["gas_m3"],
                counts["electricity_kwh"], sum(month_days.values()),
            ),
            "year": year,
        }
