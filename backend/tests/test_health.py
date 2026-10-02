"""HTTP contracts for process liveness and database readiness probes."""


def test_healthz_is_live_without_database_dependency(client):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_initialized_database(client):
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readyz_rejects_traffic_before_application_is_ready(client, monkeypatch):
    import main

    monkeypatch.setattr(main.app.state, "ready", False)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_readyz_rejects_traffic_when_database_probe_fails(client, monkeypatch):
    import main

    monkeypatch.setattr(main, "check_database_connection", lambda: False)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "detail": "Database is unavailable.",
    }