"""HTTP 与真实聚合交叉验证；只在自动创建的隔离库写入。"""
import os

import pytest
from fastapi.testclient import TestClient

from app.api.incidents import get_session_factory
from app.core.config import PROJECT_ROOT, Settings
from app.db.import_incidents import import_file
from app.main import create_app
from test_import_postgres import database, row, write

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_IMPORT_TESTS") != "1",
    reason="显式启用隔离 PostgreSQL 测试",
)


def test_http_handwritten_and_fixed_sample(database, tmp_path):
    from test_incident_analysis import SAMPLE, START, END
    from app.db.repository import summarize_incidents

    engine, factory, _ = database
    records = [row(incident_id=f"http-manual-{i}", **item)
               for i, item in enumerate(SAMPLE)]
    import_file(write(tmp_path / "manual.jsonl", records), factory)
    app = create_app(Settings(_env_file=None))
    app.dependency_overrides[get_session_factory] = lambda: factory
    with TestClient(app) as client:
        params = {"service": "payment", "start_time": START, "end_time": END,
                  "top_k": "1"}
        response = client.get("/incidents/summary", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["total_incidents"] == 5
        assert data["top_errors"] == [{"error_type": "a", "count": 2, "percentage": 40}]
        response = client.get("/incidents/summary", params={**params, "service": "missing"})
        assert response.status_code == 200
        assert response.json()["total_incidents"] == 0
        assert response.json()["top_errors"] == []

        import_file(PROJECT_ROOT / "data/incidents/sample_incidents.jsonl", factory)
        start, end = "2026-10-01T00:00:00+08:00", "2026-10-31T00:00:00+08:00"
        response = client.get("/incidents/summary", params={
            "service": "payment-service", "start_time": start, "end_time": end})
        assert response.status_code == 200
        data = response.json()
        baseline = summarize_incidents(factory, "payment-service", start, end)
        assert data["total_incidents"] == baseline["total_incidents"] == 49
        assert data["top_errors"] == baseline["top_errors"]
        assert [item["count"] for item in data["top_errors"]] == [16, 11, 11]
        assert engine.pool.checkedout() == 0
