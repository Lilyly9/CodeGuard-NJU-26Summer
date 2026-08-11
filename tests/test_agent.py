"""TDD Step 5: Agent 主循环测试 — 使用 MockLLM，绝对不调用真实网络。"""

import json

import pytest

from src.agent import run
from src.config import Config
from src.models import Action, ApprovalResult, ParseResult, RiskDecision, RiskLevel


def _make_risk(level):
    return RiskDecision(
        level=RiskLevel(level.upper()),
        rule="mock",
        needs_approval=level.upper() == "HIGH",
        is_forbidden=level.upper() == "FORBIDDEN",
    )


class MockLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0
        self.contexts = []

    def get_response(self, context):
        self.contexts.append(context)
        if self.call_count >= len(self.responses):
            return json.dumps({"action": "finish", "summary": "fallback"})
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


class MockApproval:
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    def request_approval(self, risk, get_input=None, timeout=60):
        if self.call_count >= len(self.responses):
            return ApprovalResult(approved=False, reason="exhausted")
        resp = self.responses[self.call_count]
        self.call_count += 1
        return ApprovalResult(approved=resp, reason="APPROVED" if resp else "REJECTED")


def mock_parse_success(raw):
    data = json.loads(raw)
    action_name = data.pop("action")
    return ParseResult(action=Action(type=action_name, params=data), error=None)


def mock_parse_error(raw):
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "action" in data:
            action_name = data.pop("action")
            return ParseResult(action=Action(type=action_name, params=data), error=None)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return ParseResult(action=None, error="Invalid JSON")


def mock_evaluate_low(action, workspace):
    return _make_risk("low")


def mock_evaluate_forbidden(action, workspace):
    return _make_risk("forbidden")


def mock_evaluate_high(action, workspace):
    return _make_risk("high")


def mock_evaluate_medium(action, workspace):
    return _make_risk("medium")


class MockTools:
    def __init__(self):
        self.calls = []

    def list_files(self, path, workspace):
        self.calls.append(("list_files", path))
        return {"success": True, "data": [{"name": "test.py", "type": "file"}], "error": None, "meta": {}}

    def read_file(self, path, workspace):
        self.calls.append(("read_file", path))
        return {"success": True, "data": "def add(a,b): return a-b", "error": None, "meta": {}}

    def write_file(self, path, content, workspace):
        self.calls.append(("write_file", path))
        return {"success": True, "data": None, "error": None, "meta": {"diff": "+def add(a,b): return a+b"}}

    def run_pytest(self, workspace, command="pytest", timeout=30):
        self.calls.append(("run_pytest", command))
        return {"success": True, "data": "1 passed", "error": None, "meta": {"exit_code": 0}}

    def run_command(self, command, workspace):
        self.calls.append(("run_command", command))
        return {"success": True, "data": "OK", "error": None, "meta": {"exit_code": 0}}


class TestAgentBasicFlow:
    def test_read_file_then_finish(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/main.py"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Fix the bug",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert result["steps"] == 2
        assert len(tools.calls) == 1
        assert tools.calls[0] == ("read_file", "src/main.py")

    def test_list_files_then_finish(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "list_files", "path": "src/"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Explore the project",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert len(tools.calls) == 1
        assert tools.calls[0][0] == "list_files"

    def test_write_file_then_run_pytest_then_finish(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "write_file", "path": "src/calc.py", "content": "def add(a,b): return a+b"}),
            json.dumps({"action": "run_pytest"}),
            json.dumps({"action": "finish", "summary": "tests pass"}),
        ])
        tools = MockTools()

        result = run(
            "Fix calculator",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_medium,
            approval_fn=MockApproval([]),
            tools_module=tools,
            config=Config(auto_finish_on_test_pass=False),
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert result["steps"] == 3
        assert len(tools.calls) == 2
        assert tools.calls[0][0] == "write_file"
        assert tools.calls[1][0] == "run_pytest"

    def test_run_command_then_finish(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "pytest"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Run tests",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert len(tools.calls) == 1
        assert tools.calls[0][0] == "run_command"


class TestForbiddenAction:
    def test_forbidden_action_is_blocked(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "rm -rf /"}),
            json.dumps({"action": "finish", "summary": "blocked"}),
        ])
        tools = MockTools()

        result = run(
            "Try dangerous command",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_forbidden,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert len(tools.calls) == 0

    def test_forbidden_feedback_in_context(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "rm -rf /"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Try dangerous",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_forbidden,
            approval_fn=MockApproval([]),
            tools_module=MockTools(),
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert len(llm.contexts) >= 2
        feedback_found = False
        for ctx in llm.contexts:
            for msg in ctx:
                if isinstance(msg, dict) and "forbidden" in str(msg.get("content", "")).lower():
                    feedback_found = True
        assert feedback_found

    def test_forbidden_does_not_call_approval(self, tmp_path):
        approval = MockApproval([True])

        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "shutdown"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Try shutdown",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_forbidden,
            approval_fn=approval,
            tools_module=MockTools(),
        )

        assert result["success"] is True
        assert approval.call_count == 0


class TestHighRiskApproval:
    def test_high_risk_approved(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "write_file", "path": "src/config.py", "content": "SECRET=123"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        approval = MockApproval([True])
        tools = MockTools()

        result = run(
            "Write config",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_high,
            approval_fn=approval,
            tools_module=tools,
        )

        assert result["success"] is True
        assert approval.call_count == 1
        assert len(tools.calls) == 1
        assert tools.calls[0][0] == "write_file"

    def test_high_risk_rejected(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "write_file", "path": "src/config.py", "content": "SECRET=123"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        approval = MockApproval([False])
        tools = MockTools()

        result = run(
            "Write config",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_high,
            approval_fn=approval,
            tools_module=tools,
        )

        assert result["success"] is True
        assert approval.call_count == 1
        assert len(tools.calls) == 0

    def test_high_risk_rejected_feedback(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "git commit -m x"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        approval = MockApproval([False])

        result = run(
            "Commit",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_high,
            approval_fn=approval,
            tools_module=MockTools(),
        )

        assert result["success"] is True
        rejected_found = False
        for ctx in llm.contexts:
            for msg in ctx:
                content = str(msg.get("content", "")).lower()
                if "reject" in content or "denied" in content:
                    rejected_found = True
        assert rejected_found


class TestMaxSteps:
    def test_max_steps_limit(self, tmp_path):
        actions = [
            json.dumps({"action": "read_file", "path": "a.py"}),
            json.dumps({"action": "list_files", "path": "b.py"}),
            json.dumps({"action": "read_file", "path": "c.py"}),
            json.dumps({"action": "list_files", "path": "d.py"}),
            json.dumps({"action": "read_file", "path": "e.py"}),
        ] * 5
        llm = MockLLM(actions)
        tools = MockTools()

        result = run(
            "Read many files",
            str(tmp_path),
            max_steps=3,
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["finish_reason"] == "max_steps"
        assert result["steps"] == 3
        assert len(tools.calls) == 3

    def test_max_steps_default(self, tmp_path):
        actions = [
            json.dumps({"action": "read_file", "path": f"{i}.py"}) if i % 2 == 0
            else json.dumps({"action": "list_files", "path": f"{i}.py"})
            for i in range(20)
        ]
        llm = MockLLM(actions)
        tools = MockTools()

        result = run(
            "Read files",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["finish_reason"] == "max_steps"
        assert result["steps"] == 10


class TestParseError:
    def test_parse_error_feedback_loop(self, tmp_path):
        llm = MockLLM([
            "not valid json",
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Fix bug",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_error,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert len(tools.calls) == 0
        assert len(llm.contexts) >= 2
        parse_error_found = False
        for ctx in llm.contexts:
            for msg in ctx:
                if "error" in str(msg.get("content", "")).lower():
                    parse_error_found = True
        assert parse_error_found


class TestFinishAction:
    def test_finish_breaks_immediately(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "finish", "summary": "all done"}),
        ])
        tools = MockTools()

        result = run(
            "Just finish",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert result["steps"] == 1
        assert len(tools.calls) == 0


class TestToolExecutionFeedback:
    def test_successful_tool_feedback_in_context(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/main.py"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Read file",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        feedback_found = False
        for ctx in llm.contexts:
            for msg in ctx:
                content = str(msg.get("content", ""))
                if "def add" in content:
                    feedback_found = True
        assert feedback_found

    def test_failed_tool_feedback_in_context(self, tmp_path):
        class FailingTools:
            def read_file(self, path, workspace):
                return {"success": False, "data": None, "error": "File not found", "meta": {}}

            def list_files(self, path, workspace):
                return {"success": True, "data": [], "error": None, "meta": {}}

            def write_file(self, path, content, workspace):
                return {"success": True, "data": None, "error": None, "meta": {}}

            def run_pytest(self, workspace, command="pytest", timeout=30):
                return {"success": True, "data": "", "error": None, "meta": {}}

            def run_command(self, command, workspace):
                return {"success": True, "data": "", "error": None, "meta": {}}

        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "nonexistent.py"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Read missing file",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=FailingTools(),
        )

        assert result["success"] is True
        error_found = False
        for ctx in llm.contexts:
            for msg in ctx:
                content = str(msg.get("content", ""))
                if "File not found" in content:
                    error_found = True
        assert error_found


class TestAuditLog:
    def test_audit_log_contains_all_steps(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/main.py"}),
            json.dumps({"action": "write_file", "path": "src/main.py", "content": "x=1"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        def evaluate_fn(action, workspace):
            if action.get("action") == "read_file":
                return _make_risk("low")
            return _make_risk("medium")

        result = run(
            "Fix bug",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=evaluate_fn,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert "audit_log" in result
        assert len(result["audit_log"]) == 3
        assert result["audit_log"][0]["action"]["action"] == "read_file"
        assert result["audit_log"][1]["action"]["action"] == "write_file"
        assert result["audit_log"][2]["action"]["action"] == "finish"

    def test_audit_log_records_forbidden(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "run_command", "command": "rm -rf /"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Dangerous",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_forbidden,
            approval_fn=MockApproval([]),
            tools_module=MockTools(),
        )

        assert result["audit_log"][0]["final_decision"] == "BLOCKED"

    def test_audit_log_records_rejected(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "write_file", "path": "x.py", "content": "x"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Write",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_high,
            approval_fn=MockApproval([False]),
            tools_module=MockTools(),
        )

        assert result["audit_log"][0]["final_decision"] == "REJECTED"

    def test_audit_log_records_executed(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "x.py"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])

        result = run(
            "Read",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=MockTools(),
        )

        assert result["audit_log"][0]["final_decision"] == "EXECUTED"


class TestIntegration:
    def test_full_workflow_modify_test_pass(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/calc.py"}),
            json.dumps({"action": "write_file", "path": "src/calc.py", "content": "def add(a,b): return a+b"}),
            json.dumps({"action": "run_pytest"}),
            json.dumps({"action": "finish", "summary": "All tests pass"}),
        ])
        tools = MockTools()

        def evaluate_fn(action, workspace):
            action_type = action.get("action", "")
            if action_type == "read_file":
                return _make_risk("low")
            if action_type == "write_file":
                return _make_risk("medium")
            if action_type == "run_pytest":
                return _make_risk("medium")
            return _make_risk("low")

        result = run(
            "Fix calculator.py: add function should return a+b",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=evaluate_fn,
            approval_fn=MockApproval([]),
            tools_module=tools,
            config=Config(auto_finish_on_test_pass=False),
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert result["steps"] == 4
        assert len(tools.calls) == 3
        assert tools.calls[0][0] == "read_file"
        assert tools.calls[1][0] == "write_file"
        assert tools.calls[2][0] == "run_pytest"

    def test_high_risk_workflow_approved(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/main.py"}),
            json.dumps({"action": "write_file", "path": "src/main.py", "content": "x=1"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()
        approval = MockApproval([True])

        def evaluate_fn(action, workspace):
            if action.get("action") == "write_file":
                return _make_risk("high")
            return _make_risk("low")

        result = run(
            "Update main.py",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=evaluate_fn,
            approval_fn=approval,
            tools_module=tools,
        )

        assert result["success"] is True
        assert approval.call_count == 1
        assert len(tools.calls) == 2


class TestAutoFinishOnTestPass:
    def test_auto_finish_on_test_pass(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/calc.py"}),
            json.dumps({"action": "write_file", "path": "src/calc.py", "content": "def add(a,b): return a+b"}),
            json.dumps({"action": "run_pytest"}),
            json.dumps({"action": "finish", "summary": "should not reach"}),
        ])
        tools = MockTools()

        def evaluate_fn(action, workspace):
            action_type = action.get("action", "")
            if action_type == "read_file":
                return _make_risk("low")
            if action_type == "write_file":
                return _make_risk("medium")
            if action_type == "run_pytest":
                return _make_risk("medium")
            return _make_risk("low")

        result = run(
            "Fix calculator.py",
            str(tmp_path),
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=evaluate_fn,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "all_tests_passed"
        assert result["steps"] == 3
        assert len(tools.calls) == 3
        assert tools.calls[2][0] == "run_pytest"

    def test_no_auto_finish_on_test_fail(self, tmp_path):
        class FailingTestTools:
            def __init__(self):
                self.calls = []

            def read_file(self, path, workspace):
                self.calls.append(("read_file", path))
                return {"success": True, "data": "code", "error": None, "meta": {}}

            def write_file(self, path, content, workspace):
                self.calls.append(("write_file", path))
                return {"success": True, "data": None, "error": None, "meta": {}}

            def run_pytest(self, workspace, command="pytest", timeout=30):
                self.calls.append(("run_pytest", command))
                return {"success": False, "data": "1 failed", "error": "test failed", "meta": {"exit_code": 1}}

            def run_command(self, command, workspace):
                self.calls.append(("run_command", command))
                return {"success": True, "data": "OK", "error": None, "meta": {}}

            def list_files(self, path, workspace):
                self.calls.append(("list_files", path))
                return {"success": True, "data": [], "error": None, "meta": {}}

        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "src/calc.py"}),
            json.dumps({"action": "write_file", "path": "src/calc.py", "content": "x"}),
            json.dumps({"action": "run_pytest"}),
            json.dumps({"action": "write_file", "path": "src/calc.py", "content": "y"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = FailingTestTools()

        def evaluate_fn(action, workspace):
            return _make_risk("low")

        result = run(
            "Fix bug",
            str(tmp_path),
            max_steps=10,
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=evaluate_fn,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["success"] is True
        assert result["finish_reason"] == "finish_action"
        assert result["steps"] >= 4
        assert any(c[0] == "run_pytest" for c in tools.calls)


class TestStopConditionParseFailure:
    def test_consecutive_3_parse_failures_stops(self, tmp_path):
        llm = MockLLM([
            "not json",
            "still not json",
            "also not json",
            json.dumps({"action": "finish", "summary": "should not reach"}),
        ])
        tools = MockTools()

        result = run(
            "Fix bug",
            str(tmp_path),
            max_steps=20,
            llm_client=llm,
            parse_fn=mock_parse_error,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["finish_reason"] == "parse_failure"
        assert "解析失败" in result.get("stop_reason", "")


class TestStopConditionRepeatedAction:
    def test_consecutive_3_same_actions_stops(self, tmp_path):
        llm = MockLLM([
            json.dumps({"action": "read_file", "path": "x.py"}),
            json.dumps({"action": "read_file", "path": "x.py"}),
            json.dumps({"action": "read_file", "path": "x.py"}),
            json.dumps({"action": "finish", "summary": "done"}),
        ])
        tools = MockTools()

        result = run(
            "Fix bug",
            str(tmp_path),
            max_steps=20,
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["finish_reason"] == "repeated_action"
        assert "相同无效动作" in result.get("stop_reason", "")


class TestStopConditionKeyboardInterrupt:
    def test_keyboard_interrupt_stops(self, tmp_path):
        class InterruptLLM:
            def __init__(self):
                self.call_count = 0
                self.contexts = []

            def get_response(self, context):
                self.contexts.append(context)
                self.call_count += 1
                if self.call_count == 1:
                    return json.dumps({"action": "read_file", "path": "x.py"})
                raise KeyboardInterrupt()

        llm = InterruptLLM()
        tools = MockTools()

        result = run(
            "Fix bug",
            str(tmp_path),
            max_steps=20,
            llm_client=llm,
            parse_fn=mock_parse_success,
            evaluate_fn=mock_evaluate_low,
            approval_fn=MockApproval([]),
            tools_module=tools,
        )

        assert result["finish_reason"] == "keyboard_interrupt"
        assert "用户手动中断" in result.get("stop_reason", "")