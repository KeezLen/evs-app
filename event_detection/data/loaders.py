"""Loader interfaces reserved for the data team.

Adapters should return normalized SeriesPoint values at 15-minute resolution.
GridFlex adapters resample 1-minute source data; Zonnedael gas remains marked
as coarse because its source resolution is hourly.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from event_detection.schemas import SeriesPoint


class DatasetLoader(ABC):
    dataset_id: str

    @abstractmethod
    def load(self, household: str) -> Sequence[SeriesPoint]:
        """Load, validate and normalize one household."""


class GridFlexLoader(DatasetLoader):
    dataset_id = "gridflex_heeten"

    def load(self, household: str) -> Sequence[SeriesPoint]:
        del household
        raise NotImplementedError("GridFlex source adapter is pending")


class ZonnedaelLoader(DatasetLoader):
    dataset_id = "zonnedael"

    def load(self, household: str) -> Sequence[SeriesPoint]:
        del household
        raise NotImplementedError("Zonnedael source adapter is pending")
