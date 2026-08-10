"""人工审批状态机 — 风险分级后的人工确认环节。

request_approval(action, workspace) 返回 True/False，并写入内存日志。
forbidden 级别直接拒绝，不做人工绕过。
"""

import threading
from datetime import datetime

from src.guardrail import evaluate

_approval_log = []


def get_approval_log():
    return list(_approval_log)


def clear_approval_log():
    _approval_log.clear()


def request_approval(action, workspace, get_input=None, timeout=60):
    risk_level = evaluate(action, workspace)

    if risk_level == "forbidden":
        _log(action, risk_level, False, "FORBIDDEN")
        return False

    _print_details(action, risk_level)

    if get_input is None:
        get_input = input

    while True:
        try:
            user_input = _read_with_timeout(get_input, timeout)
        except TimeoutError:
            _log(action, risk_level, False, "TIMEOUT")
            return False

        cleaned = user_input.strip().lower()
        if cleaned == "y":
            _log(action, risk_level, True, "APPROVED")
            return True
        if cleaned == "n":
            _log(action, risk_level, False, "REJECTED")
            return False


def _log(action, risk_level, approved, reason):
    _approval_log.append({
        "action": action,
        "risk_level": risk_level,
        "approved": approved,
        "reason": reason,
        "timestamp": datetime.now(),
    })


def _print_details(action, risk_level):
    pass


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