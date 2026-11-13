"""Ground-truth event matching with an explicit time tolerance."""

from collections.abc import Sequence
from datetime import timedelta

from event_detection.schemas import Event


def match_events(
    detected: Sequence[Event],
    ground_truth: Sequence[Event],
    tolerance_minutes: int = 1440,
) -> dict[str, int]:
    """Match same-type daily events within the allowed time window."""

    tolerance = timedelta(minutes=tolerance_minutes)
    remaining = list(ground_truth)
    matched = 0
    for candidate in detected:
        match_index = next(
            (
                index for index, truth in enumerate(remaining)
                if truth.type == candidate.type
                and abs(truth.start - candidate.start) <= tolerance
            ),
            None,
        )
        if match_index is not None:
            remaining.pop(match_index)
            matched += 1
    return {
        "matched": matched,
        "detected": len(detected),
        "ground_truth": len(ground_truth),
    }


def match_event_windows(
    detected: Sequence[Event],
    ground_truth: Sequence[Event],
    tolerance_minutes: int,
    minimum_truth_overlap: float = 0.5,
) -> dict[str, object]:
    """One-to-one event-window matching by signal, direction, and overlap."""
    tolerance = timedelta(minutes=tolerance_minutes)
    candidate_pairs: list[tuple[float, int, int, float]] = []
    for detected_index, candidate in enumerate(detected):
        candidate_signature = _event_signature(candidate)
        if candidate_signature is None:
            continue
        for truth_index, truth in enumerate(ground_truth):
            if candidate_signature != _event_signature(truth):
                continue
            truth_duration = max((truth.end - truth.start).total_seconds(), 1)
            expanded_start = candidate.start - tolerance
            expanded_end = candidate.end + tolerance
            overlap_start = max(expanded_start, truth.start)
            overlap_end = min(expanded_end, truth.end)
            overlap_seconds = max(0.0, (overlap_end - overlap_start).total_seconds())
            truth_overlap = overlap_seconds / truth_duration
            if truth_overlap >= minimum_truth_overlap:
                union_start = min(expanded_start, truth.start)
                union_end = max(expanded_end, truth.end)
                union_seconds = max((union_end - union_start).total_seconds(), 1)
                iou = overlap_seconds / union_seconds
                delay_minutes = (candidate.start - truth.start).total_seconds() / 60
                candidate_pairs.append((iou, detected_index, truth_index, delay_minutes))

    candidate_pairs.sort(reverse=True)
    used_detections: set[int] = set()
    used_truth: set[int] = set()
    pairs = []
    for iou, detected_index, truth_index, delay_minutes in candidate_pairs:
        if detected_index in used_detections or truth_index in used_truth:
            continue
        used_detections.add(detected_index)
        used_truth.add(truth_index)
        pairs.append({
            "detected_index": detected_index,
            "truth_index": truth_index,
            "overlap_iou": round(iou, 4),
            "delay_minutes": round(delay_minutes, 2),
        })
    return {
        "matched": len(pairs),
        "detected": len(detected),
        "ground_truth": len(ground_truth),
        "pairs": pairs,
    }


def _event_signature(event: Event) -> tuple[str, str] | None:
    signal = event.details.get("signal")
    direction = event.details.get("direction")
    if signal in {"electricity", "gas"}:
        if direction not in {"high", "low"}:
            return None
        return signal, direction

    event_type = event.type.lower()
    signal = "electricity" if "electricity" in event_type else "gas" if "gas" in event_type else None
    if signal is None:
        return None
    if direction not in {"high", "low"}:
        direction = "high" if event_type.startswith("high_") else None
    return (signal, direction) if direction in {"high", "low"} else None


def summarize_benchmark_events(
    detected: Sequence[Event],
    ground_truth: Sequence[Event],
    test_duration_hours: float,
    tolerance_minutes: int,
) -> dict[str, object]:
    """Return class metrics, injection sensitivity, false alarms, delay and overlap."""
    matching = match_event_windows(detected, ground_truth, tolerance_minutes)
    pairs = matching["pairs"]
    assert isinstance(pairs, list)
    matched_by_truth = {pair["truth_index"]: pair for pair in pairs}
    matched_by_class: dict[tuple[str, str], int] = {}
    for pair in pairs:
        signature = _event_signature(detected[pair["detected_index"]])
        if signature is not None:
            matched_by_class[signature] = matched_by_class.get(signature, 0) + 1

    signatures = sorted({
        signature for event in [*detected, *ground_truth]
        if (signature := _event_signature(event)) is not None
    })
    class_metrics = []
    total_false_alarms = 0
    for signal, direction in signatures:
        detected_count = sum(_event_signature(event) == (signal, direction) for event in detected)
        truth_count = sum(_event_signature(event) == (signal, direction) for event in ground_truth)
        matched_count = matched_by_class.get((signal, direction), 0)
        false_positives = detected_count - matched_count
        false_negatives = truth_count - matched_count
        total_false_alarms += false_positives
        precision = matched_count / detected_count if detected_count else 0.0
        recall = matched_count / truth_count if truth_count else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        class_metrics.append({
            "signal": signal,
            "direction": direction,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "detected": detected_count,
            "ground_truth": truth_count,
            "matched": matched_count,
            "false_positives": false_positives,
            "false_negatives": false_negatives,
        })

    injection_results = []
    for truth_index, truth in enumerate(ground_truth):
        pair = matched_by_truth.get(truth_index)
        injection_results.append({
            "id": truth.id,
            "pattern": truth.details.get("pattern"),
            "signal": truth.details.get("signal"),
            "direction": truth.details.get("direction"),
            "strength": truth.details.get("strength"),
            "duration_hours": truth.details.get("duration_hours"),
            "detected": pair is not None,
            "delay_minutes": pair["delay_minutes"] if pair else None,
            "overlap_iou": pair["overlap_iou"] if pair else 0.0,
        })
    weeks = max(test_duration_hours / 168, 1 / 168)
    delays = [pair["delay_minutes"] for pair in pairs]
    overlaps = [pair["overlap_iou"] for pair in pairs]
    return {
        "classes": class_metrics,
        "injections": injection_results,
        "false_alarms": total_false_alarms,
        "false_alarms_per_household_week": round(total_false_alarms / weeks, 4),
        "mean_detection_delay_minutes": round(sum(delays) / len(delays), 2) if delays else None,
        "mean_duration_overlap_iou": round(sum(overlaps) / len(overlaps), 4) if overlaps else None,
        "matching": matching,
    }
