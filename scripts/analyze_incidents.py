#!/usr/bin/env python3
"""按服务和带时区的时间区间 [start, end) 统计 JSONL 故障。"""

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import sys


DEFAULT_INPUT = Path(__file__).resolve().parents[1] / "data/incidents/sample_incidents.jsonl"


def parse_time(value: str) -> datetime:
    """禁止无时区时间，避免依赖服务器本地时区。"""
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError("时间必须为 ISO 8601 格式，例如 2026-10-01T00:00:00+08:00") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区，例如 +08:00")
    return parsed


def load_incidents(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                raise ValueError(f"第 {line_number} 行不是合法 JSON") from None
            if not isinstance(record, dict):
                raise ValueError(f"第 {line_number} 行必须是 JSON 对象")
            records.append(record)
    return records


def analyze_incidents(
    records: list[dict], service: str, start_time: str, end_time: str, top_k: int = 3
) -> dict:
    if not isinstance(service, str) or not service.strip():
        raise ValueError("服务名称不能为空")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k <= 0:
        raise ValueError("top_k 必须为正整数")
    start, end = parse_time(start_time), parse_time(end_time)
    if start >= end:
        raise ValueError("开始时间必须早于结束时间")
    counts = Counter()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"第 {index} 条记录必须是对象")
        for field in ("service", "occurred_at", "error_type"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"第 {index} 条记录的 {field} 必须是非空字符串")
        try:
            occurred = parse_time(record["occurred_at"])
        except ValueError as exc:
            raise ValueError(f"第 {index} 条记录的 occurred_at 无效：{exc}") from None
        if record["service"] == service and start <= occurred < end:
            counts[record["error_type"]] += 1
    total = sum(counts.values())
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    return {
        "service": service,
        "start_inclusive": start.isoformat(),
        "end_exclusive": end.isoformat(),
        "total_incidents": total,
        "top_k": top_k,
        "top_errors": [
            {"error_type": name, "count": count, "percentage": round(count / total * 100, 2)}
            for name, count in ranked
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="JSONL 数据文件")
    parser.add_argument("--service", required=True, help="服务名称，精确匹配")
    parser.add_argument("--start", required=True, help="开始时间（包含，必须带时区）")
    parser.add_argument("--end", required=True, help="结束时间（不包含，必须带时区）")
    parser.add_argument("--top-k", type=int, default=3, help="返回类别数量，默认 3")
    args = parser.parse_args()
    try:
        result = analyze_incidents(load_incidents(args.input), args.service, args.start, args.end, args.top_k)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"统计失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
