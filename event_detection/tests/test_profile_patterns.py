from datetime import datetime, timedelta
import pytest
from event_detection.household_profile import build_profile
from event_detection.schemas import SeriesPoint


def series(values, gas=False):
    return [SeriesPoint(timestamp=datetime(2013,1,1)+timedelta(days=i),
        quality_flag='ok', electricity_kwh=v, n_elec_intervals=96,
        gas_m3=v if gas else None, n_gas_hours=24 if gas else None)
        for i,v in enumerate(values)]


def codes(profile, fuel='electricity_kwh'):
    return {label['code'] for label in profile['fuels'][fuel]['patterns']['labels']}


@pytest.mark.parametrize('values,expected', [([10]*42,'steady_pattern'), ([1,19]*21,'high_variance'), ([8,12]*21,'variable_pattern'), ([0]*42,'no_recorded_use')])
def test_variability_labels_have_explicit_metrics(values, expected):
    profile=build_profile(series(values),'test')
    assert expected in codes(profile)
    assert profile['fuels']['electricity_kwh']['patterns']['policy']['validated'] is False


def test_weekend_effect_and_insufficient_history():
    points=series([10]*56)
    for point in points:
        if point.timestamp.weekday() >= 5:
            point.electricity_kwh=20
    assert 'weekend_higher' in codes(build_profile(points,'test'))
    assert codes(build_profile(points[:10],'test')) == {'insufficient_history'}


def test_gas_does_not_confuse_cold_weather_with_variability():
    points=series([2+0.7*(i%20) for i in range(60)],gas=True)
    for i,point in enumerate(points): point.hdd18=i%20
    profile=build_profile(points,'test')
    patterns=profile['fuels']['gas_m3']['patterns']
    assert 'steady_pattern' in codes(profile,'gas_m3')
    assert patterns['metrics']['raw_daily_cv'] > 0.35
    assert patterns['metrics']['classification_cv'] < 1e-10
    points[20].gas_m3=100
    assert 'high_variance' in codes(build_profile(points,'test'),'gas_m3')


def test_gas_without_weather_abstains():
    assert codes(build_profile(series([10]*42,gas=True),'test'),'gas_m3') == {'weather_context_needed'}
