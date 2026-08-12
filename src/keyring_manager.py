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


if __name__ == "__main__":
    import argparse
    import getpass
    import sys

    parser = argparse.ArgumentParser(description="CodeGuard API Key 凭据管理")
    parser.add_argument("--set", action="store_true", help="存储 API Key 到系统 keyring")
    parser.add_argument("--delete", action="store_true", help="从系统 keyring 删除 API Key")
    parser.add_argument("--status", action="store_true", help="检查是否已配置")
    args = parser.parse_args()

    km = KeyringManager()

    if args.set:
        print("Enter your OpenAI API Key (input will be hidden):")
        api_key = getpass.getpass("API Key: ").strip()
        if not api_key:
            print("Error: API Key cannot be empty.")
            sys.exit(1)
        km.set_key(api_key)
        print("API Key saved to system keyring.")
    elif args.delete:
        km.delete_key()
        print("API Key removed from system keyring.")
    elif args.status:
        if km.is_configured():
            print("Status: Configured (API Key is stored in system keyring)")
        else:
            print("Status: Not configured.")
    else:
        parser.print_help()