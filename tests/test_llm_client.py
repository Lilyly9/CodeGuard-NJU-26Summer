"""TDD Task 7: LLM 客户端测试 — MockLLM 预设序列 + RealLLM 跳过。"""

import json
import os

import pytest

from src.llm_client import BaseLLM, MockLLM, RealLLM


class TestBaseLLM:
    def test_base_llm_is_abstract(self):
        with pytest.raises(TypeError):
            BaseLLM()

    def test_base_llm_has_get_response_method(self):
        assert hasattr(BaseLLM, "get_response")
        assert callable(BaseLLM.get_response)


class TestMockLLM:
    def test_is_subclass_of_base_llm(self):
        assert issubclass(MockLLM, BaseLLM)

    def test_returns_preset_responses_in_order(self):
        mock = MockLLM([
            json.dumps({"action": "read_file", "path": "x.py"}),
            json.dumps({"action": "write_file", "path": "x.py", "content": "x=1"}),
            json.dumps({"action": "finish"}),
        ])
        assert mock.get_response([]) == json.dumps({"action": "read_file", "path": "x.py"})
        assert mock.get_response([]) == json.dumps({"action": "write_file", "path": "x.py", "content": "x=1"})
        assert mock.get_response([]) == json.dumps({"action": "finish"})

    def test_exhausted_returns_finish(self):
        mock = MockLLM([
            json.dumps({"action": "list_files", "path": "src/"}),
        ])
        assert mock.get_response([]) == json.dumps({"action": "list_files", "path": "src/"})
        assert mock.get_response([]) == json.dumps({"action": "finish"})
        assert mock.get_response([]) == json.dumps({"action": "finish"})

    def test_empty_responses_returns_finish_immediately(self):
        mock = MockLLM([])
        resp = mock.get_response([])
        parsed = json.loads(resp)
        assert parsed["action"] == "finish"

    def test_call_count_tracks_invocations(self):
        mock = MockLLM([
            json.dumps({"action": "read_file", "path": "a.py"}),
            json.dumps({"action": "read_file", "path": "b.py"}),
        ])
        mock.get_response([])
        mock.get_response([])
        assert mock.call_count == 2

    def test_ignores_context(self):
        mock = MockLLM([json.dumps({"action": "finish", "summary": "done"})])
        resp1 = mock.get_response([{"role": "system", "content": "hello"}])
        mock2 = MockLLM([json.dumps({"action": "finish", "summary": "done"})])
        resp2 = mock2.get_response([{"role": "system", "content": "goodbye"}])
        assert resp1 == resp2


class TestRealLLM:
    def test_is_subclass_of_base_llm(self):
        assert issubclass(RealLLM, BaseLLM)

    def test_instantiation_without_api_key(self):
        llm = RealLLM(api_key="test-key")
        assert llm is not None

    def test_get_response_skips_without_real_api_key(self):
        if not os.environ.get("OPENAI_API_KEY"):
            pytest.skip("No OPENAI_API_KEY set — skipping real LLM test")
        llm = RealLLM()
        messages = [{"role": "user", "content": "Say hello in JSON"}]
        resp = llm.get_response(messages)
        assert isinstance(resp, str)
        assert len(resp) > 0