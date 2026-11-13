from datetime import datetime, timedelta

from event_detection.evaluation.benchmark import (
    chronological_split,
    generate_benchmark_cases,
    injection_specs,
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
