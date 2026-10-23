from datetime import datetime

from event_detection.anomaly.placeholder import PlaceholderAnomalyDetector
from event_detection.nilm.rules import RuleBasedDetector
from event_detection.schemas import SeriesPoint


def test_rule_detector_ignores_invalid_points():
    # A bad reading must not become a false consumption event.
    series = [
        SeriesPoint(timestamp=datetime(2026, 1, 1), electricity_kwh=10, gas_m3=5, hdd18=10, quality_flag="ok"),
        SeriesPoint(timestamp=datetime(2026, 1, 2), electricity_kwh=10, gas_m3=5, hdd18=10, quality_flag="ok"),
        SeriesPoint(timestamp=datetime(2026, 1, 3), electricity_kwh=None, gas_m3=None, hdd18=10, quality_flag="missing"),
    ]
    assert RuleBasedDetector().detect(series) == []
    assert PlaceholderAnomalyDetector().detect(series) == []


def test_rule_detector_reports_generic_elevated_consumption():
    # Rules describe the pattern, not the appliance behind it.
    series = [
        SeriesPoint(
            timestamp=datetime(2026, 1, day),
            electricity_kwh=10 if day < 14 else 20,
            gas_m3=5 if day < 14 else 12,
            hdd18=10,
            quality_flag="ok",
        )
        for day in range(1, 15)
    ]
    events = RuleBasedDetector().detect(series)
    assert {event.type for event in events} == {"high_electricity", "high_gas"}
    assert all("baseline" in event.details for event in events)


def test_rule_detector_requires_gas_history():
    series = [
        SeriesPoint(
            timestamp=datetime(2026, 1, day),
            gas_m3=5 if day < 3 else 12,
            hdd18=10,
            quality_flag="ok",
        )
        for day in range(1, 4)
    ]

    assert [event for event in RuleBasedDetector().detect(series) if event.type == "high_gas"] == []


def test_gas_baseline_is_robust_to_one_spike():
    series = [
        SeriesPoint(
            timestamp=datetime(2026, 1, day),
            gas_m3=2 + day * 0.5 if day != 10 else 30,
            hdd18=day,
            quality_flag="ok",
        )
        for day in range(1, 15)
    ]

    intercept, slope = RuleBasedDetector._gas_baseline(series)

    assert abs(intercept - 2) < 1
    assert abs(slope - 0.5) < 0.1
