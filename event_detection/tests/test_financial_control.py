from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient
from pytest import approx

from event_detection.api.app import app
from event_detection.data import get_series
from event_detection.financial_control import FinancialControl


def test_meter_year_fills_gas_gap_with_october_average_and_keeps_valid_electricity():
    points = get_series("zonnedael", "Klant 34")
    estimate = FinancialControl().from_meter_year(points, 2013)
    october_gas = [
        point.gas_m3 for point in points if point.timestamp.month == 10 and point.gas_m3 is not None
    ]
    assert estimate["gas_days"] == 364
    assert estimate["electricity_days"] == 365
    assert estimate["electricity_kwh"] == approx(sum(point.electricity_kwh for point in points))
    assert estimate["gas_m3"] == approx(
        sum(point.gas_m3 for point in points if point.gas_m3 is not None)
        + sum(october_gas) / len(october_gas)
    )


def test_meter_year_withholds_cost_when_a_fuel_lacks_seasonal_coverage():
    points = get_series("zonnedael", "Klant 34", range_end=datetime(2013, 3, 31))
    estimate = FinancialControl().from_meter_year(points, 2013)
    assert estimate["annual_cost_eur"] is None
    assert estimate["gas_m3"] is None
    assert estimate["electricity_kwh"] is None


def test_recent_estimate_skips_incomplete_fuels_without_extending_the_window():
    points = get_series("zonnedael", "Klant 34")
    estimate = FinancialControl().from_recent_meter_days(points)
    assert estimate["window_start"] == "2013-10-03"
    assert estimate["window_end"] == "2013-12-31"
    assert estimate["gas_days"] == 89
    assert estimate["electricity_days"] == 90
    recent = [point for point in points if point.timestamp.date() >= date(2013, 10, 3)]
    assert estimate["electricity_kwh"] == approx(sum(p.electricity_kwh for p in recent) / 90 * 365)
    assert estimate["gas_m3"] < sum(p.gas_m3 for p in recent if p.gas_m3 is not None) / 89 * 365

    # Remove a row entirely. It stays a gap and the remaining annual weather
    # coverage is sufficient for the seasonal estimate.
    with_gap = FinancialControl().from_recent_meter_days(
        [p for p in points if p.timestamp.date() != date(2013, 11, 1)]
    )
    assert with_gap["window_start"] == estimate["window_start"]
    assert with_gap["gas_days"] == 88
    assert with_gap["electricity_days"] == 89
    assert with_gap["annual_cost_eur"] is not None


def test_recent_estimate_keeps_previous_year_weather_at_new_year():
    points = get_series("zonnedael", "Klant 34")
    calculator = FinancialControl()
    original = calculator.from_recent_meter_days(points)
    shifted = [point.model_copy(update={"timestamp": point.timestamp + timedelta(days=1)}) for point in points]
    estimate = calculator.from_recent_meter_days(shifted)
    assert estimate["window_end"] == "2014-01-01"
    assert estimate["weather_window_start"] == "2013-01-02"
    assert estimate["seasonal_weather_available"] is True
    assert estimate["annual_cost_eur"] == original["annual_cost_eur"]


def test_recent_estimate_withholds_cost_when_one_fuel_lacks_coverage():
    points = get_series("zonnedael", "Klant 34")
    for point in points[-35:]:
        point.electricity_kwh = None
    estimate = FinancialControl().from_recent_meter_days(points)
    assert estimate["electricity_days"] == 55
    assert estimate["gas_m3"] is not None
    assert estimate["electricity_kwh"] is None
    assert estimate["annual_cost_eur"] is None


def test_financial_estimates_are_exposed_through_the_api():
    client = TestClient(app)
    profile = client.post("/profiles/build", json={"dataset": "zonnedael", "household": "Klant 34"})
    assert profile.status_code == 200
    assert profile.json()["profile"]["annual_energy"]["year"] == 2013
    recent = profile.json()["profile"]["recent_annual_energy"]
    other = client.post("/profiles/build", json={"dataset": "zonnedael", "household": "Klant 10"})
    assert other.status_code == 200
    assert other.json()["profile"]["recent_annual_energy"]["annual_cost_eur"] != recent["annual_cost_eur"]
