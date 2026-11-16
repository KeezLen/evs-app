from datetime import datetime

from event_detection.data import available_datasets
from event_detection.data.catalog import get_series


def test_catalog_lists_only_ready_data_as_available():
    # GridFlex is still planned, while all Zonnedael resolutions are ready.
    datasets = available_datasets()
    assert {dataset.id for dataset in datasets} == {
        "gridflex_heeten",
        "zonnedael",
        "zonnedael_hourly",
        "zonnedael_15min_electricity",
    }
    assert datasets[0].available is False

    zonnedael = next(dataset for dataset in datasets if dataset.id == "zonnedael")
    assert zonnedael.available is True
    assert zonnedael.resolution_minutes == 1440
    assert len(zonnedael.households) == 58

    hourly = next(dataset for dataset in datasets if dataset.id == "zonnedael_hourly")
    assert hourly.available is True
    assert hourly.resolution_minutes == 60
    assert len(hourly.households) == 58

    electricity = next(
        dataset for dataset in datasets if dataset.id == "zonnedael_15min_electricity"
    )
    assert electricity.available is True
    assert electricity.resolution_minutes == 15
    assert len(electricity.households) == 58


def test_zonnedael_returns_daily_points_and_filters_dates():
    # The loader returns the same daily values as the source file.
    points = get_series(
        "zonnedael",
        "Klant 34",
        datetime(2013, 1, 1),
        datetime(2013, 1, 3),
    )
    assert len(points) == 3
    assert points[0].electricity_kwh == 9.568
    assert points[0].gas_m3 == 5.376
    assert points[0].quality_flag == "ok"
    assert points[0].hdd18 == 10.9


def test_zonnedael_rejects_excluded_households():
    try:
        get_series("zonnedael", "Klant 1")
    except ValueError as error:
        assert "not included" in str(error)
    else:
        raise AssertionError("Excluded household unexpectedly loaded")


def test_zonnedael_preserves_partial_days_as_quality_data():
    # The clock-change day is partial, not a low-gas day.
    points = get_series("zonnedael", "Klant 34")
    assert len(points) == 365
    partial = next(point for point in points if point.quality_flag == "partial")
    assert partial.timestamp.date().isoformat() == "2013-10-27"
    assert partial.gas_m3 is None
    assert partial.n_gas_hours == 22


def test_zonnedael_hourly_returns_interval_points():
    points = get_series(
        "zonnedael_hourly",
        "Klant 34",
        datetime(2013, 1, 1),
        datetime(2013, 1, 1, 1),
    )
    assert len(points) == 2
    assert points[0].timestamp == datetime(2013, 1, 1)
    assert points[0].interval_minutes == 60
    assert points[0].electricity_kwh == 0.207
    assert points[0].gas_m3 == 0.0715
    assert points[0].temp_mean_c == 8.8


def test_zonnedael_15min_electricity_returns_electricity_only():
    points = get_series(
        "zonnedael_15min_electricity",
        "Klant 34",
        datetime(2013, 1, 1),
        datetime(2013, 1, 1),
    )
    assert len(points) == 1
    assert points[0].interval_minutes == 15
    assert points[0].electricity_kwh == 0.03
    assert points[0].gas_m3 is None
