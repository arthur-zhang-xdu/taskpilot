"""只在本脚本创建的唯一临时库中测试迁移和约束。"""
from uuid import uuid4
from pathlib import Path
import json
from datetime import timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import IntegrityError
from alembic.config import Config
from alembic import command
from app.core.config import Settings
from app.db.session import database_url, create_session_factory, session_scope
from app.db.models import Incident
from app.schemas.incident import IncidentInput

url = database_url(Settings())
admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
name = 'taskpilot_step4_test_' + uuid4().hex
with admin.connect() as conn:
    conn.execute(text(f'CREATE DATABASE "{name}"'))
engine = create_engine(url.set(database=name), connect_args={'options': '-c timezone=UTC'})
try:
    cfg=Config('alembic.ini')
    with engine.begin() as conn:
        cfg.attributes['connection']=conn
        command.upgrade(cfg, 'head')
        command.check(cfg)
        assert conn.execute(text('select version_num from alembic_version')).scalar_one() == '0001_create_incidents'
    schema=inspect(engine)
    assert schema.get_pk_constraint('incidents')['constrained_columns']==['incident_id']
    assert len(schema.get_check_constraints('incidents'))==5
    assert schema.get_indexes('incidents')[0]['column_names']==['service','occurred_at']
    data=json.loads(Path('data/incidents/sample_incidents.jsonl').read_text().splitlines()[0])
    normalized=IncidentInput.model_validate(data).model_dump()
    factory=create_session_factory(engine)
    with session_scope(factory) as session:
        session.add(Incident(**normalized))
    with session_scope(factory) as session:
        record=session.get(Incident,normalized['incident_id'])
        assert record.occurred_at == normalized['occurred_at']
        assert record.occurred_at.tzinfo == timezone.utc
    for patch in [{'incident_id':normalized['incident_id']}, {'severity':'P9'}, {'service':' \t\n'}, {'message':None}]:
        bad={**normalized,'incident_id':uuid4().hex,**patch}
        try:
            with session_scope(factory) as session:
                session.add(Incident(**{**normalized,'incident_id':'rollback_'+uuid4().hex}))
                session.flush()
                session.add(Incident(**bad))
        except IntegrityError:
            pass
        else:
            raise AssertionError('constraint not enforced')
    with engine.connect() as conn:
        assert conn.execute(text('select count(*) from incidents')).scalar_one()==1
    with engine.begin() as conn:
        cfg.attributes['connection']=conn
        command.downgrade(cfg,'base')
        assert 'incidents' not in inspect(conn).get_table_names()
        command.upgrade(cfg,'head')
    print('PASS: isolated PostgreSQL migration, metadata parity, constraints, UTC roundtrip, transaction rollback, downgrade/upgrade')
finally:
    engine.dispose()
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE "{name}"'))
    admin.dispose()
