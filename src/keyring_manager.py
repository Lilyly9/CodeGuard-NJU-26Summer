"""Keyring 凭据管理器 — 安全存储/读取/删除 API Key。"""


def save_key(service: str, key: str) -> None:
    try:
        import keyring
    except ImportError:
        raise ImportError(
            "keyring is not installed. Install it with: pip install keyring"
        )
    keyring.set_password(service, "api_key", key)


def get_key(service: str) -> str:
    try:
        import keyring
    except ImportError:
        raise ImportError(
            "keyring is not installed. Install it with: pip install keyring"
        )
    return keyring.get_password(service, "api_key") or ""


def delete_key(service: str) -> None:
    try:
        import keyring
    except ImportError:
        raise ImportError(
            "keyring is not installed. Install it with: pip install keyring"
        )
    try:
        keyring.delete_password(service, "api_key")
    except Exception:
        pass