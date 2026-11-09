from fastapi.testclient import TestClient

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
