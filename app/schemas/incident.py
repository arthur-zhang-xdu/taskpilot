"""JSONL 输入契约；归一化结果可用于后续判重。"""
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictBool, field_validator

class IncidentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    incident_id: str
    is_synthetic: StrictBool
    service: str
    occurred_at: datetime
    error_type: str
    severity: Literal["P1", "P2", "P3"]
    message: str
    resolution: str | None = None

    @field_validator("incident_id", "service", "error_type", "severity", "message", "resolution", mode="before")
    @classmethod
    def normalize_text(cls, value, info):
        if value is None and info.field_name == "resolution":
            return None
        if not isinstance(value, str):
            raise ValueError("必须为字符串")
        value = value.strip()
        if info.field_name == "resolution":
            return value or None
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("is_synthetic")
    @classmethod
    def require_synthetic(cls, value):
        if not value:
            raise ValueError("当前导入入口仅接受合成数据")
        return value

    @field_validator("occurred_at", mode="before")
    @classmethod
    def parse_timestamp(cls, value):
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                raise ValueError("必须为带时区的 ISO 8601 时间") from None
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("必须为带时区的 ISO 8601 时间")
        return value.astimezone(timezone.utc)
