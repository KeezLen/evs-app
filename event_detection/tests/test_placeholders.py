from datetime import datetime, timezone

from event_detection.anomaly.placeholder import PlaceholderAnomalyDetector
from event_detection.data import available_datasets
from event_detection.evaluation.matching import match_events
from event_detection.nilm.rules import RuleBasedDetector
from event_detection.schemas import Event, SeriesPoint


def test_catalog_is_honest_about_missing_sources():
    datasets = available_datasets()
    assert {dataset.id for dataset in datasets} == {"gridflex_heeten", "zonnedael"}
    assert all(dataset.available is False for dataset in datasets)


def test_detectors_return_empty_until_loader_exists():
    series = [SeriesPoint(timestamp=datetime.now(timezone.utc), electricity_w=100)]
    assert RuleBasedDetector().detect(series) == []
    assert PlaceholderAnomalyDetector().detect(series) == []


def test_matching_uses_fifteen_minute_tolerance_and_type():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    detected = [Event(id="d", type="step_change", start=start, end=start, magnitude=10, confidence=.5, method="rules")]
    truth = [Event(id="t", type="step_change", start=start.replace(minute=15), end=start, magnitude=10, confidence=1, method="ground_truth")]
    assert match_events(detected, truth)["matched"] == 1
    assert match_events(detected, truth, tolerance_minutes=0)["matched"] == 0
