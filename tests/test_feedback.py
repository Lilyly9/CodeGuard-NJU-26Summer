"""feedback 模块单元测试 — 覆盖成功/失败/有数据/有 diff 等场景。"""

from src.feedback import build_feedback


class TestBuildFeedback:
    def test_success_with_data(self):
        result = {"success": True, "data": "hello world", "error": None, "meta": {}}
        feedback = build_feedback(result)
        assert "successfully" in feedback.lower()
        assert "hello world" in feedback

    def test_success_with_diff(self):
        result = {"success": True, "data": None, "error": None, "meta": {"diff": "+def add(a,b): return a+b"}}
        feedback = build_feedback(result)
        assert "successfully" in feedback.lower()
        assert "diff" in feedback.lower()
        assert "+def add" in feedback

    def test_success_no_data_no_diff(self):
        result = {"success": True, "data": None, "error": None, "meta": {}}
        feedback = build_feedback(result)
        assert "successfully" in feedback.lower()

    def test_failure(self):
        result = {"success": False, "data": None, "error": "File not found", "meta": {}}
        feedback = build_feedback(result)
        assert "failed" in feedback.lower()
        assert "File not found" in feedback

    def test_failure_no_error_field(self):
        result = {"success": False, "data": None, "meta": {}}
        feedback = build_feedback(result)
        assert "failed" in feedback.lower()
        assert "Unknown error" in feedback