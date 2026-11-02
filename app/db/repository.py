"""受限故障查询；统计和 Top K 排序在 PostgreSQL 内完成。"""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.models import Incident
from app.db.session import session_scope
from app.schemas.incident import IncidentInput


def validate_range(service: str, start_time: str, end_time: str):
    if not isinstance(service, str) or not service.strip():
        raise ValueError('服务名称不能为空')
    times = []
    for value in (start_time, end_time):
        if not isinstance(value, str):
            raise ValueError('时间必须为带时区的 ISO 8601 字符串')
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError('时间必须为带时区的 ISO 8601 字符串') from None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError('时间必须包含时区')
        times.append(parsed.astimezone(timezone.utc))
    start, end = times
    if start >= end:
        raise ValueError('开始时间必须早于结束时间')
    return service.strip(), start, end


def validate_top_k(top_k):
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError('top_k 必须为正整数')


def _filters(service, start, end):
    return (Incident.service == service, Incident.occurred_at >= start,
            Incident.occurred_at < end)


def query_incidents(factory, service: str, start_time: str, end_time: str) -> list[dict]:
    """当前小数据量入口；时间升序，相同时间按 ID 排序。"""
    service, start, end = validate_range(service, start_time, end_time)
    statement = (select(Incident).where(*_filters(service, start, end))
                 .order_by(Incident.occurred_at, Incident.incident_id.collate('C')))
    with session_scope(factory) as session:
        return [IncidentInput.model_validate(
            {field: getattr(row, field) for field in IncidentInput.model_fields}
        ).model_dump() for row in session.scalars(statement)]


def summarize_incidents(factory, service: str, start_time: str, end_time: str,
                        top_k: int = 3) -> dict:
    service, start, end = validate_range(service, start_time, end_time)
    validate_top_k(top_k)
    count = func.count()
    # 窗口求和发生在 LIMIT 之前：总数覆盖所有过滤后的分类，且与 Top K 使用同一快照。
    statement = (select(Incident.error_type, count.label('count'),
                        func.sum(count).over().label('total'))
                 .where(*_filters(service, start, end))
                 .group_by(Incident.error_type)
                 .order_by(count.desc(), Incident.error_type.collate('C').asc())
                 .limit(top_k))
    with session_scope(factory) as session:
        rows = session.execute(statement).all()
    total = int(rows[0].total) if rows else 0
    return {
        'service': service,
        'start_inclusive': start.isoformat(),
        'end_exclusive': end.isoformat(),
        'total_incidents': total,
        'top_k': top_k,
        'top_errors': [
            {'error_type': row.error_type, 'count': row.count,
             'percentage': round(row.count / total * 100, 2)} for row in rows
        ],
    }
