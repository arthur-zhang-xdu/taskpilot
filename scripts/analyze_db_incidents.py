"""按服务及 [start, end) 统计 PostgreSQL 故障，不调用模型。"""
import argparse
import json
import sys
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from app.db.repository import summarize_incidents, validate_range, validate_top_k
from app.db.session import create_db_engine, create_session_factory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service', required=True)
    parser.add_argument('--start', required=True, help='带时区起点，包含')
    parser.add_argument('--end', required=True, help='带时区终点，排除')
    parser.add_argument('--top-k', type=int, default=3)
    args = parser.parse_args(argv)
    engine = None
    try:
        # 参数不合法时不创建数据库连接资源。
        validate_range(args.service, args.start, args.end)
        validate_top_k(args.top_k)
        engine = create_db_engine()
        result = summarize_incidents(create_session_factory(engine), args.service,
                                     args.start, args.end, args.top_k)
    except ValidationError:
        print('统计失败：数据库配置校验失败', file=sys.stderr)
        return 1
    except ValueError:
        print('统计失败：请检查服务名、带时区的起止时间、正整数 top-k 及数据库配置', file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print('统计失败：数据库操作失败，请检查连接和迁移状态', file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
