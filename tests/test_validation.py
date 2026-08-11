"""校验层单元测试。"""

import pytest

from src.validation import validate_action
from src.models import Action, ParseResult, ValidationResult


class TestValidateAction:
    def test_valid_action_passes(self):
        action = Action(type="read_file", params={"path": "src/main.py"})
        parsed = ParseResult(action=action, error=None)
        result = validate_action(parsed)
        assert isinstance(result, ValidationResult)
        assert result.valid is True

    def test_empty_path_rejected(self):
        action = Action(type="read_file", params={"path": ""})
        parsed = ParseResult(action=action, error=None)
        result = validate_action(parsed)
        assert result.valid is False
        assert "empty" in result.reason.lower()

    def test_no_action_rejected(self):
        parsed = ParseResult(action=None, error="parse error")
        result = validate_action(parsed)
        assert result.valid is False