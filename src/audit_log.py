"""审计日志 — 将审计条目以 JSONL 格式追加写入文件。"""

import json
import os
from pathlib import Path

from src.models import AuditLog

_DEFAULT_LOG_DIR = "logs"


def log(entry: AuditLog, log_dir: str = _DEFAULT_LOG_DIR) -> None:
    os.makedirs(log_dir, exist_ok=True)
    log_path = Path(log_dir) / "audit.jsonl"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")