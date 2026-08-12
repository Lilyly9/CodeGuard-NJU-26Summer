"""LLM 客户端 — 抽象基类 + MockLLM + RealLLM。

BaseLLM: 定义 get_response(messages) 接口。
MockLLM: 预置响应序列，耗尽后自动返回 finish。
RealLLM: 调用 OpenAI API，支持超时重试。
"""

import json
import os
import time
from abc import ABC, abstractmethod


class BaseLLM(ABC):
    @abstractmethod
    def get_response(self, messages: list) -> str:
        ...


class MockLLM(BaseLLM):
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.call_count = 0

    def get_response(self, messages: list) -> str:
        if self.call_count < len(self._responses):
            resp = self._responses[self.call_count]
            self.call_count += 1
            return resp
        self.call_count += 1
        return json.dumps({"action": "finish"})


class RealLLM(BaseLLM):
    def __init__(self, api_key: str = "", model: str = "gpt-4o-mini",
                 max_tokens: int = 1024, temperature: float = 0.1,
                 timeout: int = 60, max_retries: int = 3):
        self._api_key = api_key or self._load_key()
        self._model = model or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._max_retries = max_retries

    @staticmethod
    def _load_key() -> str:
        env_key = os.environ.get("OPENAI_API_KEY", "")
        if env_key:
            return env_key
        from src.keyring_manager import KeyringManager
        km = KeyringManager()
        key = km.get_key()
        if key:
            return key
        raise ValueError("OPENAI_API_KEY not found. Set environment variable OPENAI_API_KEY or run 'python -m src.keyring_manager --set'.")

    def get_response(self, messages: list) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self._api_key,
            base_url=os.environ.get("OPENAI_BASE_URL", None),
            timeout=self._timeout,
        )

        last_error = None
        for attempt in range(self._max_retries):
            try:
                response = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=self._max_tokens,
                    temperature=self._temperature,
                )
                return response.choices[0].message.content
            except Exception as e:
                last_error = e
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)

        raise RuntimeError(
            f"LLM request failed after {self._max_retries} attempts: {last_error}"
        )