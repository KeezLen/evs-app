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


def test_benchmark_runs_selected_household_with_weather_audit(monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "_BENCHMARK_RESULT_DIR", tmp_path)
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
    assert body["protocol"] == "corrected_v2"
    assert body["id"]
    assert body["source"] == "automatic"
    assert body["weather_audit"]["weather_gas_enabled"] is True
    result = body["results"][0]
    assert result["household"] == "Klant 34"
    assert result["protocol"] == "corrected_v2"
    assert {method["method"] for method in result["methods"] if method["applicable"]} == {
        "rules", "isolation_forest", "no_alert", "random_budget_rules", "random_budget_isolation_forest"
    }
    assert result["detector_support"]["rnn"]["electricity"]["status"] == "unsupported_resolution"
    random_baseline = next(method for method in result["methods"] if method["method"] == "random_budget_rules")
    assert random_baseline["random_alerts_generated"] == random_baseline["random_alert_budget"]


def test_benchmark_macro_excludes_undefined_metrics_and_reports_support():
    def household(name, precision, recall, f1, detected, truth, matched):
        return {"household": name, "methods": [{"method": "test", "applicable": True,
                "normal_scores": {"classes": []}, "scores": {"classes": [{
                    "signal": "electricity", "direction": "high", "precision": precision,
                    "recall": recall, "f1": f1, "detected": detected,
                    "ground_truth": truth, "matched": matched, "false_positives": detected - matched,
                }]}}]}

    rows = api_module._benchmark_aggregate([
        household("A", None, 0.0, 0.0, 0, 1, 0),
        household("B", 0.5, 0.5, 0.5, 2, 2, 1),
    ])
    row = rows[0]
    assert (row["macro_precision"], row["macro_recall"], row["macro_f1"]) == (0.5, 0.25, 0.25)
    assert (row["precision_households"], row["recall_households"], row["f1_households"]) == (1, 2, 2)
    assert (row["detected"], row["ground_truth"], row["matched"]) == (2, 3, 1)


def test_all_household_benchmark_queues_progress_job(monkeypatch):
    monkeypatch.setattr(
        api_module,
        "run_household_benchmark",
        lambda dataset, household, patterns, seed, weather_gas_enabled, lookback_days, strengths, protocol: {
            "household": household,
            "methods": [],
        },
    )
    monkeypatch.setattr(api_module._BENCHMARK_EXECUTOR, "submit", lambda *args: None)
    client = TestClient(app)
    started = client.post("/benchmark", json={"dataset": "zonnedael", "all_households": True})

    assert started.status_code == 200
    job_id = started.json()["job_id"]
    status = client.get(f"/benchmark/jobs/{job_id}")

    assert status.status_code == 200
    assert status.json()["total_households"] == 58
    assert status.json()["status"] in {"queued", "running", "completed"}


def test_completed_background_benchmark_is_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "_BENCHMARK_RESULT_DIR", tmp_path)
    monkeypatch.setattr(
        api_module,
        "run_household_benchmark",
        lambda dataset, household, patterns, seed, weather_gas_enabled, lookback_days, strengths, protocol: {
            "dataset": dataset,
            "household": household,
            "protocol": protocol,
            "methods": [],
        },
    )
    job_id = "test-job"
    api_module._BENCHMARK_JOBS[job_id] = {"job_id": job_id, "status": "queued"}

    api_module._run_benchmark_job(
        job_id,
        api_module.BenchmarkRequest(dataset="zonnedael", all_households=True),
        ["Klant 34"],
        {"weather_gas_enabled": False},
    )

    job = api_module._BENCHMARK_JOBS[job_id]
    assert job["status"] == "completed"
    assert job["saved_result_id"]
    saved = TestClient(app).get(f"/benchmark/saved/{job['saved_result_id']}")
    assert saved.status_code == 200
    assert saved.json()["dataset"] == "zonnedael"
    assert saved.json()["result"]["seed"] == 17
    assert saved.json()["result"]["all_households"] is True
    assert saved.json()["result"]["results"][0]["household"] == "Klant 34"


def test_manual_saved_run_can_be_listed_and_retrieved(monkeypatch, tmp_path):
    monkeypatch.setattr(api_module, "_BENCHMARK_RESULT_DIR", tmp_path)
    client = TestClient(app)
    result = {
        "status": "completed",
        "protocol": "corrected_v2",
        "results": [{"dataset": "zonnedael_hourly", "household": "Klant 34"}],
        "aggregate": [],
    }

    saved = client.post("/benchmark/saved", json={"result": result})

    assert saved.status_code == 200
    assert saved.json()["source"] == "manual"
    listed = client.get("/benchmark/saved")
    assert [row["id"] for row in listed.json()] == [saved.json()["id"]]
    loaded = client.get(f"/benchmark/saved/{saved.json()['id']}")
    assert loaded.status_code == 200
    assert loaded.json()["result"] == result
    assert client.get("/benchmark/saved/not-an-id").status_code == 404
