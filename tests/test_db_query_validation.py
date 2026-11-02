import pytest
from app.db.repository import query_incidents, summarize_incidents
from scripts.analyze_db_incidents import main

START='2026-10-01T00:00:00+08:00'
END='2026-10-02T00:00:00+08:00'


def forbidden():
    raise AssertionError('不应连接数据库')


@pytest.mark.parametrize('service,start,end', [('', START, END), ('  ', START, END),
    (False, START, END), ('payment', 'bad', END), ('payment', START, START),
    ('payment', END, START), ('payment', '2026-10-01T00:00:00', END),
    ('payment', START, None)])
def test_invalid_range_without_connection(service,start,end):
    for operation in (query_incidents, summarize_incidents):
        with pytest.raises(ValueError):
            operation(forbidden,service,start,end)


@pytest.mark.parametrize('top_k', [0,-1,True,1.5,'3'])
def test_invalid_top_k_without_connection(top_k):
    with pytest.raises(ValueError):
        summarize_incidents(forbidden,'payment',START,END,top_k)


def test_cli_bad_arguments_do_not_connect(monkeypatch,capsys):
    monkeypatch.setattr('scripts.analyze_db_incidents.create_db_engine', forbidden)
    assert main(['--service','payment','--start','SECRET','--end',END])==1
    output=capsys.readouterr()
    assert output.out==''
    assert 'SECRET' not in output.err
