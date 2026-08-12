import pytest

from src.config import Config
from src.llm_client import MockLLM


@pytest.fixture
def mock_config():
    return Config(
        workspace="/tmp/test_ws",
        max_steps=10,
        command_timeout=30,
        max_file_size=100000,
        auto_finish_on_test_pass=True,
        allowed_commands=["pytest", "python", "ruff", "git diff", "git status"],
        protected_files=[".env", "*.pem", "*.key", ".git"],
    )


@pytest.fixture
def mock_llm():
    return MockLLM(responses=[
        '{"action": "read_file", "path": "src/main.py"}',
        '{"action": "finish"}',
    ])