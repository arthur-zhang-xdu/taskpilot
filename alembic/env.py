"""凭据从 Settings 读取，不写入 Alembic 配置或日志。"""
from alembic import context
from app.core.config import Settings
from app.db.base import Base
from app.db import models  # 注册 metadata
from app.db.session import create_db_engine, database_url

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(url=database_url(Settings()), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    # 测试可注入隔离数据库连接；普通 CLI 使用显式配置。
    connection = context.config.attributes.get("connection")
    def migrate(connection):
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    if connection is not None:
        migrate(connection)
    else:
        engine = create_db_engine()
        try:
            with engine.connect() as connection:
                migrate(connection)
        finally:
            engine.dispose()
