from datetime import datetime
from statistics import mean

from fastapi.testclient import TestClient

from event_detection.api.app import app
from event_detection.data import get_series
from event_detection.household_profile import build_profile
from event_detection.schemas import SeriesPoint

client = TestClient(app)


def test_profile_uses_catalog_households_and_shared_series():
    dataset = next(d for d in client.get('/datasets').json() if d['id'] == 'zonnedael')
    assert 'Klant 34' in dataset['households']
    response = client.post('/profiles/build', json={
        'dataset': dataset['id'], 'household': 'Klant 34',
        'home': {'energy_label': 'C', 'floor_area_m2': 70},
    })
    assert response.status_code == 200
    profile = response.json()['profile']
    points = get_series('zonnedael', 'Klant 34')
    electricity = [p.electricity_kwh for p in points if p.n_elec_intervals == 96 and p.electricity_kwh is not None]
    assert profile['fuels']['electricity_kwh']['mean_daily'] == mean(electricity)
    assert profile['home']['energy_label'] == 'C'
    assert profile['home']['floor_area_m2'] == 70
    assert profile['home']['sleep_schedule'] is None
    assert profile['fuels']['gas_m3']['peak_hour'] is None
    assert 'expected_usage' not in response.json()


def test_profile_preserves_quality_per_fuel_and_weekday_patterns():
    points = [
        SeriesPoint(timestamp=datetime(2013, 1, 7), quality_flag='partial', electricity_kwh=12, n_elec_intervals=96, gas_m3=4, n_gas_hours=22),
        SeriesPoint(timestamp=datetime(2013, 1, 8), quality_flag='ok', electricity_kwh=8, n_elec_intervals=96, gas_m3=6, n_gas_hours=24),
        SeriesPoint(timestamp=datetime(2013, 1, 9), quality_flag='missing', electricity_kwh=0, n_elec_intervals=0),
    ]
    profile = build_profile(points, 'test')
    assert profile['fuels']['electricity_kwh']['mean_daily'] == 10
    assert profile['fuels']['electricity_kwh']['highest_usage_weekdays'] == [0]
    assert profile['fuels']['gas_m3']['mean_daily'] == 6
    assert profile['fuels']['gas_m3']['valid_days'] == 1
    assert profile['fuels']['gas_m3']['by_weekday']['0'] is None
    assert profile['home']['woning_type'] is None


def test_profile_matches_existing_api_error_conventions():
    for dataset, household in [('zonnedael', 'Klant 1'), ('unknown', 'Klant 34')]:
        assert client.post('/profiles/build', json={'dataset': dataset, 'household': household}).status_code == 400
    assert client.post('/profiles/build', json={'dataset': 'zonnedael', 'household': 'Klant 34', 'home': {'floor_area_m2': -1}}).status_code == 422
