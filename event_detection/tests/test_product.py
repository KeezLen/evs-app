from fastapi.testclient import TestClient
from event_detection.api.app import app
from event_detection.evaluation.scenarios import load_scenario
from event_detection.product import analyze_household

client = TestClient(app)


def test_product_uses_one_household_and_does_not_claim_real_savings():
    response = client.post('/product/analyze', json={'dataset': 'zonnedael', 'household': 'Klant 34',
        'home': {'energy_label': 'C'}})
    assert response.status_code == 200
    body = response.json()
    assert body['profile']['household_id'] == body['advice_context']['household_id'] == 'Klant 34'
    assert body['advice_context']['home']['energy_label'] == 'C'
    assert body['advice_context']['allow_heating_reduction'] is False
    assert 'savings' not in body
    assert len(body['daily_series']) == 365
    assert all(e['type'] in ('high_gas', 'high_electricity') for e in body['events'])


def test_product_short_history_has_no_events_and_gaps_are_not_events():
    short, _, _ = load_scenario('incomplete', 'Klant 34')
    assert analyze_household(short, 'Klant 34', {})['events'] == []
    missing, _, _ = load_scenario('missing', 'Klant 34')
    result = analyze_household(missing, 'Klant 34', {})
    problems = {q['date']: q['fuels'] for q in result['profile']['data_quality']}
    for event in result['events']:
        fuel = 'gas_m3' if event.type == 'high_gas' else 'electricity_kwh'
        assert fuel not in problems.get(str(event.start.date()), [])


def test_product_range_validation_and_no_future_rows():
    base = {'dataset': 'zonnedael', 'household': 'Klant 34'}
    response = client.post('/product/analyze', json={**base, 'range_start': '2013-03-22', 'range_end': '2013-03-31'})
    assert response.status_code == 200
    assert response.json()['profile']['status'] == 'insufficient_history'
    assert response.json()['events'] == []
    assert client.post('/profiles/build', json={**base, 'range_end': '2013-01-10'}).json()['profile']['period']['observed_days'] == 10
    for fields in ({'range_start': '2014-01-01', 'range_end': '2013-01-01'}, {'range_start': '2013-01-01T00:00:00Z'}):
        assert client.post('/product/analyze', json={**base, **fields}).status_code == 422
    assert client.post('/product/analyze', json={**base, 'household': 'Klant 1'}).status_code == 400


def test_app_and_analyst_views_are_served_by_same_service():
    for path in ('/app', '/event_detection.html', '/event_benchmark.html'):
        response = client.get(path)
        assert response.status_code == 200
        assert 'text/html' in response.headers['content-type']
