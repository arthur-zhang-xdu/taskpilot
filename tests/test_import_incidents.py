import json
from pathlib import Path
import pytest
from app.db.import_incidents import IncidentImportError, load_batch
from scripts.import_incidents import main


def example(**changes):
    return dict(incident_id='test-1', is_synthetic=True, service='payment-service',
                occurred_at='2026-10-01T08:00:00+08:00', error_type='timeout',
                severity='P2', message='模拟错误', resolution=None) | changes


def write_records(path, records):
    path.write_text(''.join(json.dumps(record, ensure_ascii=False)+'\n' for record in records), encoding='utf-8')
    return path


def test_normalized_duplicates_and_blank_lines(tmp_path):
    path = write_records(tmp_path/'in.jsonl', [example(), example(
        service=' payment-service ', occurred_at='2026-10-01T00:00:00Z', resolution=' ')])
    path.write_text('\n'+path.read_text()+'\n')
    batch = load_batch(path)
    assert batch.read == 2
    assert len(batch.records) == 1
    assert batch.records[0].line == 2
    assert load_batch(write_records(tmp_path/'empty', [])).read == 0


def test_file_conflict_reports_both_physical_lines(tmp_path):
    path=write_records(tmp_path/'in', [example(), example(message='不同的模拟错误')])
    path.write_text('\n'+path.read_text())
    with pytest.raises(IncidentImportError, match='第 3 行与第 2 行'):
        load_batch(path)


@pytest.mark.parametrize('record,field', [(example(severity='SECRET'),'severity'),
                                          (example(occurred_at='SECRET'),'occurred_at'),
                                          (example(SECRET='SECRET'),'未知字段'),
                                          ([], '记录')])
def test_validation_errors_do_not_echo_input(tmp_path, record, field):
    path=write_records(tmp_path/'in', [example(), record])
    with pytest.raises(IncidentImportError) as error:
        load_batch(path)
    assert '第 2 行' in str(error.value)
    assert field in str(error.value)
    assert 'SECRET' not in str(error.value)


def test_cli_invalid_input_does_not_connect(tmp_path, monkeypatch, capsys):
    import scripts.import_incidents as cli
    def forbidden():
        raise AssertionError('must not create engine')
    monkeypatch.setattr(cli, 'create_db_engine', forbidden)
    path=tmp_path/'in'
    path.write_text('\n{SECRET invalid json}\n')
    assert main(['--input', str(path)]) == 1
    output=capsys.readouterr()
    assert output.out == ''
    assert '第 2 行' in output.err
    assert 'SECRET' not in output.err


def test_sample_is_100_unique():
    batch=load_batch(Path('data/incidents/sample_incidents.jsonl'))
    assert batch.read == len(batch.records) == 100
