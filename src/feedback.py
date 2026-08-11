"""反馈处理器 — 将 ToolResult 转为人类可读的文本反馈。"""

from src.models import ToolResult


def analyze(tool_result: ToolResult) -> str:
    if tool_result.success:
        return "成功"
    return "失败"