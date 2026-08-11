"""Config 配置加载模块 — 读取 config.toml，缺失字段用默认值兜底。"""

import os
from dataclasses import dataclass, field

try:
    import tomllib
except ImportError:
    import tomli as tomllib


@dataclass
class Config:
    workspace: str = "."
    max_steps: int = 10
    command_timeout: int = 30
    max_file_size: int = 100000
    auto_finish_on_test_pass: bool = True
    allowed_commands: list = field(default_factory=lambda: [
        "pytest", "python", "ruff", "git diff", "git status",
    ])
    protected_files: list = field(default_factory=lambda: [
        ".env", "*.pem", "*.key", ".git",
    ])


def load_config(path: str = "config.toml") -> Config:
    defaults = Config()

    if not path or not os.path.isfile(path):
        return defaults

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return defaults

    agent = data.get("agent", {})
    if not isinstance(agent, dict):
        return defaults

    return Config(
        workspace=agent.get("workspace", defaults.workspace),
        max_steps=agent.get("max_steps", defaults.max_steps),
        command_timeout=agent.get("command_timeout", defaults.command_timeout),
        max_file_size=agent.get("max_file_size", defaults.max_file_size),
        auto_finish_on_test_pass=agent.get("auto_finish_on_test_pass", defaults.auto_finish_on_test_pass),
        allowed_commands=agent.get("allowed_commands", defaults.allowed_commands),
        protected_files=agent.get("protected_files", defaults.protected_files),
    )