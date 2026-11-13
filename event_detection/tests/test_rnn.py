from datetime import datetime, timedelta
import math

from event_detection.anomaly.rnn import RNNForecastDetector
from event_detection.evaluation.benchmark import chronological_split
from event_detection.schemas import SeriesPoint


def _hourly_history() -> list[SeriesPoint]:
    start = datetime(2026, 1, 1)
    points = []
    for index in range(24 * 22):
        timestamp = start + timedelta(hours=index)
        daily_cycle = math.sin(2 * math.pi * timestamp.hour / 24)
        electricity = 0.35 + 0.08 * daily_cycle + (index % 7) * 0.002
        gas = 0.08 + max(0, 15 - (8 + 4 * daily_cycle)) * 0.015
        if index == 24 * 18 + 10:
            electricity = 8.0
            gas = 2.0
        points.append(SeriesPoint(
            timestamp=timestamp,
            interval_minutes=60,
            electricity_kwh=electricity,
            gas_m3=gas,
            temp_mean_c=8 + 4 * daily_cycle,
            hdd18=max(0, 18 - (8 + 4 * daily_cycle)),
            quality_flag="ok",
        ))
    return points


def test_rnn_trains_on_prior_hourly_history_and_scores_selected_window():
    RNNForecastDetector._model_cache.clear()
    series = _hourly_history()
    detection_start = series[24 * 14].timestamp

    events = RNNForecastDetector().detect(series, detection_start=detection_start)

    assert events
    assert all(event.start >= detection_start for event in events)
    assert {event.type for event in events} <= {"unusual_electricity", "unusual_gas"}
    assert all("predicted" in event.details for event in events)
    assert all(event.details["forecast_horizon_minutes"] == 60 for event in events)
    assert {event.details["direction"] for event in events} == {"high", "low"}


def test_rnn_rejects_unsupported_daily_resolution():
    daily = [
        SeriesPoint(
            timestamp=datetime(2026, 1, 1) + timedelta(days=index),
            interval_minutes=1440,
            electricity_kwh=10 + index % 3,
            gas_m3=4,
            quality_flag="ok",
        )
        for index in range(100)
    ]

    assert RNNForecastDetector().detect(daily) == []


def test_rnn_predicts_four_quarter_hour_steps_for_one_hour_horizon():
    start = datetime(2026, 1, 1)
    points = []
    for index in range(24 * 15 * 4):
        timestamp = start + timedelta(minutes=15 * index)
        daily_cycle = math.sin(2 * math.pi * (timestamp.hour + timestamp.minute / 60) / 24)
        value = 0.08 + 0.03 * daily_cycle + (index % 5) * 0.001
        if index == 24 * 12 * 4 + 8:
            value = 8.0
        points.append(SeriesPoint(
            timestamp=timestamp,
            interval_minutes=15,
            electricity_kwh=value,
            quality_flag="ok",
        ))
    detection_start = points[24 * 10 * 4].timestamp

    events = RNNForecastDetector().detect(points, detection_start=detection_start)

    assert events
    assert all(event.start >= detection_start for event in events)
    assert all(event.details["forecast_horizon_minutes"] == 60 for event in events)


def test_rnn_benchmark_uses_explicit_train_calibration_test_partitions():
    RNNForecastDetector._model_cache.clear()
    partitions = chronological_split(_hourly_history())
    test_start = partitions.test[0].timestamp

    events = RNNForecastDetector().detect_benchmark(
        partitions.training,
        partitions.calibration,
        partitions.test,
        lookback_days=1,
    )

    assert all(event.start >= test_start for event in events)
    assert all(event.details["forecast_horizon_minutes"] == 60 for event in events)