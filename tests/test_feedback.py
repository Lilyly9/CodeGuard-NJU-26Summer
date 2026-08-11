"""反馈处理器单元测试。"""

import pytest

from src.feedback import analyze
from src.models import ToolResult


class TestAnalyze:
    def test_success_returns_成功(self):
        result = ToolResult(success=True, data="hello")
        assert analyze(result) == "成功"

    def test_failure_returns_失败(self):
        result = ToolResult(success=False, error="File not found")
        assert analyze(result) == "失败"