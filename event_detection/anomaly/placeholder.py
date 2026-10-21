"""Explicit TBD anomaly implementation."""

from collections.abc import Sequence

from event_detection.schemas import Event, SeriesPoint
from .base import AnomalyDetector


class PlaceholderAnomalyDetector(AnomalyDetector):
    """TBD: real anomaly detection is intentionally not implemented yet."""

    name = "placeholder"

    def detect(self, series: Sequence[SeriesPoint]) -> list[Event]:
        del series
        return []
