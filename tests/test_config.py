"""T03 配置模块单元测试 — 严格按 PLAN T03 验收。

覆盖 Config 默认值、load_config 文件读取、缺失字段兜底。
"""

import json

import pytest

from src.config import Config, _merge_config, load_config


class TestConfigDefaults:
    def test_default_workspace(self):
        c = Config()
        assert c.workspace == "."

    def test_default_max_steps(self):
        c = Config()
        assert c.max_steps == 10

    def test_default_command_timeout(self):
        c = Config()
        assert c.command_timeout == 30

    def test_default_max_file_size(self):
        c = Config()
        assert c.max_file_size == 100000

    def test_default_allowed_commands(self):
        c = Config()
        expected = ["python", "pytest", "ruff", "mypy", "git diff", "git status"]
        assert c.allowed_commands == expected

    def test_default_protected_files(self):
        c = Config()
        expected = [".env", ".git", "*.pem", "*.key"]
        assert c.protected_files == expected

    def test_default_allowed_extensions(self):
        c = Config()
        expected = [".py", ".json", ".toml", ".md", ".txt"]
        assert c.allowed_extensions == expected

    def test_default_auto_finish(self):
        c = Config()
        assert c.auto_finish_on_test_pass is False

    def test_default_log_level(self):
        c = Config()
        assert c.log_level == "info"

    def test_default_high_size_threshold(self):
        c = Config()
        assert c.high_size_threshold == 10240

    def test_default_forbidden_shell_chars(self):
        c = Config()
        expected = [";", "|", "&", ">", "<", "`", "$("]
        assert c.forbidden_shell_chars == expected

    def test_config_is_dataclass(self):
        c = Config()
        assert hasattr(c, "__dataclass_fields__")

    def test_config_instances_are_independent(self):
        c1 = Config()
        c2 = Config()
        c1.max_steps = 5
        assert c2.max_steps == 10


class TestLoadConfig:
    def test_load_config_defaults_when_file_missing(self, tmp_path):
        import os
        original_cwd = os.getcwd()
        try:
            os.chdir(str(tmp_path))
            c = load_config()
            assert c.max_steps == 10
            assert c.workspace == "."
        finally:
            os.chdir(original_cwd)

    def test_load_config_from_file(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[agent]\nmax_steps = 5\n")
        c = load_config(str(config_path))
        assert c.max_steps == 5
        assert c.workspace == "."

    def test_load_config_multiple_fields(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[agent]\n"
            "max_steps = 8\n"
            "workspace = \"./demo_project\"\n"
            "command_timeout = 60\n"
        )
        c = load_config(str(config_path))
        assert c.max_steps == 8
        assert c.workspace == "./demo_project"
        assert c.command_timeout == 60
        assert c.max_file_size == 100000

    def test_load_config_preserves_other_defaults(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[agent]\nmax_steps = 3\n")
        c = load_config(str(config_path))
        assert c.command_timeout == 30
        assert c.allowed_commands == [
            "python", "pytest", "ruff", "mypy", "git diff", "git status",
        ]

    def test_load_config_empty_file(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("")
        c = load_config(str(config_path))
        assert c.max_steps == 10
        assert c.workspace == "."

    def test_load_config_no_agent_section(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[other]\nkey = \"value\"\n")
        c = load_config(str(config_path))
        assert c.max_steps == 10
        assert c.workspace == "."

    def test_load_config_allowed_commands_override(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[agent]\n"
            "allowed_commands = [\"python\", \"pytest\"]\n"
        )
        c = load_config(str(config_path))
        assert c.allowed_commands == ["python", "pytest"]

    def test_load_config_protected_files_override(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[agent]\n"
            "protected_files = [\".env\", \".git\", \"secrets.json\"]\n"
        )
        c = load_config(str(config_path))
        assert c.protected_files == [".env", ".git", "secrets.json"]

    def test_load_config_boolean_field(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[agent]\nauto_finish_on_test_pass = true\n")
        c = load_config(str(config_path))
        assert c.auto_finish_on_test_pass is True

    def test_load_config_high_size_threshold(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text("[agent]\nhigh_size_threshold = 20480\n")
        c = load_config(str(config_path))
        assert c.high_size_threshold == 20480

    def test_load_config_forbidden_shell_chars(self, tmp_path):
        config_path = tmp_path / "config.toml"
        config_path.write_text(
            "[agent]\n"
            "forbidden_shell_chars = [\";\", \"|\", \"&\"]\n"
        )
        c = load_config(str(config_path))
        assert c.forbidden_shell_chars == [";", "|", "&"]


class TestMergeConfig:
    def test_merge_overrides_single_field(self):
        c = Config()
        result = _merge_config(c, {"max_steps": 5})
        assert result.max_steps == 5
        assert result.workspace == "."

    def test_merge_does_not_affect_unrelated(self):
        c = Config()
        c.max_steps = 20
        result = _merge_config(c, {"workspace": "/tmp"})
        assert result.workspace == "/tmp"
        assert result.max_steps == 20

    def test_merge_empty_dict_no_change(self):
        c = Config()
        c.max_steps = 7
        result = _merge_config(c, {})
        assert result.max_steps == 7
        assert result.workspace == "."

    def test_merge_unknown_key_ignored(self):
        c = Config()
        result = _merge_config(c, {"unknown_field": "ignored"})
        assert result.workspace == "."

    def test_merge_all_fields(self):
        c = Config()
        data = {
            "workspace": "/project",
            "max_steps": 5,
            "command_timeout": 60,
            "max_file_size": 50000,
            "allowed_commands": ["python"],
            "protected_files": [".env"],
            "allowed_extensions": [".py"],
            "auto_finish_on_test_pass": True,
            "log_level": "debug",
            "high_size_threshold": 5000,
            "forbidden_shell_chars": [";"],
        }
        result = _merge_config(c, data)
        assert result.workspace == "/project"
        assert result.max_steps == 5
        assert result.command_timeout == 60
        assert result.max_file_size == 50000
        assert result.allowed_commands == ["python"]
        assert result.protected_files == [".env"]
        assert result.allowed_extensions == [".py"]
        assert result.auto_finish_on_test_pass is True
        assert result.log_level == "debug"
        assert result.high_size_threshold == 5000
        assert result.forbidden_shell_chars == [";"]

    def test_merge_returns_same_instance(self):
        c = Config()
        result = _merge_config(c, {"max_steps": 3})
        assert result is c