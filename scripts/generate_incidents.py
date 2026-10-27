#!/usr/bin/env python3
"""生成固定时间范围内的 100 条合成故障，输出为 UTF-8 JSONL。"""

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "data" / "incidents" / "sample_incidents.jsonl"
)
START = datetime(2026, 10, 1, tzinfo=timezone(timedelta(hours=8)))
END = datetime(2026, 11, 1, tzinfo=timezone(timedelta(hours=8)))
SERVICE_COUNTS = {"payment-service": 50, "order-service": 30, "user-service": 20}
ERROR_COUNTS = {
    "connection_timeout": 35,
    "database_connection_error": 25,
    "upstream_http_5xx": 20,
    "rate_limit_exceeded": 12,
    "invalid_request": 8,
}
ERROR_DETAILS = {
    "connection_timeout": (
        "P2", "连接上游服务超时", "检查连接池、上游延迟和超时配置"
    ),
    "database_connection_error": (
        "P1", "无法建立数据库连接", "检查数据库可用性、连接数和网络连通性"
    ),
    "upstream_http_5xx": (
        "P2", "上游接口返回 HTTP 5xx", "核对上游日志、请求链路和服务状态"
    ),
    "rate_limit_exceeded": (
        "P2", "请求触发限流", "检查请求速率、限流阈值和重试退避策略"
    ),
    "invalid_request": (
        "P3", "请求参数不符合接口约定", "核对参数格式、必填字段和接口版本"
    ),
}


def generate_incidents(seed: int = 42) -> list[dict]:
    """固定全局类别数量；种子决定服务与类别配对和发生时间。"""
    rng = random.Random(seed)
    services = [name for name, count in SERVICE_COUNTS.items() for _ in range(count)]
    errors = [name for name, count in ERROR_COUNTS.items() for _ in range(count)]
    rng.shuffle(services)
    rng.shuffle(errors)
    seconds = int((END - START).total_seconds())
    records = []
    for index, (service, error_type) in enumerate(zip(services, errors), start=1):
        severity, message, suggestion = ERROR_DETAILS[error_type]
        records.append({
            "incident_id": f"inc_{index:04d}",
            "is_synthetic": True,
            "service": service,
            "occurred_at": (START + timedelta(seconds=rng.randrange(seconds))).isoformat(),
            "error_type": error_type,
            "severity": severity,
            "message": "模拟：" + message,
            "resolution": "模拟处理建议（未执行、未验证根因）：" + suggestion,
        })
    return sorted(records, key=lambda record: (record["occurred_at"], record["incident_id"]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="随机种子，默认 42")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="输出 JSONL 文件路径；已存在的文件会被覆盖")
    args = parser.parse_args()
    records = generate_incidents(args.seed)
    content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    encoded = content.encode("utf-8")
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(encoded)
    except OSError as exc:
        parser.exit(1, f"写入失败：{exc}\n")
    print(json.dumps({
        "output": str(args.output.resolve()),
        "count": len(records),
        "seed": args.seed,
        "is_synthetic": True,
        "start_inclusive": START.isoformat(),
        "end_exclusive": END.isoformat(),
        "service_counts": dict(sorted(Counter(r["service"] for r in records).items())),
        "error_counts": dict(sorted(Counter(r["error_type"] for r in records).items())),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
