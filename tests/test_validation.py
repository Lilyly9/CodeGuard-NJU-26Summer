"""Validation 层单元测试 — 覆盖合法动作、缺失字段、路径穿越、敏感文件、类型错误、未知字段警告。"""

import pytest

from src.validation import validate_action
from src.models import ValidationResult


class FakeConfig:
    def __init__(self):
        self.workspace = "."
        self.max_steps = 10
        self.command_timeout = 30
        self.max_file_size = 100000
        self.allowed_commands = ["pytest", "python", "ruff", "git diff", "git status"]
        self.protected_files = [".env", "*.pem", "*.key", ".git"]


class TestValidActions:
    def test_read_file_is_valid(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "main.py").write_text("x")

        result = validate_action(
            {"action": "read_file", "path": str(ws / "main.py")},
            str(ws),
            FakeConfig(),
        )
        assert isinstance(result, ValidationResult)
        assert result.valid is True
        assert result.errors == []

    def test_write_file_is_valid(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "write_file", "path": str(ws / "new.py"), "content": "x=1"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is True

    def test_list_files_is_valid(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "list_files", "path": str(ws)},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is True

    def test_run_pytest_is_valid(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "run_pytest"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is True

    def test_run_command_is_valid(self):
        result = validate_action(
            {"action": "run_command", "command": "pytest"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is True

    def test_finish_is_valid(self):
        result = validate_action(
            {"action": "finish", "summary": "done"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is True

    def test_edit_file_is_valid(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "main.py").write_text("line1\nline2\nline3\n")

        result = validate_action(
            {
                "action": "edit_file",
                "path": str(ws / "main.py"),
                "start_line": 2,
                "end_line": 2,
                "new_content": "replaced",
            },
            str(ws),
            FakeConfig(),
        )
        assert result.valid is True


class TestMissingAction:
    def test_missing_action_rejected(self):
        result = validate_action(
            {"path": "x.py"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "action" in result.reason.lower()

    def test_empty_action_rejected(self):
        result = validate_action(
            {"action": ""},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "action" in result.reason.lower()

    def test_unknown_action_rejected(self):
        result = validate_action(
            {"action": "delete_file"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "unknown" in result.reason.lower()

    def test_non_dict_parsed_rejected(self):
        result = validate_action(
            "not a dict",
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False


class TestMissingRequiredParams:
    def test_read_file_missing_path(self):
        result = validate_action(
            {"action": "read_file"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "path" in result.reason.lower()

    def test_write_file_missing_content(self):
        result = validate_action(
            {"action": "write_file", "path": "x.py"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "content" in result.reason.lower()

    def test_run_command_missing_command(self):
        result = validate_action(
            {"action": "run_command"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "command" in result.reason.lower()

    def test_edit_file_missing_params(self):
        result = validate_action(
            {"action": "edit_file", "path": "x.py"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert "start_line" in result.reason.lower()


class TestPathTraversal:
    def test_dot_dot_in_path_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": "../secret.env"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "traversal" in result.reason.lower()

    def test_dot_dot_in_middle_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": "src/../../etc/passwd"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "traversal" in result.reason.lower()


class TestSensitiveFiles:
    def test_dot_env_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": ".env"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "sensitive" in result.reason.lower() or ".env" in result.reason.lower()

    def test_pem_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": "key.pem"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "sensitive" in result.reason.lower() or ".pem" in result.reason.lower()

    def test_key_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": "private.key"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "sensitive" in result.reason.lower() or ".key" in result.reason.lower()


class TestUnknownFields:
    def test_unknown_field_produces_warning(self):
        result = validate_action(
            {"action": "read_file", "path": "x.py", "extra_field": "value"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is True
        assert len(result.warnings) >= 1
        assert any("extra_field" in w for w in result.warnings)

    def test_multiple_unknown_fields(self):
        result = validate_action(
            {
                "action": "read_file",
                "path": "x.py",
                "foo": "bar",
                "baz": "qux",
            },
            "/ws",
            FakeConfig(),
        )
        assert result.valid is True
        assert len(result.warnings) >= 2


class TestParamTypeErrors:
    def test_start_line_not_int(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "main.py").write_text("line1\nline2\n")

        result = validate_action(
            {
                "action": "edit_file",
                "path": str(ws / "main.py"),
                "start_line": "not_a_number",
                "end_line": 2,
                "new_content": "x",
            },
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "type" in result.reason.lower() or "start_line" in result.reason.lower()

    def test_end_line_not_int(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "main.py").write_text("line1\nline2\n")

        result = validate_action(
            {
                "action": "edit_file",
                "path": str(ws / "main.py"),
                "start_line": 1,
                "end_line": "two",
                "new_content": "x",
            },
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "type" in result.reason.lower() or "end_line" in result.reason.lower()

    def test_content_not_string(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {
                "action": "write_file",
                "path": str(ws / "test.py"),
                "content": 123,
            },
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False


class TestPathOutsideWorkspace:
    def test_path_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        result = validate_action(
            {"action": "read_file", "path": str(outside)},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "outside" in result.reason.lower()

    def test_write_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        outside = tmp_path / "outside.txt"

        result = validate_action(
            {"action": "write_file", "path": str(outside), "content": "x"},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is False
        assert "outside" in result.reason.lower()


class TestErrorsAndWarningsLists:
    def test_errors_list_populated_on_failure(self):
        result = validate_action(
            {"action": "read_file"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is False
        assert len(result.errors) >= 1
        assert isinstance(result.errors[0], str)

    def test_warnings_list_empty_on_clean_action(self):
        result = validate_action(
            {"action": "read_file", "path": "x.py"},
            "/ws",
            FakeConfig(),
        )
        assert result.valid is True
        assert result.warnings == []

    def test_sanitized_params_preserved(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()

        result = validate_action(
            {"action": "read_file", "path": str(ws / "main.py")},
            str(ws),
            FakeConfig(),
        )
        assert result.valid is True
        assert result.sanitized_params["action"] == "read_file"
        assert result.sanitized_params["path"] == str(ws / "main.py")