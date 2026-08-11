"""pytest 全局 fixture — 供所有测试文件共享使用。"""

import json

import pytest

from src.llm_client import MockLLM
from src.config import Config


@pytest.fixture
def mock_llm():
    return MockLLM([json.dumps({"action": "finish"})])


@pytest.fixture
def default_config():
    return Config()


@pytest.fixture
def tmp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws)