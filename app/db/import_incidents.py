"""小批量 JSONL 导入：先完整校验，再在单事务中比较和写入。"""
from dataclasses import dataclass
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select

from app.db.models import Incident
from app.db.session import session_scope
from app.schemas.incident import IncidentInput


class IncidentImportError(ValueError):
    """可以安全展示的输入或内容冲突摘要，不包含原始数据。"""


@dataclass(frozen=True)
class ImportResult:
    read: int
    inserted: int
    skipped: int


@dataclass(frozen=True)
class ValidatedRecord:
    line: int
    incident: IncidentInput


@dataclass(frozen=True)
class ValidatedBatch:
    read: int
    records: tuple[ValidatedRecord, ...]


def load_batch(path: Path) -> ValidatedBatch:
    """错误携带物理行号；空行不计入读取数，未知字段名也不回显。"""
    records = {}
    count = 0
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            count += 1
            try:
                raw = json.loads(line)
            except ValueError:
                raise IncidentImportError(f"第 {line_number} 行：不是合法 JSON") from None
            try:
                incident = IncidentInput.model_validate(raw)
            except ValidationError as exc:
                fields = sorted({
                    str(error['loc'][0]) if error['loc'] and error['loc'][0] in IncidentInput.model_fields
                    else '记录或未知字段'
                    for error in exc.errors(include_input=False, include_context=False)
                })
                raise IncidentImportError(
                    f"第 {line_number} 行：字段 {', '.join(fields)} 校验失败"
                ) from None
            previous = records.get(incident.incident_id)
            if previous is not None:
                if previous.incident != incident:
                    raise IncidentImportError(
                        f"第 {line_number} 行与第 {previous.line} 行：incident_id 相同但规范化内容冲突"
                    )
            else:
                records[incident.incident_id] = ValidatedRecord(line_number, incident)
    return ValidatedBatch(count, tuple(records.values()))


def import_batch(batch: ValidatedBatch, factory) -> ImportResult:
    """唯一约束竞争或任何写入异常均交给事务上下文回滚。"""
    inserted = 0
    with session_scope(factory) as session:
        ids = [record.incident.incident_id for record in batch.records]
        existing = {
            row.incident_id: row
            for row in session.scalars(select(Incident).where(Incident.incident_id.in_(ids)))
        } if ids else {}
        pending = []
        for record in batch.records:
            incident = record.incident
            old = existing.get(incident.incident_id)
            if old is not None:
                old_values = {field: getattr(old, field) for field in IncidentInput.model_fields}
                if old_values != incident.model_dump():
                    raise IncidentImportError(
                        f"第 {record.line} 行：incident_id 已存在，但规范化内容与数据库冲突"
                    )
            else:
                pending.append(Incident(**incident.model_dump()))
        session.add_all(pending)
        inserted = len(pending)
    # 必须等事务提交成功才返回成功统计。
    return ImportResult(batch.read, inserted, batch.read - inserted)


def import_file(path: Path, factory) -> ImportResult:
    return import_batch(load_batch(path), factory)
