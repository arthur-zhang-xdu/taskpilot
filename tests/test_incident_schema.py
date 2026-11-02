import json
from datetime import timedelta
from pathlib import Path
import pytest
from pydantic import ValidationError
from app.schemas.incident import IncidentInput
from app.core.config import Settings
from app.db.session import create_db_engine, database_url


def sample():
    return json.loads(Path('data/incidents/sample_incidents.jsonl').read_text().splitlines()[0])


def test_normalization_and_all_samples():
    for line in Path('data/incidents/sample_incidents.jsonl').read_text().splitlines():
        record = IncidentInput.model_validate_json(line)
        assert record.occurred_at.utcoffset() == timedelta(0)
    data = sample()
    data.update(service=' payment-service ', resolution='  ', occurred_at='2026-10-01T08:00:00+08:00')
    first = IncidentInput.model_validate(data)
    data['occurred_at'] = '2026-10-01T00:00:00Z'
    assert first == IncidentInput.model_validate(data)
    assert first.service == 'payment-service'
    assert first.resolution is None


@pytest.mark.parametrize('change', [
    {'incident_id': ' \t\n'}, {'service': 1}, {'message': False},
    {'severity': 'p1'}, {'is_synthetic': 'true'}, {'is_synthetic': False},
    {'occurred_at': '2026-10-01T00:00:00'}, {'occurred_at': 1790812800},
    {'unknown': 'value'},
])
def test_reject_invalid(change):
    data = sample()
    data.update(change)
    with pytest.raises(ValidationError):
        IncidentInput.model_validate(data)


def test_engine_is_lazy_and_password_is_protected(monkeypatch):
    import socket
    def forbidden(*args, **kwargs):
        raise AssertionError('unexpected network')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    settings = Settings(_env_file=None, postgres_user='test', postgres_db='test',
                        postgres_password='a@b%pass')
    assert database_url(settings).password == 'a@b%pass'
    assert 'a@b%pass' not in repr(settings)
    engine = create_db_engine(settings)
    engine.dispose()
