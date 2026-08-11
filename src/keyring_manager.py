"""Keyring 凭据管理 — 使用系统 keyring 安全存储 API Key。

KeyringManager 封装 keyring 库的 set/get/delete 操作，
不在日志或输出中打印 key 明文。
"""

from typing import Optional

import keyring


class KeyringManager:
    SERVICE_NAME = "codeguard"

    def set_key(self, key: str) -> None:
        keyring.set_password(self.SERVICE_NAME, "api_key", key)

    def get_key(self) -> Optional[str]:
        return keyring.get_password(self.SERVICE_NAME, "api_key")

    def delete_key(self) -> None:
        try:
            keyring.delete_password(self.SERVICE_NAME, "api_key")
        except keyring.errors.PasswordDeleteError:
            pass

    def is_configured(self) -> bool:
        return self.get_key() is not None