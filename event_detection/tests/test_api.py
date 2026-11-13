from fastapi.testclient import TestClient

import event_detection.api.app as api_module
from event_detection.api.app import app


def test_evaluation_uses_fixture_for_other_selected_household():
    response = TestClient(app).post(
        "/evaluate",
        json={
            "dataset": "zonnedael",
            "household": "Klant 10",
            "module": "nilm",
            "method": "rules",
            "scenario": "high_use",
        },
    )
    assert response.status_code == 200
    assert "Klant 34" in response.json()["source"]


def test_evaluation_supports_isolation_forest():
    response = TestClient(app).post(
        "/evaluate",
        json={
            "dataset": "zonnedael",
            "household": "Klant 34",
            "module": "anomaly",
            "method": "isolation_forest",
            "scenario": "high_use",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "isolation_forest" in body["source"]
    assert "unusual_gas" in {metric["event_type"] for metric in body["metrics"]}


def test_event_summary_returns_quality_and_event_statistics():
    response = TestClient(app).get(
        "/event-summary",
        params={
            "dataset": "zonnedael",
            "household": "Klant 34",
            "module": "anomaly",
            "method": "isolation_forest",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total_points"] == 365
    assert body["valid_points"] == 364
    assert body["event_count"] == len(body["events"])
    assert "events_by_type" in body
    assert body["test_split"]["training_ratio"] == (
        body["test_split"]["training_points"] / body["valid_points"]
    )
    assert body["test_split"]["training_points"] < body["total_points"]


def test_series_range_returns_household_dataset_bounds():
    response = TestClient(app).get(
        "/series-range",
        params={"dataset": "zonnedael_15min_electricity", "household": "Klant 34"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["start_date"] == "2013-01-01"
    assert body["end_date"] == "2013-12-31"
    assert body["resolution_minutes"] == 15


def test_event_summary_rejects_unsupported_rnn_lookback():
    response = TestClient(app).get(
        "/event-summary",
        params={
            "dataset": "zonnedael_hourly",
            "household": "Klant 34",
            "module": "anomaly",
            "method": "rnn",
            "lookback_days": 2,
        },
    )

    assert response.status_code == 422


def test_rnn_evaluation_rejects_daily_only_scenarios():
    response = TestClient(app).post(
        "/evaluate",
        json={
            "dataset": "zonnedael",
            "household": "Klant 34",
            "module": "anomaly",
            "method": "rnn",
        },
    )

    assert response.status_code == 400
    assert "daily-only" in response.json()["detail"]


def test_rnn_summary_rejects_daily_resolution():
    response = TestClient(app).get(
        "/event-summary",
        params={
            "dataset": "zonnedael",
            "household": "Klant 34",
            "module": "anomaly",
            "method": "rnn",
        },
    )

    assert response.status_code == 400
    assert "hourly and 15-minute" in response.json()["detail"]


def test_benchmark_runs_selected_household_with_weather_audit():
    response = TestClient(app).post(
        "/benchmark",
        json={
            "dataset": "zonnedael",
            "household": "Klant 34",
            "patterns": ["spikes"],
            "seed": 13,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["weather_audit"]["weather_gas_enabled"] is True
    result = body["results"][0]
    assert result["household"] == "Klant 34"
    assert {method["method"] for method in result["methods"] if method["applicable"]} == {
        "rules", "isolation_forest"
    }


def test_all_household_benchmark_queues_progress_job(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "run_household_benchmark",
        lambda dataset, household, patterns, seed, weather_gas_enabled, lookback_days, strengths: {
            "household": household,
            "methods": [],
        },
    )
    client = TestClient(app)
    started = client.post("/benchmark", json={"dataset": "zonnedael", "all_households": True})

    assert started.status_code == 200
    job_id = started.json()["job_id"]
    status = client.get(f"/benchmark/jobs/{job_id}")

    assert status.status_code == 200
    assert status.json()["total_households"] == 58
    assert status.json()["status"] in {"queued", "running", "completed"}
