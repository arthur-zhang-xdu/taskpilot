"""HTTP 与后续工具共用的统计契约。"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.repository import validate_range, validate_top_k


class SummaryQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    service: str
    start_time: str
    end_time: str
    top_k: int = Field(default=3, strict=True, gt=0)

    @model_validator(mode="after")
    def normalize(self):
        service, start, end = validate_range(self.service, self.start_time, self.end_time)
        validate_top_k(self.top_k)
        self.service = service
        self.start_time = start.isoformat()
        self.end_time = end.isoformat()
        return self


class ErrorCategory(BaseModel):
    error_type: str = Field(min_length=1)
    count: int = Field(strict=True, gt=0)
    percentage: float = Field(ge=0, le=100)


class SummaryResponse(BaseModel):
    service: str
    start_inclusive: datetime
    end_exclusive: datetime
    total_incidents: int = Field(strict=True, ge=0)
    top_k: int = Field(strict=True, gt=0)
    top_errors: list[ErrorCategory]
    data_source: Literal["synthetic_incidents"] = "synthetic_incidents"
