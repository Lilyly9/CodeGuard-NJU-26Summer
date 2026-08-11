"""人工审批状态机 — 风险分级后的人工确认环节。返回 ApprovalResult 对象。

request_approval(action, workspace) 返回 ApprovalResult(approved, reason, timestamp)
forbidden 级别直接拒绝，不做人工绕过。
"""

import threading
from datetime import datetime

from src.guardrail import evaluate
from src.models import ApprovalResult, RiskLevel

_approval_log = []


def get_approval_log():
    return list(_approval_log)


def clear_approval_log():
    _approval_log.clear()


def request_approval(action, workspace, get_input=None, timeout=60):
    risk = evaluate(action, workspace)

    if risk.level == RiskLevel.FORBIDDEN:
        _log(action, risk.level.value, False, "FORBIDDEN")
        return ApprovalResult(approved=False, reason="FORBIDDEN")

    _print_details(action, risk)

    if get_input is None:
        get_input = input

    while True:
        try:
            user_input = _read_with_timeout(get_input, timeout)
        except TimeoutError:
            _log(action, risk.level.value, False, "TIMEOUT")
            return ApprovalResult(approved=False, reason="TIMEOUT")

        cleaned = user_input.strip().lower()
        if cleaned == "y":
            _log(action, risk.level.value, True, "APPROVED")
            return ApprovalResult(approved=True, reason="APPROVED")
        if cleaned == "n":
            _log(action, risk.level.value, False, "REJECTED")
            return ApprovalResult(approved=False, reason="REJECTED")


def _log(action, risk_level, approved, reason):
    _approval_log.append({
        "action": action,
        "risk_level": risk_level,
        "approved": approved,
        "reason": reason,
        "timestamp": datetime.now(),
    })


def _print_details(action, risk):
    print(f"\n[APPROVAL REQUIRED]")
    print(f"  Action: {action.get('action', 'unknown')}")
    if action.get("path"):
        print(f"  Path:   {action['path']}")
    if action.get("command"):
        print(f"  Command: {action['command']}")
    print(f"  Risk:   {risk.level.value} — {risk.rule}")
    print(f"  Approve? (y/N): ", end="", flush=True)


def _read_with_timeout(get_input, timeout):
    result = [None]
    exc = [None]

    def _target():
        try:
            result[0] = get_input("")
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