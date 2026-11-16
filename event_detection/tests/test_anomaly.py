from datetime import datetime, timedelta

from event_detection.anomaly.isolation_forest import IsolationForestAnomalyDetector
from event_detection.schemas import SeriesPoint


def _series_with_electricity_spike() -> list[SeriesPoint]:
    start = datetime(2026, 1, 1)
    return [
        SeriesPoint(
            timestamp=start + timedelta(days=index),
            electricity_kwh=50 if index == 45 else 10 + (index % 5) * 0.2,
            gas_m3=5,
            temp_mean_c=10,
            hdd18=8,
            quality_flag="ok",
        )
        for index in range(60)
    ]


def test_isolation_forest_scores_only_the_holdout_period():
    series = _series_with_electricity_spike()
    training_end = series[int(len(series) * 0.7)].timestamp
    events = IsolationForestAnomalyDetector().detect(series)

    assert all(event.start >= training_end for event in events)


def test_isolation_forest_uses_provisional_chronological_defaults():
    detector = IsolationForestAnomalyDetector()

    assert detector.training_ratio == 0.7
    assert detector.contamination == 0.01


def test_isolation_forest_imputes_heldout_weather_from_training_only():
    detector = IsolationForestAnomalyDetector()
    training = [
        SeriesPoint(timestamp=datetime(2026, 1, 1) + timedelta(days=index),
                    electricity_kwh=10, temp_mean_c=value, hdd18=value + 5,
                    quality_flag="ok")
        for index, value in enumerate((5.0, 15.0))
    ]
    heldout = [
        SeriesPoint(timestamp=datetime(2026, 2, 1) + timedelta(days=index),
                    electricity_kwh=10, temp_mean_c=None, hdd18=None,
                    quality_flag="ok")
        for index in range(2)
    ]

    training_medians = detector._context_medians(training)
    features = detector._features(heldout, "electricity_kwh", training_medians)

    assert features[:, 5].tolist() == [10.0, 10.0]
    assert features[:, 6].tolist() == [15.0, 15.0]


def test_isolation_forest_benchmark_scores_only_test_using_calibration():
    start = datetime(2026, 1, 1)
    series = [
        SeriesPoint(
            timestamp=start + timedelta(days=index),
            electricity_kwh=50 if index == 90 else 10 + (index % 5) * 0.2,
            quality_flag="ok",
        )
        for index in range(100)
    ]
    training, calibration, test = series[:70], series[70:80], series[80:]

    events = IsolationForestAnomalyDetector(contamination=0.1).detect_benchmark(
        training,
        calibration,
        test,
    )

    assert all(event.start >= test[0].timestamp for event in events)
    assert all(event.method == "isolation_forest" for event in events)


def test_isolation_forest_uses_history_before_requested_detection_window():
    series = _series_with_electricity_spike()
    detection_start = datetime(2026, 2, 12)

    events = IsolationForestAnomalyDetector(contamination=0.05).detect(
        series,
        detection_start=detection_start,
    )

    assert all(event.start >= detection_start for event in events)


def test_isolation_forest_ignores_invalid_points_and_short_history():
    series = _series_with_electricity_spike()
    series[45] = series[45].model_copy(update={"quality_flag": "partial"})
    assert IsolationForestAnomalyDetector().detect(series) == []

    short_series = series[:10]
    assert IsolationForestAnomalyDetector().detect(short_series) == []


def test_isolation_forest_merges_adjacent_anomalous_intervals():
    detector = IsolationForestAnomalyDetector()
    events = [
        detector._event(
            SeriesPoint(
                timestamp=datetime(2026, 1, 1, 12, index * 15),
                interval_minutes=15,
                electricity_kwh=10,
                quality_flag="ok",
            ),
            "electricity",
            10,
            5,
            -0.2,
            0.8,
        )
        for index in range(2)
    ]

    merged = detector._aggregate_events(events)

    assert len(merged) == 1
    assert merged[0].end == datetime(2026, 1, 1, 12, 30)
    assert merged[0].details["interval_count"] == 2