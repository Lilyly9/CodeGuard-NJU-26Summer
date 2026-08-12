"""TDD Step 1: LLM 输出解析器 — parse_llm_output(raw) 返回 ParseResult dataclass。"""

import json

import pytest

from src.parser import parse_llm_output
from src.models import ParseResult


class TestValidParsing:
    def test_parse_read_file(self):
        raw = json.dumps({"action": "read_file", "path": "src/main.py"})
        result = parse_llm_output(raw)
        assert isinstance(result, ParseResult)
        assert result.error is None
        assert result.action.type == "read_file"
        assert result.action.params["path"] == "src/main.py"

    def test_parse_write_file(self):
        raw = json.dumps(
            {"action": "write_file", "path": "src/main.py", "content": "x=1"}
        )
        result = parse_llm_output(raw)
        assert isinstance(result, ParseResult)
        assert result.error is None
        assert result.action.type == "write_file"
        assert result.action.params["path"] == "src/main.py"
        assert result.action.params["content"] == "x=1"

    def test_parse_run_pytest(self):
        raw = json.dumps({"action": "run_pytest", "args": "tests/ -v"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "run_pytest"
        assert result.action.params["args"] == "tests/ -v"

    def test_parse_run_command(self):
        raw = json.dumps({"action": "run_command", "command": "pytest"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "run_command"
        assert result.action.params["command"] == "pytest"

    def test_parse_list_files(self):
        raw = json.dumps({"action": "list_files", "path": "src/"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "list_files"
        assert result.action.params["path"] == "src/"

    def test_parse_finish(self):
        raw = json.dumps({"action": "finish", "summary": "done"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "finish"
        assert result.action.params["summary"] == "done"

    def test_parse_all_action_types(self):
        actions = {
            "read_file": {"path": "x.py"},
            "write_file": {"path": "x.py", "content": "x"},
            "run_pytest": {},
            "run_command": {"command": "pytest"},
            "list_files": {},
            "finish": {},
        }
        for action, extra in actions.items():
            data = {"action": action, **extra}
            raw = json.dumps(data)
            result = parse_llm_output(raw)
            assert result.error is None
            assert result.action.type == action


class TestInvalidJson:
    def test_plain_text_returns_error(self):
        result = parse_llm_output("hello world")
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_trailing_comma(self):
        raw = '{"action": "read_file", "path": "x.py",}'
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_unclosed_brace(self):
        raw = '{"action": "read_file"'
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_empty_string(self):
        result = parse_llm_output("")
        assert result.error is not None
        assert "Invalid JSON" in result.error


class TestMissingActionField:
    def test_no_action_key(self):
        raw = json.dumps({"path": "x.py"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing 'action'" in result.error

    def test_action_is_null(self):
        raw = json.dumps({"action": None})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing 'action'" in result.error

    def test_action_is_empty(self):
        raw = json.dumps({"action": ""})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing 'action'" in result.error


class TestUnknownAction:
    def test_delete_file_unknown(self):
        raw = json.dumps({"action": "delete_file", "path": "x.py"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Unknown action" in result.error
        assert "delete_file" in result.error

    def test_random_action(self):
        raw = json.dumps({"action": "rm -rf /"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Unknown action" in result.error

    def test_typo_in_action(self):
        raw = json.dumps({"action": "readfile"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Unknown action" in result.error


class TestMissingRequiredParams:
    def test_read_file_missing_path(self):
        raw = json.dumps({"action": "read_file"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing required param" in result.error
        assert "path" in result.error

    def test_write_file_missing_path(self):
        raw = json.dumps({"action": "write_file", "content": "x"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing required param" in result.error
        assert "path" in result.error

    def test_write_file_missing_content(self):
        raw = json.dumps({"action": "write_file", "path": "x.py"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing required param" in result.error
        assert "content" in result.error

    def test_run_command_missing_command(self):
        raw = json.dumps({"action": "run_command"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Missing required param" in result.error
        assert "command" in result.error

    def test_finish_no_required_params(self):
        raw = json.dumps({"action": "finish"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "finish"

    def test_list_files_no_required_params(self):
        raw = json.dumps({"action": "list_files"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "list_files"

    def test_run_pytest_no_required_params(self):
        raw = json.dumps({"action": "run_pytest"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "run_pytest"


class TestEdgeCases:
    def test_extra_fields_preserved(self):
        raw = json.dumps(
            {"action": "read_file", "path": "x.py", "reason": "debug", "line": 42}
        )
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.params["path"] == "x.py"
        assert result.action.params["reason"] == "debug"
        assert result.action.params["line"] == 42

    def test_params_is_list(self):
        raw = json.dumps({"action": "read_file", "path": ["x.py", "y.py"]})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.params["path"] == ["x.py", "y.py"]

    def test_llm_output_with_markdown_wrapper(self):
        raw = '```json\n{"action": "read_file", "path": "x.py"}\n```'
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Invalid JSON" in result.error

    def test_never_raises_exception(self):
        weird_inputs = [
            None,
            123,
            True,
            ["a", "b"],
            {"action": "read_file"},
            b"binary",
            "\x00\x01\x02",
        ]
        for inp in weird_inputs:
            result = parse_llm_output(inp)
            assert result.error is not None


class TestBoundaryExploits:
    def test_action_delete_database(self):
        raw = json.dumps({"action": "delete_database", "path": "/"})
        result = parse_llm_output(raw)
        assert result.error is not None
        assert "Unknown action" in result.error

    def test_path_param_not_string(self):
        raw = json.dumps({"action": "read_file", "path": 123})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.params["path"] == 123

    def test_content_param_not_string(self):
        raw = json.dumps({"action": "write_file", "path": "x.py", "content": 999})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.params["content"] == 999

    def test_extra_unknown_fields_ignored(self):
        raw = json.dumps({"action": "finish", "hack": "malicious", "summary": "done"})
        result = parse_llm_output(raw)
        assert result.error is None
        assert result.action.type == "finish"
        assert "hack" in result.action.params