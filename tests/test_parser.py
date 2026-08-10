"""TDD Step 1 (RED): LLM 输出解析器 — 失败测试。

parse_llm_output(raw) -> 对合法 JSON 返回解析后的 dict；
对非法 JSON / 缺失字段 / 不支持动作返回 {"error": ..., "raw": ...}。
"""

import json

import pytest

from src.parser import parse_llm_output


class TestValidParsing:
    def test_parse_read_file(self):
        raw = json.dumps({"action": "read_file", "path": "src/main.py"})
        result = parse_llm_output(raw)
        assert result["action"] == "read_file"
        assert result["path"] == "src/main.py"

    def test_parse_write_file(self):
        raw = json.dumps(
            {"action": "write_file", "path": "src/main.py", "content": "x=1"}
        )
        result = parse_llm_output(raw)
        assert result["action"] == "write_file"
        assert result["path"] == "src/main.py"
        assert result["content"] == "x=1"

    def test_parse_run_tests(self):
        raw = json.dumps({"action": "run_tests", "args": "tests/ -v"})
        result = parse_llm_output(raw)
        assert result["action"] == "run_tests"
        assert result["args"] == "tests/ -v"

    def test_parse_run_command(self):
        raw = json.dumps({"action": "run_command", "command": "pytest"})
        result = parse_llm_output(raw)
        assert result["action"] == "run_command"
        assert result["command"] == "pytest"

    def test_parse_list_files(self):
        raw = json.dumps({"action": "list_files", "path": "src/"})
        result = parse_llm_output(raw)
        assert result["action"] == "list_files"
        assert result["path"] == "src/"

    def test_parse_finish(self):
        raw = json.dumps({"action": "finish", "summary": "done"})
        result = parse_llm_output(raw)
        assert result["action"] == "finish"
        assert result["summary"] == "done"

    def test_parse_all_action_types(self):
        actions = {
            "read_file": {"path": "x.py"},
            "write_file": {"path": "x.py", "content": "x"},
            "run_tests": {},
            "run_command": {"command": "pytest"},
            "list_files": {},
            "finish": {},
        }
        for action, extra in actions.items():
            data = {"action": action, **extra}
            raw = json.dumps(data)
            result = parse_llm_output(raw)
            assert result["action"] == action
            assert "error" not in result


class TestInvalidJson:
    def test_plain_text_returns_error(self):
        result = parse_llm_output("hello world")
        assert "error" in result
        assert "Invalid JSON" in result["error"]
        assert result["raw"] == "hello world"

    def test_trailing_comma(self):
        raw = '{"action": "read_file", "path": "x.py",}'
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_unclosed_brace(self):
        raw = '{"action": "read_file"'
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Invalid JSON" in result["error"]

    def test_empty_string(self):
        result = parse_llm_output("")
        assert "error" in result
        assert "Invalid JSON" in result["error"]
        assert result["raw"] == ""


class TestMissingActionField:
    def test_no_action_key(self):
        raw = json.dumps({"path": "x.py"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing 'action'" in result["error"]
        assert result["raw"] == raw

    def test_action_is_null(self):
        raw = json.dumps({"action": None})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing 'action'" in result["error"]

    def test_action_is_empty(self):
        raw = json.dumps({"action": ""})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing 'action'" in result["error"]


class TestUnknownAction:
    def test_delete_file_unknown(self):
        raw = json.dumps({"action": "delete_file", "path": "x.py"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Unknown action" in result["error"]
        assert "delete_file" in result["error"]

    def test_random_action(self):
        raw = json.dumps({"action": "rm -rf /"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Unknown action" in result["error"]

    def test_typo_in_action(self):
        raw = json.dumps({"action": "readfile"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Unknown action" in result["error"]


class TestMissingRequiredParams:
    def test_read_file_missing_path(self):
        raw = json.dumps({"action": "read_file"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing required param" in result["error"]
        assert "path" in result["error"]

    def test_write_file_missing_path(self):
        raw = json.dumps({"action": "write_file", "content": "x"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing required param" in result["error"]
        assert "path" in result["error"]

    def test_write_file_missing_content(self):
        raw = json.dumps({"action": "write_file", "path": "x.py"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing required param" in result["error"]
        assert "content" in result["error"]

    def test_run_command_missing_command(self):
        raw = json.dumps({"action": "run_command"})
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Missing required param" in result["error"]
        assert "command" in result["error"]

    def test_finish_no_required_params(self):
        raw = json.dumps({"action": "finish"})
        result = parse_llm_output(raw)
        assert result["action"] == "finish"
        assert "error" not in result

    def test_list_files_no_required_params(self):
        raw = json.dumps({"action": "list_files"})
        result = parse_llm_output(raw)
        assert result["action"] == "list_files"
        assert "error" not in result

    def test_run_tests_no_required_params(self):
        raw = json.dumps({"action": "run_tests"})
        result = parse_llm_output(raw)
        assert result["action"] == "run_tests"
        assert "error" not in result


class TestEdgeCases:
    def test_extra_fields_preserved(self):
        raw = json.dumps(
            {"action": "read_file", "path": "x.py", "reason": "debug", "line": 42}
        )
        result = parse_llm_output(raw)
        assert result["path"] == "x.py"
        assert result["reason"] == "debug"
        assert result["line"] == 42

    def test_params_is_list(self):
        raw = json.dumps({"action": "read_file", "path": ["x.py", "y.py"]})
        result = parse_llm_output(raw)
        assert result["path"] == ["x.py", "y.py"]

    def test_llm_output_with_markdown_wrapper(self):
        raw = '```json\n{"action": "read_file", "path": "x.py"}\n```'
        result = parse_llm_output(raw)
        assert "error" in result
        assert "Invalid JSON" in result["error"]
        assert raw in result["raw"]

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
            assert "error" in result
            assert "raw" in result