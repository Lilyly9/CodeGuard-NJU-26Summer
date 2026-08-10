"""TDD Task 6: Config 配置加载模块测试。"""

import pytest

from src.config import Config, load_config


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
        assert "pytest" in c.allowed_commands
        assert "python" in c.allowed_commands
        assert "ruff" in c.allowed_commands
        assert "git diff" in c.allowed_commands
        assert "git status" in c.allowed_commands

    def test_default_protected_files(self):
        c = Config()
        assert ".env" in c.protected_files
        assert "*.pem" in c.protected_files
        assert "*.key" in c.protected_files
        assert ".git" in c.protected_files

    def test_config_is_dataclass(self):
        c = Config()
        d = c.__dict__
        assert "workspace" in d
        assert "max_steps" in d


class TestLoadConfigFileNotFound:
    def test_file_not_exists_returns_defaults(self, tmp_path):
        c = load_config(str(tmp_path / "nonexistent.toml"))
        assert c.workspace == "."
        assert c.max_steps == 10
        assert c.command_timeout == 30
        assert isinstance(c, Config)

    def test_empty_path_returns_defaults(self):
        c = load_config("")
        assert c.max_steps == 10


class TestLoadConfigPartialOverride:
    def test_partial_config_falls_back_to_defaults(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("""[agent]
max_steps = 5
workspace = "./demo"
""")
        c = load_config(str(toml_path))
        assert c.max_steps == 5
        assert c.workspace == "./demo"
        assert c.command_timeout == 30
        assert c.max_file_size == 100000

    def test_override_allowed_commands(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("""[agent]
allowed_commands = ["python", "pytest"]
""")
        c = load_config(str(toml_path))
        assert c.allowed_commands == ["python", "pytest"]

    def test_override_protected_files(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("""[agent]
protected_files = [".env", "secret.txt"]
""")
        c = load_config(str(toml_path))
        assert "secret.txt" in c.protected_files
        assert ".env" in c.protected_files

    def test_override_all_fields(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("""[agent]
workspace = "/tmp/proj"
max_steps = 3
command_timeout = 60
max_file_size = 50000
allowed_commands = ["pytest"]
protected_files = [".env"]
""")
        c = load_config(str(toml_path))
        assert c.workspace == "/tmp/proj"
        assert c.max_steps == 3
        assert c.command_timeout == 60
        assert c.max_file_size == 50000
        assert c.allowed_commands == ["pytest"]
        assert c.protected_files == [".env"]


class TestLoadConfigEdgeCases:
    def test_empty_file_returns_defaults(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("")
        c = load_config(str(toml_path))
        assert c.max_steps == 10

    def test_no_agent_section_returns_defaults(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("[other]\nkey = 1\n")
        c = load_config(str(toml_path))
        assert c.max_steps == 10

    def test_load_config_returns_config_instance(self, tmp_path):
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("[agent]\nmax_steps = 7\n")
        c = load_config(str(toml_path))
        assert isinstance(c, Config)


class TestConfigTypeConversion:
    def test_max_steps_is_int(self):
        c = Config()
        assert isinstance(c.max_steps, int)

    def test_command_timeout_is_int(self):
        c = Config()
        assert isinstance(c.command_timeout, int)

    def test_max_file_size_is_int(self):
        c = Config()
        assert isinstance(c.max_file_size, int)

    def test_allowed_commands_is_list(self):
        c = Config()
        assert isinstance(c.allowed_commands, list)

    def test_protected_files_is_list(self):
        c = Config()
        assert isinstance(c.protected_files, list)


class TestConfigImmutableDefaults:
    def test_default_lists_are_independent(self):
        c1 = Config()
        c2 = Config()
        c1.allowed_commands.append("extra")
        assert "extra" not in c2.allowed_commands

    def test_default_protected_files_independent(self):
        c1 = Config()
        c2 = Config()
        c1.protected_files.append("extra")
        assert "extra" not in c2.protected_files