"""校验层 — 对解析后的动作进行合法性校验，返回 ValidationResult。"""

from src.models import ParseResult, ValidationResult


def validate_action(parsed: ParseResult) -> ValidationResult:
    if parsed.action is None:
        return ValidationResult(valid=False, reason="No action in parse result")

    action = parsed.action
    path = action.params.get("path", "")
    if isinstance(path, str) and path == "":
        return ValidationResult(
            valid=False,
            reason="Path cannot be empty",
            sanitized_params=action.params,
        )

    return ValidationResult(
        valid=True,
        reason="",
        sanitized_params=action.params,
    )