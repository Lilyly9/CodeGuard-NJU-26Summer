"""人工审批状态机 — 风险分级后的人工确认环节。

request_approval(decision, get_input, timeout) 返回 ApprovalResult。
forbidden 级别直接拒绝，不做人工绕过。
"""

import threading
from datetime import datetime

from src.models import ApprovalResult, RiskDecision, RiskLevel

_approval_log = []


def get_approval_log():
    return list(_approval_log)


def clear_approval_log():
    _approval_log.clear()


def request_approval(decision: RiskDecision, get_input=None, timeout=60) -> ApprovalResult:
    if decision.level == RiskLevel.FORBIDDEN:
        result = ApprovalResult(approved=False, reason="FORBIDDEN")
        _log(result, decision.level.value, "FORBIDDEN")
        return result

    if decision.action:
        _print_details(decision)

    if get_input is None:
        get_input = input

    while True:
        try:
            user_input = _read_with_timeout(get_input, timeout)
        except TimeoutError:
            result = ApprovalResult(approved=False, reason="TIMEOUT")
            _log(result, decision.level.value, "TIMEOUT")
            return result

        cleaned = user_input.strip().lower()
        if cleaned == "y":
            result = ApprovalResult(approved=True, reason="APPROVED")
            _log(result, decision.level.value, "APPROVED")
            return result
        if cleaned == "n":
            result = ApprovalResult(approved=False, reason="REJECTED")
            _log(result, decision.level.value, "REJECTED")
            return result


def _log(result, risk_level, reason):
    _approval_log.append({
        "approved": result.approved,
        "risk_level": risk_level,
        "reason": reason,
        "timestamp": datetime.now(),
    })


def _print_details(decision):
    action = decision.action or {}
    print(f"\n[APPROVAL REQUIRED]")
    print(f"  Action: {action.get('action', 'unknown')}")
    if action.get("path"):
        print(f"  Path:   {action['path']}")
    if action.get("command"):
        print(f"  Command: {action['command']}")
    print(f"  Risk:   {decision.level.value} — {decision.rule}")
    print(f"  Approve? (y/N): ", end="", flush=True)


def _read_with_timeout(get_input, timeout):
    result = [None]
    exc = [None]

    def _target():
        try:
            result[0] = get_input("> ")
        except Exception as e:
            exc[0] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        raise TimeoutError("Approval timed out")

    if exc[0]:
        raise exc[0]

    return result[0]