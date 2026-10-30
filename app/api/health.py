"""存活检查不访问模型或其他外部服务。"""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Literal

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str


@router.get("/health/live", response_model=HealthResponse, tags=["health"])
def live(request: Request) -> HealthResponse:
    return HealthResponse(service=request.app.state.settings.app_name)
