"""显式启用后，在自行创建的隔离 PostgreSQL 库中测试导入。"""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, PROJECT_ROOT
from app.db.import_incidents import IncidentImportError, ImportResult, import_file
from app.db.models import Incident
from app.db.session import database_url, create_session_factory
from scripts.import_incidents import main

pytestmark = pytest.mark.skipif(os.getenv('RUN_POSTGRES_IMPORT_TESTS') != '1',
                                reason='显式设置 RUN_POSTGRES_IMPORT_TESTS=1 才创建隔离测试库')


@pytest.fixture
def database():
    url = database_url(Settings(_env_file=PROJECT_ROOT / '.env'))
    admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    name = 'taskpilot_import_test_' + uuid4().hex
    engine = None
    created = False
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
        created = True
        test_url = url.set(database=name)
        engine = create_engine(test_url, connect_args={'options': '-c timezone=UTC'})
        with engine.begin() as conn:
            config = Config(str(PROJECT_ROOT / 'alembic.ini'))
            config.attributes['connection'] = conn
            command.upgrade(config, 'head')
        yield engine, create_session_factory(engine), test_url
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as conn:
                conn.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def row(**changes):
    return dict(incident_id='one', is_synthetic=True, service='payment-service',
                occurred_at='2026-10-01T08:00:00+08:00', error_type='timeout',
                severity='P2', message='模拟', resolution=None) | changes


def write(path, rows):
    path.write_text(''.join(json.dumps(item)+'\n' for item in rows))
    return path


def count(engine):
    with engine.connect() as conn:
        return conn.scalar(select(func.count()).select_from(Incident))


def test_sample_idempotency(database, tmp_path):
    engine, factory, _ = database
    sample = PROJECT_ROOT / 'data/incidents/sample_incidents.jsonl'
    assert import_file(sample, factory) == ImportResult(100, 100, 0)
    assert import_file(sample, factory) == ImportResult(100, 0, 100)
    assert count(engine) == 100
    with Session(engine) as session:
        stored = {record.incident_id: record for record in session.scalars(select(Incident))}
        from app.db.import_incidents import load_batch
        for record in load_batch(sample).records:
            expected = record.incident.model_dump()
            assert {key: getattr(stored[expected['incident_id']], key) for key in expected} == expected


def test_normalized_duplicates_conflicts_and_bad_batch(database, tmp_path):
    engine, factory, _ = database
    path = tmp_path/'in'
    assert import_file(write(path, [row(), row(occurred_at='2026-10-01T00:00:00Z',
                                             service=' payment-service ', resolution=' ')]), factory) == ImportResult(2, 1, 1)
    assert import_file(path, factory) == ImportResult(2, 0, 2)
    for records in ([row(incident_id='new'), row(message='冲突')],
                    [row(incident_id='new'), row(severity='P9')],
                    [row(incident_id='new'), row(incident_id='new', message='文件内冲突')]):
        with pytest.raises(IncidentImportError):
            import_file(write(path, records), factory)
        assert count(engine) == 1
    assert import_file(write(path, []), factory) == ImportResult(0, 0, 0)


def test_write_failure_rolls_back_flushed_rows(database, tmp_path):
    engine, factory, _ = database
    path = write(tmp_path/'in', [row(incident_id='first'), row(incident_id='second')])
    # 确定性模拟“查重后发生并发唯一冲突”：先真正 flush 一行，再重复插入同 ID。
    def concurrent_conflict(session, flush_context, instances):
        pending = list(session.new)
        if pending:
            first = pending[0]
            session.connection().execute(Incident.__table__.insert().values(
                **{column.name: getattr(first, column.name) for column in Incident.__table__.columns}))
            assert session.connection().scalar(select(func.count()).select_from(Incident)) == 1
    event.listen(factory, 'before_flush', concurrent_conflict)
    try:
        with pytest.raises(IntegrityError):
            import_file(path, factory)
    finally:
        event.remove(factory, 'before_flush', concurrent_conflict)
    assert count(engine) == 0


def test_cli_counts_and_error_exit(database, tmp_path, monkeypatch, capsys):
    engine, factory, url = database
    monkeypatch.setenv('DATABASE_URL', url.render_as_string(hide_password=False))
    path = write(tmp_path/'in', [row()])
    assert main(['--input', str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {'read': 1, 'inserted': 1, 'skipped': 0}
    assert main(['--input', str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == {'read': 1, 'inserted': 0, 'skipped': 1}
    write(path, [row(incident_id='new'), row(message='SECRET_VALUE')])
    assert main(['--input', str(path)]) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert '第 2 行' in output.err
    assert 'SECRET_VALUE' not in output.err
    assert url.render_as_string(hide_password=False) not in output.err
    assert count(engine) == 1


def test_query_handwritten_boundaries_and_totals(database, tmp_path):
    from app.db.repository import query_incidents, summarize_incidents
    from test_incident_analysis import SAMPLE, START, END
    engine, factory, _ = database
    records = [row(incident_id=f'manual-{index}', **item) for index,item in enumerate(SAMPLE)]
    import_file(write(tmp_path/'manual', records), factory)
    expected = [
        {'error_type':'a','count':2,'percentage':40.0},
        {'error_type':'b','count':2,'percentage':40.0},
        {'error_type':'c','count':1,'percentage':20.0},
    ]
    result=summarize_incidents(factory,' payment ',START,END)
    assert result['total_incidents']==5
    assert result['top_errors']==expected
    assert summarize_incidents(factory,'payment',START,END,1)['top_errors']==expected[:1]
    assert summarize_incidents(factory,'payment',START,END,1)['total_incidents']==5
    assert summarize_incidents(factory,'payment',START,END,10)['top_errors']==expected
    assert summarize_incidents(factory,'payment','2026-09-30T16:00:00Z',
                               '2026-10-01T16:00:00Z')==result
    found=query_incidents(factory,'payment',START,END)
    assert [item['incident_id'] for item in found]==[f'manual-{i}' for i in range(1,6)]
    assert query_incidents(factory,'missing',START,END)==[]
    for service,start,end in [('missing',START,END),('payment','2027-01-01T00:00:00Z','2027-01-02T00:00:00Z')]:
        empty=summarize_incidents(factory,service,start,end)
        assert empty['total_incidents']==0
        assert empty['top_errors']==[]
    # 等价时区的记录落在起点；同一时刻的明细按 ID 稳定排序。
    import_file(write(tmp_path/'extra', [row(incident_id='manual-00',service='payment',
                                          occurred_at='2026-09-30T16:00:00Z',error_type='b')]), factory)
    assert [item['incident_id'] for item in query_incidents(factory,'payment',START,END)][:2]==['manual-00','manual-1']
    assert summarize_incidents(factory,'payment',START,END)['total_incidents']==6
    # 服务名作为绑定值，不能改变 SQL 条件。
    assert summarize_incidents(factory,"payment' OR 1=1 --",START,END)['total_incidents']==0


def test_query_actual_sample_and_cli(database, monkeypatch, capsys):
    from app.db.repository import summarize_incidents
    from scripts.analyze_db_incidents import main as analyze_main
    from scripts.analyze_incidents import analyze_incidents, load_incidents
    engine,factory,url=database
    path=PROJECT_ROOT/'data/incidents/sample_incidents.jsonl'
    import_file(path,factory)
    start='2026-10-01T00:00:00+08:00'
    end='2026-10-31T00:00:00+08:00'
    result=summarize_incidents(factory,'payment-service',start,end)
    assert result['total_incidents']==49
    assert result['top_errors']==[
        {'error_type':'connection_timeout','count':16,'percentage':32.65},
        {'error_type':'database_connection_error','count':11,'percentage':22.45},
        {'error_type':'upstream_http_5xx','count':11,'percentage':22.45},
    ]
    baseline=analyze_incidents(load_incidents(path),'payment-service',start,end)
    assert result['top_errors']==baseline['top_errors']
    monkeypatch.setenv('DATABASE_URL',url.render_as_string(hide_password=False))
    assert analyze_main(['--service','payment-service','--start',start,'--end',end])==0
    assert json.loads(capsys.readouterr().out)==result
