from datetime import datetime, timedelta

import pytest

import event_detection.evaluation.benchmark as benchmark_module
from event_detection.evaluation.benchmark import (
    chronological_split,
    detector_support_diagnostics,
    generate_benchmark_cases,
    injection_specs,
    random_budget_events,
    rolling_weekly_splits,
)
from event_detection.evaluation.matching import match_event_windows, summarize_benchmark_events
from event_detection.schemas import Event, SeriesPoint


def _series(count: int = 1000, interval_minutes: int = 15) -> list[SeriesPoint]:
    return [
        SeriesPoint(
            timestamp=datetime(2013, 1, 1) + timedelta(minutes=interval_minutes * index),
            interval_minutes=interval_minutes,
            electricity_kwh=0.1 + (index % 7) * 0.002,
            gas_m3=0.025 + (index % 5) * 0.001,
            temp_mean_c=1.0,
            hdd18=17.0,
            quality_flag="ok",
        )
        for index in range(count)
    ]


def _event(
    event_id: str,
    start: datetime,
    end: datetime,
    direction: str = "high",
) -> Event:
    return Event(
        id=event_id,
        type="unusual_electricity",
        start=start,
        end=end,
        magnitude=1.0,
        confidence=0.8,
        method="test",
        details={"signal": "electricity", "direction": direction},
    )


def test_chronological_split_uses_70_10_20_and_preserves_order():
    parts = chronological_split(_series(100))

    assert (len(parts.training), len(parts.calibration), len(parts.test)) == (70, 10, 20)
    assert parts.training[-1].timestamp < parts.calibration[0].timestamp
    assert parts.calibration[-1].timestamp < parts.test[0].timestamp


@pytest.mark.parametrize("training_weeks", [2, 4, 8])
def test_rolling_weekly_splits_use_preceding_weeks_and_exclude_partial_test(training_weeks):
    points = _series((training_weeks + 4) * 7 * 24 + 12, interval_minutes=60)
    splits = rolling_weekly_splits(list(reversed(points)), training_weeks)

    assert len(splits) == 3
    for index, parts in enumerate(splits):
        assert len(parts.training) == training_weeks * 7 * 24
        assert len(parts.calibration) == len(parts.test) == 7 * 24
        assert parts.training[0].timestamp == datetime(2013, 1, 1) + timedelta(weeks=index)
        assert parts.training[-1].timestamp + timedelta(hours=1) == parts.calibration[0].timestamp
        assert parts.calibration[-1].timestamp + timedelta(hours=1) == parts.test[0].timestamp
    assert splits[0].test[-1].timestamp + timedelta(hours=1) == splits[1].test[0].timestamp


def test_rolling_weekly_split_rejects_insufficient_or_missing_partitions():
    with pytest.raises(ValueError, match="at least 4 weeks"):
        rolling_weekly_splits(_series(27, interval_minutes=1440), 2)
    points = _series(28, interval_minutes=1440)
    with pytest.raises(ValueError, match="empty partition"):
        rolling_weekly_splits(points[:14] + points[21:], 2)


def test_rolling_benchmark_runs_detectors_and_reports_progress(monkeypatch):
    points = _series(28 * 24, interval_minutes=60)
    monkeypatch.setattr(benchmark_module, "get_series", lambda dataset, household: points)
    progress = []
    results = benchmark_module.run_household_rolling_benchmark(
        "test", "A", ["spikes"], 17, False, 1, [0.5], "corrected_v2", 2,
        on_progress=lambda completed, total: progress.append((completed, total)),
    )

    assert progress == [(0, 1), (1, 1)]
    assert len(results) == 1
    result = results[0]
    assert result["point_counts"] == {"training": 336, "calibration": 168, "test": 168}
    assert result["date_ranges"]["test_start"] == datetime(2013, 1, 22)
    assert result["ground_truth"]
    assert {"isolation_forest", "rnn"} <= {method["method"] for method in result["methods"]}


def test_benchmark_injections_are_deterministic_and_do_not_mutate_source():
    original = _series()
    partitions = chronological_split(original)
    before = [point.electricity_kwh for point in original]

    first_test, first_truth = generate_benchmark_cases(partitions, ["spikes", "low_use"], 17, False)
    second_test, second_truth = generate_benchmark_cases(partitions, ["spikes", "low_use"], 17, False)

    assert len(first_truth) == 10
    assert [(event.id, event.start, event.end) for event in first_truth] == [
        (event.id, event.start, event.end) for event in second_truth
    ]
    assert [point.electricity_kwh for point in original] == before
    assert [point.electricity_kwh for point in first_test] == [
        point.electricity_kwh for point in second_test
    ]
    assert all(event.start >= partitions.test[0].timestamp for event in first_truth)


def test_weather_gas_injections_are_enabled_only_when_weather_is_validated():
    parts = chronological_split(_series())

    _, disabled_truth = generate_benchmark_cases(parts, ["weather_gas"], 5, False)
    _, enabled_truth = generate_benchmark_cases(parts, ["weather_gas"], 5, True)

    assert disabled_truth == []
    assert len(enabled_truth) == 2
    assert all(event.details["signal"] == "gas" for event in enabled_truth)
    assert all(event.details["pattern"] == "weather_gas" for event in enabled_truth)


def test_weather_gas_injections_are_skipped_when_dataset_has_no_gas():
    electricity_only = [
        point.model_copy(update={"gas_m3": None, "interval_minutes": 15})
        for point in _series(1000, interval_minutes=15)
    ]
    partitions = chronological_split(electricity_only)

    _, truth = generate_benchmark_cases(partitions, ["weather_gas"], 5, True)

    assert truth == []


def test_injection_strengths_filter_only_compatible_pattern_levels():
    specs = injection_specs(["spikes", "sustained_high"], True, [0.3, 0.5])

    assert {spec.pattern for spec in specs} == {"spike", "sustained_high"}
    assert {spec.strength for spec in specs} == {0.3, 0.5}
    assert not any(spec.pattern == "spike" and spec.strength == 0.3 for spec in specs)


def test_low_injections_do_not_increase_original_readings():
    series = _series()
    partitions = chronological_split(series)
    for point in partitions.test:
        point.electricity_kwh = 0.001
        point.gas_m3 = 0.001

    original = list(partitions.test)
    injected, truth = generate_benchmark_cases(partitions, ["low_use"], 17, False)
    legacy_points, legacy_truth = generate_benchmark_cases(partitions, ["low_use"], 17, False, protocol="legacy_v1")

    assert truth
    for event in truth:
        attribute = "electricity_kwh" if event.details["signal"] == "electricity" else "gas_m3"
        for before, after in zip(original, injected):
            if event.start <= before.timestamp < event.end:
                assert getattr(after, attribute) < getattr(before, attribute)
    assert legacy_truth
    assert any(after.electricity_kwh > before.electricity_kwh for before, after in zip(original, legacy_points))


def test_weather_gas_never_falls_back_to_warm_windows():
    parts = chronological_split(_series())
    for point in parts.test:
        point.hdd18 = 1.0
    skipped = []

    _, corrected = generate_benchmark_cases(parts, ["weather_gas"], 5, True, protocol="corrected_v2", skipped=skipped)
    _, legacy = generate_benchmark_cases(parts, ["weather_gas"], 5, True, protocol="legacy_v1")

    assert corrected == []
    assert len(skipped) == 2
    assert len(legacy) == 2


def test_injection_windows_reject_gaps_and_invalid_points():
    parts = chronological_split(_series(300, interval_minutes=60))
    for index, point in enumerate(parts.test):
        point.timestamp += timedelta(hours=index * 6)
    original = [point.model_copy() for point in parts.test]
    skipped = []

    changed, truth = generate_benchmark_cases(parts, ["low_use"], 17, False, skipped=skipped)

    assert truth == []
    assert changed == original
    assert len(skipped) == 4


def test_injections_leave_partial_and_missing_points_untouched():
    parts = chronological_split(_series(300, interval_minutes=60))
    for index, point in enumerate(parts.test):
        point.quality_flag = "partial" if index % 2 else "missing"
    original = [point.model_copy() for point in parts.test]

    changed, truth = generate_benchmark_cases(parts, ["low_use"], 17, False)

    assert truth == []
    assert changed == original


def test_corrected_scores_distinguish_undefined_from_zero():
    start = datetime(2013, 1, 1)
    high = _event("high", start, start + timedelta(hours=1))
    low = _event("low", start, start + timedelta(hours=1), "low")
    scores = summarize_benchmark_events([low], [high], 168, 0)
    metrics = {row["direction"]: row for row in scores["classes"]}

    assert (metrics["high"]["precision"], metrics["high"]["recall"], metrics["high"]["f1"]) == (None, 0.0, 0.0)
    assert (metrics["low"]["precision"], metrics["low"]["recall"], metrics["low"]["f1"]) == (0.0, None, 0.0)
    legacy = summarize_benchmark_events([low], [high], 168, 0, protocol="legacy_v1")
    assert all(row["precision"] == 0.0 and row["recall"] == 0.0 for row in legacy["classes"])


def test_injected_values_record_realized_changes():
    parts = chronological_split(_series())
    _, truth = generate_benchmark_cases(parts, ["spikes"], 17, False, [0.5])

    for event in truth:
        for original, injected, delta in zip(event.details["original_values"], event.details["injected_values"], event.details["realized_deltas"]):
            assert injected > original
            assert delta == injected - original


def test_short_rnn_history_reports_insufficient_training_windows():
    partitions = chronological_split(_series(200, interval_minutes=60))

    diagnostics = detector_support_diagnostics(partitions, 7)

    assert diagnostics["rnn"]["electricity"]["status"] == "insufficient_training_windows"
    assert diagnostics["rnn"]["electricity"]["training_windows"] == 0
    assert diagnostics["rnn"]["electricity"]["lookback_days"] == 7


def test_sufficient_rnn_support_reports_training_and_calibration_windows():
    partitions = chronological_split(_series(1000, interval_minutes=60))

    diagnostics = detector_support_diagnostics(partitions, 1)

    assert diagnostics["rnn"]["electricity"]["status"] == "sufficient_support"
    assert diagnostics["rnn"]["electricity"]["training_windows"] == 676
    assert diagnostics["rnn"]["electricity"]["calibration_windows"] > 8
    assert diagnostics["rnn"]["electricity"]["test_windows"] > 0


def test_rnn_diagnostics_report_no_test_forecast_windows_across_gaps():
    partitions = chronological_split(_series(300, interval_minutes=60))
    partitions.test[0].quality_flag = "missing"
    for index, point in enumerate(partitions.test):
        point.timestamp += timedelta(hours=index)

    diagnostics = detector_support_diagnostics(partitions, 1)

    assert diagnostics["rnn"]["electricity"]["status"] == "no_test_forecast_windows"
    assert diagnostics["rnn"]["electricity"]["test_points"] == len(partitions.test) - 1
    assert diagnostics["rnn"]["electricity"]["test_windows"] == 0


def test_random_control_is_seeded_and_preserves_alert_budget_and_class():
    test = _series(200, interval_minutes=60)
    budget = [
        _event("alert-high", datetime(2013, 1, 1), datetime(2013, 1, 1, 2), "high"),
        _event("alert-low", datetime(2013, 1, 1, 2), datetime(2013, 1, 1, 3), "low"),
    ]

    first = random_budget_events(test, budget, 42)
    second = random_budget_events(test, budget, 42)

    assert [(event.start, event.end, event.details["direction"]) for event in first] == [
        (event.start, event.end, event.details["direction"]) for event in second
    ]
    assert len(first) == len(budget)
    assert [event.details["direction"] for event in first] == ["high", "low"]
    assert all(event.start >= test[0].timestamp and event.end <= test[-1].timestamp + timedelta(hours=1) for event in first)


def test_random_control_skips_alerts_without_valid_contiguous_windows():
    test = _series(20, interval_minutes=60)
    for index, point in enumerate(test):
        point.timestamp += timedelta(hours=index)
    two_hour_alert = _event("alert", test[0].timestamp, test[0].timestamp + timedelta(hours=2))

    generated = random_budget_events(test, [two_hour_alert], 7)

    assert generated == []


def test_interval_matching_uses_overlap_tolerance_and_one_to_one_assignment():
    start = datetime(2013, 1, 1)
    truth = [_event("truth", start, start + timedelta(hours=1))]
    detected = [
        _event("d1", start + timedelta(minutes=30), start + timedelta(minutes=90)),
        _event("d2", start + timedelta(minutes=30), start + timedelta(minutes=90)),
    ]

    result = match_event_windows(detected, truth, tolerance_minutes=15)

    assert result["matched"] == 1
    assert len(result["pairs"]) == 1
    assert match_event_windows(detected, truth, tolerance_minutes=0)["matched"] == 1


def test_interval_matching_requires_half_the_truth_after_tolerance():
    start = datetime(2013, 1, 1)
    truth = [_event("truth", start, start + timedelta(hours=2))]
    shorter = [_event("short", start, start + timedelta(minutes=45))]
    half = [_event("half", start, start + timedelta(hours=1))]

    assert match_event_windows(shorter, truth, tolerance_minutes=0)["matched"] == 0
    assert match_event_windows(shorter, truth, tolerance_minutes=15)["matched"] == 1
    assert match_event_windows(half, truth, tolerance_minutes=0)["matched"] == 1


def test_matching_keeps_high_and_low_events_separate_and_scores_metrics():
    start = datetime(2013, 1, 1)
    truth = [
        _event("high", start, start + timedelta(minutes=15), "high"),
        _event("low", start + timedelta(hours=1), start + timedelta(hours=1, minutes=15), "low"),
    ]
    detected = [_event("wrong-direction", start, start + timedelta(minutes=15), "low")]

    result = summarize_benchmark_events(detected, truth, test_duration_hours=168, tolerance_minutes=15)

    assert result["matching"]["matched"] == 0
    assert result["false_alarms"] == 1
    assert len(result["classes"]) == 2
