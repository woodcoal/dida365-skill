"""Tests for Dida365 CLI."""

import unittest
from datetime import datetime
from cli import DidaCLI, normalize_date


class TestDidaCLI(unittest.TestCase):
    def setUp(self):
        self.cli = DidaCLI()

    def test_normalize_date(self):
        # 验证日期标准化
        date_str = "2023-10-27"
        normalized = normalize_date(date_str)
        self.assertIn("2023-10-27T00:00:00", normalized)
        
        # 已带 T 的不处理
        already_normalized = "2023-10-27T12:00:00+0800"
        self.assertEqual(normalize_date(already_normalized), already_normalized)

    def test_parse_api_datetime(self):
        # 验证 API 时间解析
        # 毫秒时间戳
        ts = 1698336000000 
        dt = self.cli._parse_api_datetime(ts)
        self.assertIsInstance(dt, datetime)
        
        # ISO 格式
        iso_str = "2023-10-27T10:00:00+0000"
        dt_iso = self.cli._parse_api_datetime(iso_str)
        self.assertEqual(dt_iso.year, 2023)
        self.assertEqual(dt_iso.month, 10)
        self.assertEqual(dt_iso.day, 27)

    def test_priority_labels(self):
        from cli import PRIORITY_LABELS
        self.assertEqual(PRIORITY_LABELS[1], "低")
        self.assertEqual(PRIORITY_LABELS[5], "高")


if __name__ == "__main__":
    unittest.main()
