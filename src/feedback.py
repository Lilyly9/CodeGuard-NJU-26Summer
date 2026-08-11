"""Feedback 构建器 — 将 ToolResult 格式化为 LLM 可读的字符串。

build_feedback(result) 返回 str。
"""


def build_feedback(result: dict) -> str:
    if result.get("success"):
        data = result.get("data")
        if data:
            return f"Tool executed successfully.\nOutput:\n{data}"
        meta = result.get("meta", {})
        if meta.get("diff"):
            return f"Tool executed successfully.\nDiff:\n{meta['diff']}"
        return "Tool executed successfully."
    else:
        return f"Tool execution failed: {result.get('error', 'Unknown error')}"