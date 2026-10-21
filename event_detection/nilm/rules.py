"""Conservative placeholder for rule-based NILM detection.

The actual rules will be added after the data team's loader provides validated
15-minute electricity and gas series. Returning no events is preferable to
inventing appliance labels or presenting guesses as observations.
"""

from collections.abc import Sequence

from event_detection.schemas import Event, SeriesPoint
from .base import Detector, detector_registry


class RuleBasedDetector(Detector):
    """Future step, appliance, base-load and gas rule implementation."""

    name = "rules"

    def detect(self, series: Sequence[SeriesPoint]) -> list[Event]:
        """Return no events until validated aggregate data is available."""

        del series
        return []


detector_registry.register(RuleBasedDetector())
