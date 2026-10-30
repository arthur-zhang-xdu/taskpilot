from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app


def test_app_without_key_or_network(monkeypatch):
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("健康检查不应连接外网")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok", "service": "TaskPilot"}
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/health/live" in schema.json()["paths"]
        assert client.get("/missing").status_code == 404


def test_injected_config_does_not_expose_key():
    settings = Settings(app_name="TestPilot", llm_api_key="test-only-secret")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")
        assert response.json() == {"status": "ok", "service": "TestPilot"}
        assert "test-only-secret" not in response.text
