import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_config_priority(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_NAME=FromFile\nLLM_TIMEOUT_SECONDS=45\n", encoding="utf-8")
    assert Settings(_env_file=dotenv).app_name == "FromFile"
    monkeypatch.setenv("APP_NAME", "FromEnvironment")
    assert Settings(_env_file=dotenv).app_name == "FromEnvironment"
    assert Settings(app_name="Explicit", _env_file=dotenv).app_name == "Explicit"
    assert Settings(_env_file=dotenv).llm_timeout_seconds == 45


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
def test_invalid_timeout(monkeypatch, value):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", value)
    with pytest.raises(ValidationError):
        Settings()


def test_invalid_level_hides_input(monkeypatch):
    secret = "test-sensitive-value"
    monkeypatch.setenv("LOG_LEVEL", secret)
    with pytest.raises(ValidationError) as error:
        Settings()
    assert secret not in str(error.value)
    assert "log_level" in str(error.value)


def test_secret_is_masked():
    settings = Settings(llm_api_key="test-only-secret")
    assert "test-only-secret" not in repr(settings)
    assert "test-only-secret" not in settings.model_dump_json()
