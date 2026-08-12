"""端到端集成测试 — 复用 demo.py 的三个演示函数，验证三机制。"""

import io
import sys

import pytest

from demo import demo_1_block, demo_2_approval, demo_3_feedback


def _capture_output(func, *args, **kwargs):
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        func(*args, **kwargs)
        output = sys.stdout.getvalue()
        return output
    finally:
        sys.stdout = old_stdout


class TestDemoBlock:
    def test_demo_block(self):
        output = _capture_output(demo_1_block)
        assert "测试通过" in output


class TestDemoApproval:
    def test_demo_approval_rejected(self):
        output = _capture_output(demo_2_approval)
        assert "测试通过" in output


class TestDemoFeedback:
    def test_demo_feedback_loop(self):
        output = _capture_output(demo_3_feedback)
        assert "测试通过" in output