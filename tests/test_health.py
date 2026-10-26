from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_service_status() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "piagent"}


def test_dashboard_is_served() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "PiAgent" in response.text
    assert "/health" in response.text
    assert "width=device-width" in response.text
    assert "Phone connection" in response.text
    assert "untrusted network" in response.text
