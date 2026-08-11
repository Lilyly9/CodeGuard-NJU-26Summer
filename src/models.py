"""CodeGuard 数据模型 — 严格遵循 SPEC §12 定义。

包含 8 个核心实体 + RiskLevel 枚举，所有实体支持 to_dict() JSON 序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class RiskLevel(str, Enum):
    """风险等级枚举，对应 SPEC §4.3 四级分级。

    - LOW: 只读操作（list_directory, read_file, git status/diff）
    - MEDIUM: 写入/测试操作（write_file, edit_file, run_pytest, ruff, mypy）
    - HIGH: 高风险写入或危险命令（覆盖大文件、install、commit）
    - FORBIDDEN: 绝对禁止（路径遍历、敏感文件、Shell 控制符、网络命令）
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    FORBIDDEN = "FORBIDDEN"


# ---------------------------------------------------------------------------
# 序列化辅助函数
# ---------------------------------------------------------------------------

def _serialize(obj: Any) -> Any:
    """将任意对象递归转换为 JSON 可序列化类型。

    - dataclass 实例 → 调用其 to_dict()
    - datetime → ISO 8601 字符串
    - Enum → .value（字符串）
    - list → 递归转换每个元素
    - dict → 递归转换每个值
    - None → None
    - 其他 → 原样返回
    """
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# 8 个核心实体（SPEC §12）
# ---------------------------------------------------------------------------

@dataclass
class Action:
    """LLM 产生的动作。

    Attributes:
        type: 工具名称（list_files, read_file, write_file, run_command, run_pytest, finish）。
        params: 工具参数键值对。
        reason: LLM 执行该动作的理由（可选，默认空字符串）。
    """

    type: str
    params: dict = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "params": _serialize(self.params),
            "reason": self.reason,
        }


@dataclass
class ParseResult:
    """Parser 层的解析结果。

    Attributes:
        action: 解析成功时包含结构化动作；解析失败时为 None。
        error: 解析失败时的错误描述；成功时为 None。
    """

    action: Optional[Action] = None
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """解析是否成功（无错误且 action 非空）。"""
        return self.error is None and self.action is not None

    def to_dict(self) -> dict:
        return {
            "action": _serialize(self.action),
            "error": self.error,
        }


@dataclass
class ValidationResult:
    """Validation 层的校验结果。

    Attributes:
        valid: 校验是否通过。
        reason: 校验失败时的原因描述；成功时为空字符串。
        sanitized_params: 校验后清理过的参数（可能被规范化）。
        errors: 校验错误列表。
        warnings: 校验警告列表（如未知字段）。
    """

    valid: bool
    reason: str = ""
    sanitized_params: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "sanitized_params": _serialize(self.sanitized_params),
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class RiskDecision:
    """Risk Assessor 的风险分级结果。

    Attributes:
        level: 风险等级（LOW / MEDIUM / HIGH / FORBIDDEN）。
        rule: 触发该分级的规则描述。
        needs_approval: 是否需要人工审批（HIGH 级别为 True）。
        is_forbidden: 是否被直接拦截（FORBIDDEN 级别为 True）。
        action: 关联的动作参数（来自 ValidationResult.sanitized_params）。
    """

    level: RiskLevel
    rule: str
    needs_approval: bool = False
    is_forbidden: bool = False
    action: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "rule": self.rule,
            "needs_approval": self.needs_approval,
            "is_forbidden": self.is_forbidden,
            "action": _serialize(self.action),
        }


@dataclass
class ApprovalResult:
    """Approval Manager 的审批记录。

    Attributes:
        approved: 是否批准。
        user: 审批人标识（默认 "user"）。
        timestamp: 审批时间戳。
        reason: 审批意见/原因（拒绝时填写原因，超时时标注 "Timeout"）。
    """

    approved: bool
    user: str = "user"
    timestamp: datetime = field(default_factory=datetime.now)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "user": self.user,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
        }


@dataclass
class ToolResult:
    """工具执行结果。

    Attributes:
        success: 执行是否成功。
        data: 工具返回的数据（如文件内容、文件列表）。
        error: 失败时的错误描述；成功时为 None。
        meta: 元数据字典，可包含 diff, exit_code, stdout, stderr, finished 等。
    """

    success: bool
    data: Any = None
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": str(self.data) if self.data is not None else None,
            "error": self.error,
            "meta": _serialize(self.meta),
        }


@dataclass
class Memory:
    """会话记忆，存储当前任务上下文和历史。

    Attributes:
        task: 用户任务描述。
        history: 历史动作列表（最多 20 条）。
        last_test_result: 最近一次测试结果。
        approvals: 所有审批记录。
        step_count: 当前步数。
    """

    task: str
    history: list = field(default_factory=list)
    last_test_result: Optional[ToolResult] = None
    approvals: list = field(default_factory=list)
    step_count: int = 0

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "history": _serialize(self.history),
            "last_test_result": _serialize(self.last_test_result),
            "approvals": _serialize(self.approvals),
            "step_count": self.step_count,
        }


@dataclass
class AuditLog:
    """审计日志条目，记录每一步的完整信息。

    Attributes:
        step: 步数编号。
        timestamp: 记录时间戳。
        action: 执行的动作。
        risk_level: 风险等级字符串。
        approval: 审批结果（自动批准或人工审批）。
        tool_result: 工具执行结果。
        final_decision: 最终决策（EXECUTED / BLOCKED / REJECTED）。
    """

    step: int
    timestamp: datetime
    action: Action
    risk_level: str
    approval: Optional[ApprovalResult] = None
    tool_result: Optional[ToolResult] = None
    final_decision: str = ""

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "timestamp": self.timestamp.isoformat(),
            "action": _serialize(self.action),
            "risk_level": self.risk_level,
            "approval": _serialize(self.approval),
            "tool_result": _serialize(self.tool_result),
            "final_decision": self.final_decision,
        }