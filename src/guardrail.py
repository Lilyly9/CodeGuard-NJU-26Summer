"""风险分级护栏 — 代码判断，非提示词。返回 RiskDecision 对象。

assess_risk(validated, config) 返回 RiskDecision(level, rule, needs_approval, is_forbidden)
evaluate(action, workspace) 为向后兼容包装器，内部调用 validate_action + assess_risk。
"""

import re

from src.models import RiskDecision, RiskLevel, ValidationResult


def assess_risk(validated: ValidationResult, config) -> RiskDecision:
    if not validated.valid:
        return RiskDecision(
            level=RiskLevel.FORBIDDEN,
            rule=validated.reason,
            needs_approval=False,
            is_forbidden=True,
            action=validated.sanitized_params,
        )

    params = validated.sanitized_params
    action_type = (params.get("action") or "").strip()
    command = (params.get("command") or "").strip()
    path = (params.get("path") or "").strip()

    cmd_normalized = re.sub(r"\s+", " ", command)

    def _make(level, rule, needs_approval=False, is_forbidden=False):
        return RiskDecision(
            level=level,
            rule=rule,
            needs_approval=needs_approval,
            is_forbidden=is_forbidden,
            action=params,
        )

    # ── forbidden ──────────────────────────────────────────────────────────

    if any(conn in cmd_normalized for conn in ("&&", "||", "|", ";")):
        return _make(RiskLevel.FORBIDDEN, "Shell connector detected in command", is_forbidden=True)

    if re.search(r"\brm\s+-rf\s+/(?:\s|$)", cmd_normalized):
        return _make(RiskLevel.FORBIDDEN, "rm -rf / is forbidden", is_forbidden=True)

    if re.search(r"\bshutdown\b", cmd_normalized):
        return _make(RiskLevel.FORBIDDEN, "shutdown command is forbidden", is_forbidden=True)

    if re.search(r"\bformat\b", cmd_normalized):
        return _make(RiskLevel.FORBIDDEN, "format command is forbidden", is_forbidden=True)

    # ── high ───────────────────────────────────────────────────────────────

    if re.search(r"\brm\b", cmd_normalized):
        return _make(RiskLevel.HIGH, "rm command requires approval", needs_approval=True)

    if "git commit" in cmd_normalized:
        return _make(RiskLevel.HIGH, "git commit requires approval", needs_approval=True)

    # ── medium ─────────────────────────────────────────────────────────────

    if "pytest" in cmd_normalized:
        return _make(RiskLevel.MEDIUM, "Test execution")

    if action_type in ("write_file", "edit_file") and path.endswith(".py"):
        return _make(RiskLevel.MEDIUM, "Python file write")

    # ── low ────────────────────────────────────────────────────────────────

    if action_type == "read_file":
        return _make(RiskLevel.LOW, "Read-only operation")

    if action_type in ("list_files", "list_directory"):
        return _make(RiskLevel.LOW, "Read-only operation")

    if "git status" in cmd_normalized or "git diff" in cmd_normalized:
        return _make(RiskLevel.LOW, "Read-only operation")

    return _make(RiskLevel.LOW, "Default low risk")


def evaluate(action, workspace):
    """Backward-compatible wrapper. Calls validate_action + assess_risk."""
    from src.validation import validate_action
    from src.config import Config

    config = Config()
    validated = validate_action(action, workspace, config)
    return assess_risk(validated, config)