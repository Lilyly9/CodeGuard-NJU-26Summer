"""Keyring 管理器单元测试。"""

import pytest

from src.keyring_manager import save_key, get_key, delete_key


class TestKeyringManager:
    def test_save_and_get_key(self):
        save_key("codeguard-test", "test-key-123")
        result = get_key("codeguard-test")
        assert result == "test-key-123"
        delete_key("codeguard-test")

    def test_delete_key_does_not_raise(self):
        delete_key("codeguard-test-nonexistent")

    def test_get_key_returns_empty_when_not_set(self):
        result = get_key("codeguard-test-nonexistent")
        assert result == ""