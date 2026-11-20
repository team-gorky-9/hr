"""Клиент OpenAI-совместимого API без сети: SDK подменён, проверяется поведение клиента."""
import httpx2 as httpx  # HTTP-библиотека, на которой построен openai SDK
import openai
import pytest
from pydantic import BaseModel

from app.ai.client import OpenAICompatClient, extract_json, inline_schema
from app.ai.config import LLMConfig
from app.ai.errors import LLMInvalidResponseError, LLMUnavailableError


class Answer(BaseModel):
    status: str


class Outer(BaseModel):
    items: list[Answer]


class FakeSDK:
    """Отвечает по очереди заготовками: строка — content, исключение — бросить."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.chat = self
        self.completions = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        message = type("M", (), {"content": reply})
        usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})
        return type("R", (), {"choices": [type("C", (), {"message": message})], "usage": usage})


def client(*replies, **config):
    llm = OpenAICompatClient(LLMConfig(yandex_api_key="k", yandex_folder_id="b1g", llm_provider="yandexgpt", **config))
    llm._sdk = FakeSDK(*replies)
    return llm


def http_error(cls, status):
    request = httpx.Request("POST", "https://llm.api.cloud.yandex.net/v1/chat/completions")
    return cls("err", response=httpx.Response(status, request=request), body=None)


def call(llm, model=Answer):
    return llm.complete_structured("system", "user <resume_text>секрет</resume_text>", model, model_role="assess",
                                   prompt_version="assess-v1")


def test_json_schema_is_sent_and_parsed():
    llm = client('{"status": "met"}')
    assert call(llm).status == "met"
    request = llm._sdk.requests[0]
    assert request["response_format"]["type"] == "json_schema"
    assert request["model"] == "gpt://b1g/yandexgpt/latest" and request["temperature"] == 0.0
    assert llm.calls[0].status == "ok" and llm.calls[0].mode == "json_schema"


def test_falls_back_to_prompt_json_when_schema_rejected():
    llm = client(http_error(openai.BadRequestError, 400), '```json\n{"status": "unknown"}\n```')
    assert call(llm).status == "unknown"
    assert "response_format" not in llm._sdk.requests[1]
    assert "JSON-схеме" in llm._sdk.requests[1]["messages"][0]["content"]
    assert llm.calls[0].mode == "prompt_json"


def test_invalid_json_is_repaired_once_then_fails():
    llm = client('{"wrong": 1}', '{"status": "met"}')
    assert call(llm).status == "met"
    assert "не прошёл проверку" in llm._sdk.requests[1]["messages"][-1]["content"]
    broken = client('{"wrong": 1}', '{"still": 2}')
    with pytest.raises(LLMInvalidResponseError):
        call(broken)
    assert broken.calls[0].status == "invalid_response"


def test_timeout_is_retried_then_unavailable():
    request = httpx.Request("POST", "https://x")
    ok = client(openai.APITimeoutError(request), '{"status": "met"}')
    assert call(ok).status == "met" and ok.calls[0].attempts == 2
    down = client(openai.APITimeoutError(request), openai.APITimeoutError(request))
    with pytest.raises(LLMUnavailableError):
        call(down)


def test_auth_error_is_unavailable_without_secrets():
    llm = client(http_error(openai.AuthenticationError, 401))
    with pytest.raises(LLMUnavailableError) as error:
        call(llm)
    assert "401" in str(error.value)
    assert "секрет" not in str(llm.calls[0].as_audit()) and "k" != llm.calls[0].as_audit().get("error")


def test_missing_key_is_reported():
    with pytest.raises(LLMUnavailableError):
        OpenAICompatClient(LLMConfig(yandex_api_key=None, _env_file=None))


def test_schema_has_no_refs():
    assert "$ref" not in str(inline_schema(Outer))


def test_extract_json_strips_text_around():
    assert extract_json('Вот ответ:\n```json\n{"a": 1}\n```') == '{"a": 1}'
