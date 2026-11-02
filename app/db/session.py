"""显式创建资源；导入模块不连接数据库。"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import sessionmaker
from app.core.config import Settings


def database_url(settings: Settings) -> URL:
    raw = settings.database_url.get_secret_value()
    if raw:
        try:
            url = make_url(raw)
        except Exception:
            raise ValueError("DATABASE_URL 格式无效") from None
        if url.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL 必须使用 postgresql+psycopg 驱动")
        return url
    if not (settings.postgres_user and settings.postgres_db and settings.postgres_password.get_secret_value()):
        raise ValueError("请配置 DATABASE_URL 或 POSTGRES_USER/POSTGRES_DB/POSTGRES_PASSWORD")
    return URL.create("postgresql+psycopg", username=settings.postgres_user,
                      password=settings.postgres_password.get_secret_value(),
                      host=settings.postgres_host, port=settings.postgres_port,
                      database=settings.postgres_db)


def create_db_engine(settings: Settings | None = None) -> Engine:
    return create_engine(database_url(settings or Settings()), pool_pre_ping=True,
                         hide_parameters=True,
                         connect_args={"options": "-c timezone=UTC", "connect_timeout": 5})


def create_session_factory(engine: Engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory):
    """一个操作一个 Session：成功提交、异常回滚，最后关闭。"""
    with factory.begin() as session:
        yield session
