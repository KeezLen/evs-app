"""Dataset boundary for the data team's future loaders.

This module intentionally returns metadata and an empty series only. It does not
pretend that public files or appliance labels have been added to this branch.
"""

from datetime import datetime

from event_detection.schemas import DatasetInfo, SeriesPoint

_DATASETS = [
    DatasetInfo(
        id="gridflex_heeten",
        name="GridFlex Heeten",
        households=[],
        resolution_minutes=15,
        available=False,
        notes="Loader pending; source data is 1-minute and must be resampled to 15 minutes.",
    ),
    DatasetInfo(
        id="zonnedael",
        name="Zonnedael",
        households=[],
        resolution_minutes=15,
        available=False,
        notes="Loader pending; gas is hourly and will remain explicitly coarse.",
    ),
]


def available_datasets() -> list[DatasetInfo]:
    """Return the catalog without claiming that files or labels exist."""

    return _DATASETS.copy()


def get_series(
    dataset: str,
    household: str,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> list[SeriesPoint]:
    """Return future loader output; currently an empty, valid series."""

    del dataset, household, range_start, range_end
    return []
