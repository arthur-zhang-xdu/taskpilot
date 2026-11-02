"""导入已迁移的 PostgreSQL；相同内容跳过，冲突整批失败。"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.db.import_incidents import IncidentImportError, import_batch, load_batch
from app.db.session import create_db_engine, create_session_factory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='UTF-8 JSONL 文件路径')
    args = parser.parse_args(argv)
    engine = None
    try:
        # 先校验文件，再读取数据库配置、创建连接资源。
        batch = load_batch(args.input)
        engine = create_db_engine()
        result = import_batch(batch, create_session_factory(engine))
    except IncidentImportError as exc:
        print(f'导入失败：{exc}；本次未提交新增记录', file=sys.stderr)
        return 1
    except (OSError, UnicodeError):
        print('导入失败：无法读取 UTF-8 输入文件；本次未提交新增记录', file=sys.stderr)
        return 1
    except ValidationError:
        print('导入失败：数据库配置校验失败；本次未提交新增记录', file=sys.stderr)
        return 1
    except ValueError:
        print('导入失败：数据库配置无效；本次未提交新增记录', file=sys.stderr)
        return 1
    except IntegrityError:
        print('导入失败：数据库约束冲突（可能存在并发写入）；本批事务已回滚', file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print('导入失败：数据库操作失败，请检查连接和迁移状态；未返回成功结果', file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(asdict(result), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
