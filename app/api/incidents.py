"""只读统计接口；同步 SQL 在 FastAPI 工作线程中执行。"""
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import InterfaceError, OperationalError

from app.db.repository import summarize_incidents
from app.db.session import create_db_engine, create_session_factory
from app.schemas.summary import SummaryQuery, SummaryResponse

router = APIRouter(prefix="/incidents", tags=["incidents"])


class DatabaseResource:
    """每个应用一个延迟初始化的连接池，不在启动时要求数据库配置。"""

    def __init__(self, settings):
        self.settings = settings
        self.lock = Lock()
        self.engine = None
        self.factory = None

    def get_factory(self):
        with self.lock:
            if self.factory is None:
                engine = create_db_engine(self.settings)
                self.engine = engine
                self.factory = create_session_factory(engine)
            return self.factory

    def close(self):
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None
            self.factory = None


def summary_query(
    service: str,
    start_time: str,
    end_time: str,
    top_k: Annotated[str, Query(description="正整数，默认 3")] = "3",
) -> SummaryQuery:
    # HTTP 参数是文本：允许整数文本，但拒绝小数及布尔值。
    try:
        if not top_k.isascii() or not top_k.isdecimal():
            raise ValueError("top_k 必须为正整数")
        return SummaryQuery(service=service, start_time=start_time,
                            end_time=end_time, top_k=int(top_k))
    except ValidationError as exc:
        errors = [{"loc": ["query", *error["loc"]],
                   "msg": error["msg"], "type": error["type"]}
                  for error in exc.errors()]
        raise HTTPException(422, errors) from None
    except ValueError:
        raise HTTPException(422, "top_k 必须为正整数") from None


def get_session_factory(request: Request,
                        query: Annotated[SummaryQuery, Depends(summary_query)]):
    # 先完成全部参数校验，缺少必填项也不能触发数据库初始化。
    try:
        return request.app.state.database.get_factory()
    except ValueError:
        raise HTTPException(503, "数据库服务暂不可用") from None


@router.get("/summary", response_model=SummaryResponse,
            responses={503: {"description": "数据库服务暂不可用"}})
def summary(query: Annotated[SummaryQuery, Depends(summary_query)],
            factory=Depends(get_session_factory)) -> SummaryResponse:
    try:
        result = summarize_incidents(factory, **query.model_dump())
    except (OperationalError, InterfaceError):
        raise HTTPException(503, "数据库服务暂不可用") from None
    return SummaryResponse(**result)
