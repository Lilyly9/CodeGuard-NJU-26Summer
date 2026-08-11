"""CodeGuard 配置模块 — 严格遵循 SPEC §9.4 定义。

支持从 config.toml 读取配置，缺失字段使用默认值兜底。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Config:
    workspace: str = "."
    max_steps: int = 10
    command_timeout: int = 30
    max_file_size: int = 100000
    allowed_commands: list = field(default_factory=lambda: [
        "python", "pytest", "ruff", "mypy", "git diff", "git status",
    ])
    protected_files: list = field(default_factory=lambda: [
        ".env", ".git", "*.pem", "*.key",
    ])
    allowed_extensions: list = field(default_factory=lambda: [
        ".py", ".json", ".toml", ".md", ".txt",
    ])
    auto_finish_on_test_pass: bool = False
    log_level: str = "info"
    high_size_threshold: int = 10240
    forbidden_shell_chars: list = field(default_factory=lambda: [
        ";", "|", "&", ">", "<", "`", "$(",
    ])


def _merge_config(config: Config, data: dict) -> Config:
    """用字典数据覆盖 Config 的对应字段，未提供的字段保留默认值。"""
    field_map = {
        "workspace": "workspace",
        "max_steps": "max_steps",
        "command_timeout": "command_timeout",
        "max_file_size": "max_file_size",
        "allowed_commands": "allowed_commands",
        "protected_files": "protected_files",
        "allowed_extensions": "allowed_extensions",
        "auto_finish_on_test_pass": "auto_finish_on_test_pass",
        "log_level": "log_level",
        "high_size_threshold": "high_size_threshold",
        "forbidden_shell_chars": "forbidden_shell_chars",
    }
    for toml_key, attr_name in field_map.items():
        if toml_key in data:
            setattr(config, attr_name, data[toml_key])
    return config


def load_config(path: Optional[str] = None) -> Config:
    """从 config.toml 加载配置，缺失字段使用默认值。

    Args:
        path: config.toml 文件路径，默认为当前目录的 "config.toml"。

    Returns:
        Config 实例，所有字段均有值（文件值或默认值）。
    """
    config = Config()
    if path is None:
        path = "config.toml"
    if not path:
        return config
    file_path = Path(path)
    if not file_path.is_file():
        return config
    try:
        import tomli
        toml_lib = tomli
    except ImportError:
        import tomllib
        toml_lib = tomllib
    with open(file_path, "rb") as f:
        data = toml_lib.load(f)
    agent_data = data.get("agent", {})
    return _merge_config(config, agent_data)