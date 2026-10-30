"""所有新增测试都隔离开发环境和真实 .env。"""
import pytest
from app.core.config import Settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", tmp_path / "absent.env")
