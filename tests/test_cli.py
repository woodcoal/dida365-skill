"""Tests for Dida365 CLI."""

import os
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

    def test_filter_hidden_projects(self):
        """测试隐藏清单过滤功能"""
        # 测试数据：包含隐藏和正常的清单
        projects = [
            {"id": "1", "name": "工作项目"},
            {"id": "2", "name": "~私人清单"},
            {"id": "3", "name": "日常任务"},
            {"id": "4", "name": "~敏感项目"},
            {"id": "5", "name": "学习计划"},
        ]
        
        # 保存原始值
        original_prefix = os.environ.get("DIDA_LIST_HIDDEN_PREFIX")
        
        try:
            # 设置隐藏前缀为 "~"
            os.environ["DIDA_LIST_HIDDEN_PREFIX"] = "~"
            from cli import HIDDEN_PREFIX, DidaCLI
            cli = DidaCLI()
            
            # 测试过滤功能
            filtered = cli._filter_hidden_projects(projects, include_hidden=False)
            self.assertEqual(len(filtered), 3)  # 应该过滤掉 2 个
            filtered_names = [p["name"] for p in filtered]
            self.assertNotIn("~私人清单", filtered_names)
            self.assertNotIn("~敏感项目", filtered_names)
            self.assertIn("工作项目", filtered_names)
            self.assertIn("日常任务", filtered_names)
            
            # 测试包含隐藏项目
            all_projects = cli._filter_hidden_projects(projects, include_hidden=True)
            self.assertEqual(len(all_projects), 5)  # 应该包含所有项目
            
        finally:
            # 恢复原始值
            if original_prefix is None:
                os.environ.pop("DIDA_LIST_HIDDEN_PREFIX", None)
            else:
                os.environ["DIDA_LIST_HIDDEN_PREFIX"] = original_prefix


if __name__ == "__main__":
    unittest.main()
