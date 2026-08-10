"""Memory 对话记忆模块 — 历史截断（最多 20 条）+ JSON 持久化。

提供 add_history / get_recent / save / load 接口。
"""

import json
import os
from pathlib import Path


class Memory:
    def __init__(self, task, history=None, last_test_result=None, step_count=0):
        self.task = task
        self.history = list(history) if history else []
        self.last_test_result = last_test_result
        self.step_count = step_count

    def add_history(self, action, result):
        self.history.append({
            "action": action,
            "result": _serialize_result(result),
        })
        self.step_count += 1
        if len(self.history) > 20:
            self.history = self.history[-20:]

    def get_recent(self, n=5):
        return self.history[-n:] if self.history else []

    def save(self, path="~/.codeguard/memory.json"):
        expanded = Path(path).expanduser()
        expanded.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "task": self.task,
            "history": self.history[-20:],
            "last_test_result": self.last_test_result,
            "step_count": self.step_count,
        }
        expanded.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self, path="~/.codeguard/memory.json"):
        expanded = Path(path).expanduser()
        if not expanded.is_file():
            return
        try:
            data = json.loads(expanded.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            return
        self.task = data.get("task", self.task)
        self.history = data.get("history", [])
        self.last_test_result = data.get("last_test_result")
        self.step_count = data.get("step_count", 0)


def _serialize_result(result):
    if result is None:
        return None
    if isinstance(result, dict):
        return {
            "success": result.get("success"),
            "data": str(result.get("data")) if result.get("data") is not None else None,
            "error": result.get("error"),
            "meta": {str(k): str(v) for k, v in result.get("meta", {}).items()},
        }
    return result