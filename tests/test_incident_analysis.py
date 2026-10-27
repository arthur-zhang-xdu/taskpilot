"""独立手写数据及预期结果；不使用数据生成器构造基准答案。"""

import unittest

from scripts.analyze_incidents import analyze_incidents


# 手算：[10 月 1 日, 10 月 2 日) 内 payment 共 5 条：a=2, b=2, c=1。
# 第 1 条在起点前，第 7 条恰好在终点，第 8 条属于其他服务。
SAMPLE = [
    {"service": "payment", "occurred_at": "2026-09-30T23:59:59+08:00", "error_type": "a"},
    {"service": "payment", "occurred_at": "2026-10-01T00:00:00+08:00", "error_type": "b"},
    {"service": "payment", "occurred_at": "2026-10-01T01:00:00+08:00", "error_type": "a"},
    {"service": "payment", "occurred_at": "2026-10-01T02:00:00+08:00", "error_type": "c"},
    {"service": "payment", "occurred_at": "2026-10-01T03:00:00+08:00", "error_type": "b"},
    {"service": "payment", "occurred_at": "2026-10-01T23:59:59+08:00", "error_type": "a"},
    {"service": "payment", "occurred_at": "2026-10-02T00:00:00+08:00", "error_type": "c"},
    {"service": "order", "occurred_at": "2026-10-01T04:00:00+08:00", "error_type": "c"},
]
START = "2026-10-01T00:00:00+08:00"
END = "2026-10-02T00:00:00+08:00"


class AnalysisTests(unittest.TestCase):
    def test_boundaries_service_ties_and_percentages(self):
        result = analyze_incidents(SAMPLE, "payment", START, END)
        self.assertEqual(result["total_incidents"], 5)
        self.assertEqual(result["top_errors"], [
            {"error_type": "a", "count": 2, "percentage": 40.0},
            {"error_type": "b", "count": 2, "percentage": 40.0},
            {"error_type": "c", "count": 1, "percentage": 20.0},
        ])

    def test_top_k_keeps_full_denominator(self):
        result = analyze_incidents(SAMPLE, "payment", START, END, 1)
        self.assertEqual(result["total_incidents"], 5)
        self.assertEqual(result["top_errors"], [{"error_type": "a", "count": 2, "percentage": 40.0}])
        self.assertEqual(len(analyze_incidents(SAMPLE, "payment", START, END, 10)["top_errors"]), 3)

    def test_empty(self):
        for records, service in (([], "payment"), (SAMPLE, "missing")):
            result = analyze_incidents(records, service, START, END)
            self.assertEqual(result["total_incidents"], 0)
            self.assertEqual(result["top_errors"], [])

    def test_equivalent_utc_range(self):
        result = analyze_incidents(SAMPLE, "payment", "2026-09-30T16:00:00+00:00", "2026-10-01T16:00:00+00:00")
        self.assertEqual(result["total_incidents"], 5)

    def test_invalid_inputs(self):
        for start, end, k in ((START, START, 3), (END, START, 3), ("bad", END, 3),
                              ("2026-10-01T00:00:00", END, 3), (START, END, 0)):
            with self.subTest(start=start, end=end, k=k), self.assertRaises(ValueError):
                analyze_incidents(SAMPLE, "payment", start, end, k)
        with self.assertRaises(ValueError):
            analyze_incidents([{"service": "payment"}], "payment", START, END)


if __name__ == "__main__":
    unittest.main()
