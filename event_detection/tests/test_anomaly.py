from datetime import datetime, timedelta

from event_detection.anomaly.isolation_forest import IsolationForestAnomalyDetector
from event_detection.schemas import SeriesPoint


def _series_with_electricity_spike() -> list[SeriesPoint]:
    start = datetime(2026, 1, 1)
    return [
        SeriesPoint(
            timestamp=start + timedelta(days=index),
            electricity_kwh=50 if index == 35 else 10,
            gas_m3=5,
            temp_mean_c=10,
            hdd18=8,
            quality_flag="ok",
        )
        for index in range(40)
    ]


def test_isolation_forest_detects_spike_and_reports_context():
    events = IsolationForestAnomalyDetector().detect(_series_with_electricity_spike())

    electricity_events = [event for event in events if event.type == "unusual_electricity"]
    assert len(electricity_events) == 1
    assert electricity_events[0].start == datetime(2026, 2, 5)
    assert electricity_events[0].method == "isolation_forest"
    assert electricity_events[0].details["observed"] == 50


def test_isolation_forest_ignores_invalid_points_and_short_history():
    series = _series_with_electricity_spike()
    series[35] = series[35].model_copy(update={"quality_flag": "partial"})
    assert IsolationForestAnomalyDetector().detect(series) == []

    short_series = series[:10]
    assert IsolationForestAnomalyDetector().detect(short_series) == []