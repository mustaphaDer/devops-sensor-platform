import random

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_and_ready():
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_normal_readings_are_not_anomalies_and_spike_is():
    rng = random.Random(0)
    for _ in range(50):
        r = client.post("/readings", json={"machine_id": "press-1", "value": 60 + rng.gauss(0, 1)})
        assert r.status_code == 201
    spike = client.post("/readings", json={"machine_id": "press-1", "value": 90}).json()
    assert spike["anomaly"] is True and spike["z_score"] > 3


def test_first_readings_never_flagged():
    r = client.post("/readings", json={"machine_id": "new-1", "value": 1e6}).json()
    assert r["anomaly"] is False and r["z_score"] is None


def test_validation_rejects_bad_input():
    assert client.post("/readings", json={"machine_id": "bad id!", "value": 1}).status_code == 422
    assert client.post("/readings", json={"machine_id": "m", "value": "hot"}).status_code == 422


def test_stats_and_404():
    client.post("/readings", json={"machine_id": "lathe-7", "value": 10})
    client.post("/readings", json={"machine_id": "lathe-7", "value": 20})
    body = client.get("/machines/lathe-7/stats").json()
    assert body["count"] == 2 and body["mean"] == 15
    assert client.get("/machines/nope/stats").status_code == 404


def test_metrics_exposed_with_route_labels():
    client.post("/readings", json={"machine_id": "m-metrics", "value": 1})
    text = client.get("/metrics").text
    assert 'sensor_readings_total{machine="m-metrics"} 1.0' in text
    assert 'route="/readings"' in text
    assert 'route="/machines/{machine_id}/stats"' in text or "http_requests_total" in text
