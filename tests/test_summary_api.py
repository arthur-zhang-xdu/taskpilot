from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.api import incidents
from app.core.config import Settings
from app.main import create_app


PARAMS = {"service": " payment-service ",
          "start_time": "2026-10-01T00:00:00+08:00",
          "end_time": "2026-10-31T00:00:00+08:00"}


def test_summary_contract_and_resource_lifecycle(monkeypatch):
    engine = Mock()
    factory = object()
    create_engine = Mock(return_value=engine)
    monkeypatch.setattr(incidents, "create_db_engine", create_engine)
    monkeypatch.setattr(incidents, "create_session_factory", lambda _: factory)
    calls = []

    def summarize(received_factory, **query):
        assert received_factory is factory
        calls.append(query)
        return {"service": query["service"],
                "start_inclusive": query["start_time"],
                "end_exclusive": query["end_time"],
                "top_k": query["top_k"], "total_incidents": 5,
                "top_errors": [{"error_type": "a", "count": 2, "percentage": 40}]}

    monkeypatch.setattr(incidents, "summarize_incidents", summarize)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/openapi.json").status_code == 200
        create_engine.assert_not_called()
        for _ in range(2):
            response = client.get("/incidents/summary", params={**PARAMS, "top_k": "1"})
            assert response.status_code == 200
            data = response.json()
            assert data["total_incidents"] == 5
            assert data["top_errors"][0]["percentage"] == 40
            assert data["data_source"] == "synthetic_incidents"
        assert calls[0] == {"service": "payment-service", "top_k": 1,
                            "start_time": "2026-09-30T16:00:00+00:00",
                            "end_time": "2026-10-30T16:00:00+00:00"}
        create_engine.assert_called_once()
        engine.dispose.assert_not_called()
    engine.dispose.assert_called_once()


@pytest.mark.parametrize("change", [
    {"service": " "}, {"start_time": "2026-10-01T00:00:00"},
    {"end_time": PARAMS["start_time"]}, {"top_k": "0"},
    {"top_k": "-1"}, {"top_k": "1.5"}, {"top_k": "true"},
])
def test_invalid_query(change):
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/incidents/summary", params={**PARAMS, **change}).status_code == 422


def test_empty_and_database_failure(monkeypatch):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[incidents.get_session_factory] = lambda: object()

    def empty(_, **query):
        return {"service": query["service"], "start_inclusive": query["start_time"],
                "end_exclusive": query["end_time"], "top_k": query["top_k"],
                "total_incidents": 0, "top_errors": []}

    monkeypatch.setattr(incidents, "summarize_incidents", empty)
    with TestClient(app) as client:
        response = client.get("/incidents/summary", params=PARAMS)
        assert response.status_code == 200
        assert response.json()["top_errors"] == []

        def unavailable(*args, **kwargs):
            raise OperationalError("secret SQL", {}, Exception("secret password"))

        monkeypatch.setattr(incidents, "summarize_incidents", unavailable)
        response = client.get("/incidents/summary", params=PARAMS)
        assert response.status_code == 503
        assert response.json() == {"detail": "数据库服务暂不可用"}


def test_missing_database_configuration():
    with TestClient(create_app(Settings(_env_file=None))) as client:
        assert client.get("/incidents/summary", params=PARAMS).status_code == 503


@pytest.mark.parametrize("missing", ["service", "start_time", "end_time"])
def test_missing_parameter_never_initializes_database(monkeypatch, missing):
    create_engine = Mock(side_effect=AssertionError("不应初始化数据库"))
    monkeypatch.setattr(incidents, "create_db_engine", create_engine)
    with TestClient(create_app(Settings(_env_file=None))) as client:
        params = {key: value for key, value in PARAMS.items() if key != missing}
        assert client.get("/incidents/summary", params=params).status_code == 422
    create_engine.assert_not_called()


def test_programming_error_is_not_disguised_as_unavailability(monkeypatch):
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[incidents.get_session_factory] = lambda: object()

    def broken(*args, **kwargs):
        raise RuntimeError("programming error")

    monkeypatch.setattr(incidents, "summarize_incidents", broken)
    with TestClient(app) as client:
        with pytest.raises(RuntimeError, match="programming error"):
            client.get("/incidents/summary", params=PARAMS)
