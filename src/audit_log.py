"""审计日志模块 — 记录 agent 每一步的决策和执行结果。

AuditLogger 写入 JSONL 格式，自动过滤敏感信息。
"""

import copy
import json
import os
from datetime import datetime
from pathlib import Path


_SENSITIVE_PATTERNS = ["api_key", "API_KEY", "OPENAI_API_KEY", "token", "secret", "password"]


class AuditLogger:
    def __init__(self, log_path: Path):
        self._log_path = Path(log_path)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._entries = []

    def log(self, entry: dict) -> None:
        serialized = self._serialize_entry(entry)
        filtered = self._filter_sensitive(serialized)
        self._entries.append(filtered)
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(filtered, ensure_ascii=False) + "\n")

    def get_entries(self) -> list:
        return copy.deepcopy(self._entries)

    def _serialize_entry(self, entry: dict) -> dict:
        serialized = dict(entry)
        if "timestamp" in serialized and isinstance(serialized["timestamp"], datetime):
            serialized["timestamp"] = serialized["timestamp"].isoformat()
        if "tool_result" in serialized:
            tr = serialized["tool_result"]
            if isinstance(tr, dict):
                serialized["tool_result"] = {
                    "success": tr.get("success"),
                    "data": str(tr.get("data")) if tr.get("data") is not None else None,
                    "error": tr.get("error"),
                    "meta": {str(k): str(v) for k, v in tr.get("meta", {}).items()},
                }
        return serialized

    def _filter_sensitive(self, data: dict) -> dict:
        result = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(pattern.lower() in key_lower for pattern in _SENSITIVE_PATTERNS):
                result[key] = "***REDACTED***"
            elif isinstance(value, dict):
                result[key] = self._filter_sensitive(value)
            else:
                result[key] = value
        return result