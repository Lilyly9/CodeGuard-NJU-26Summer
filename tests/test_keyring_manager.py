"""Keyring 凭据管理单元测试 — 使用 unittest.mock 模拟 keyring 模块。"""

import keyring
import pytest

from unittest.mock import patch

from src.keyring_manager import KeyringManager


class TestKeyringManager:
    def test_set_and_get_key(self):
        km = KeyringManager()
        with patch.object(keyring, "set_password") as mock_set, \
             patch.object(keyring, "get_password", return_value="sk-test-key") as mock_get:
            km.set_key("sk-test-key")
            mock_set.assert_called_once_with("codeguard", "api_key", "sk-test-key")

            result = km.get_key()
            mock_get.assert_called_once_with("codeguard", "api_key")
            assert result == "sk-test-key"

    def test_delete_key(self):
        km = KeyringManager()
        with patch.object(keyring, "delete_password") as mock_delete:
            km.delete_key()
            mock_delete.assert_called_once_with("codeguard", "api_key")

    def test_delete_key_handles_password_delete_error(self):
        km = KeyringManager()
        with patch.object(keyring, "delete_password", side_effect=keyring.errors.PasswordDeleteError("not found")):
            km.delete_key()

    def test_is_configured_true(self):
        km = KeyringManager()
        with patch.object(keyring, "get_password", return_value="sk-test-key"):
            assert km.is_configured() is True

    def test_is_configured_false(self):
        km = KeyringManager()
        with patch.object(keyring, "get_password", return_value=None):
            assert km.is_configured() is False

    def test_get_key_returns_none_when_not_set(self):
        km = KeyringManager()
        with patch.object(keyring, "get_password", return_value=None):
            result = km.get_key()
            assert result is None

    def test_service_name_is_codeguard(self):
        assert KeyringManager.SERVICE_NAME == "codeguard"