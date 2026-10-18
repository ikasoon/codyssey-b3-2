import asyncio
import json

import pytest
import httpx2
import openai
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from gitdraft.config import resolve_config
from gitdraft.drafts import CommitDraft, PRDraft
from gitdraft.errors import DraftError
from gitdraft.generator import RequestStats, generate
from gitdraft.gitio import Changes
from gitdraft.providers import model_session

COMMIT = dict(type="feat", subject="초안 생성 기능 추가", summary=["변경을 요약한다."],
              as_is=["생성 기능이 없었다."], to_be=["초안을 생성한다."], what=["기능을 추가했다."],
              why=["반복 작업을 줄인다."], how=["테스트 미실행: 실행 방법을 확인한다."])
PR = dict(title="초안 생성 기능 추가", summary=["변경을 요약한다."], why=["반복 작업을 줄인다."],
          what=["기능을 추가했다."], how_to_test=["테스트 미실행: 실행 방법을 확인한다."])
CHANGES = Changes(" M sample.py", "+변경 내용 private-test-key", 1, 1)


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-test-key")
    return resolve_config(model="test-model", temperature=0.4, max_tokens=1500)


@pytest.mark.parametrize("kind,data,expected", [("commit", COMMIT, CommitDraft), ("pr", PR, PRDraft)])
def test_one_request_and_settings(kind, data, expected, config):
    calls = []
    async def respond(messages, info):
        calls.append(info)
        prompt = next(p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        assert "private-test-key" not in prompt
        assert "변경 내용" in prompt
        assert info.model_settings["temperature"] == 0.4
        assert info.model_settings["max_tokens"] == 1500
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])
    stats = RequestStats()
    result = asyncio.run(generate(CHANGES, kind, config, stats, model=FunctionModel(respond)))
    assert isinstance(result, expected)
    assert stats.attempts == len(calls) == 1


def test_invalid_output_does_not_retry(config):
    calls = []
    async def respond(messages, info):
        calls.append(1)
        return ModelResponse(parts=[TextPart('{"invalid": "private-test-key"}')])
    with pytest.raises(DraftError, match="형식") as exc:
        asyncio.run(generate(CHANGES, "commit", config, RequestStats(), model=FunctionModel(respond)))
    assert len(calls) == 1
    assert "private-test-key" not in str(exc.value)


def test_redaction_preserves_structured_output(config):
    async def respond(messages, info):
        data = COMMIT | {"what": ["키 설정 api_key = private-test-key"]}
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])
    result = asyncio.run(generate(CHANGES, "commit", config, RequestStats(), model=FunctionModel(respond)))
    assert "private-test-key" not in result.model_dump_json()
    assert "[REDACTED]" in result.what[0]


def test_timeout_is_reported_without_raw_exception(config):
    async def fail(messages, info):
        raise TimeoutError("private-test-key")
    with pytest.raises(DraftError, match="시간이 초과") as exc:
        asyncio.run(generate(CHANGES, "commit", config, RequestStats(), model=FunctionModel(fail)))
    assert "private-test-key" not in str(exc.value)


@pytest.mark.parametrize("timed_out,reason", [(True, "시간이 초과"), (False, "연결할 수 없습니다")])
def test_wrapped_sdk_network_errors(timed_out, reason, config):
    async def fail(messages, info):
        request = httpx2.Request("POST", "https://example.com")
        cause = (openai.APITimeoutError(request) if timed_out
                 else openai.APIConnectionError(request=request))
        raise ModelAPIError("model", "private-test-key") from cause
    with pytest.raises(DraftError, match=reason) as exc:
        asyncio.run(generate(CHANGES, "commit", config, RequestStats(), model=FunctionModel(fail)))
    assert "private-test-key" not in str(exc.value)


@pytest.mark.parametrize("status,reason", [(401, "인증"), (402, "잔액"), (429, "한도"), (503, "서비스")])
def test_http_errors_are_safe(status, reason, config):
    async def fail(messages, info):
        raise ModelHTTPError(status, "model", {"error": "private-test-key"})
    with pytest.raises(DraftError, match=reason) as exc:
        asyncio.run(generate(CHANGES, "commit", config, RequestStats(), model=FunctionModel(fail)))
    assert "private-test-key" not in str(exc.value)


@pytest.mark.parametrize("provider,model_name,base_url", [
    ("openrouter", "openai/gpt-4.1-mini", None),
    ("openai-compatible", "local-model", "http://localhost:11434/v1"),
    ("anthropic", "test-model", None),
])
def test_provider_selection_and_retry_policy(provider, model_name, base_url, monkeypatch):
    monkeypatch.setenv("TEST_KEY", "private-test-key")
    async def inspect_model():
        config = resolve_config(provider=provider, model=model_name, base_url=base_url,
                                api_key_env="TEST_KEY", api_timeout=12.5)
        async with model_session(config) as model:
            assert model.model_name == model_name
            assert model.client.max_retries == 0
            assert model.client.api_key == "private-test-key"
            assert model.client.timeout == 12.5
            if provider == "openrouter":
                assert str(model.client.base_url) == "https://openrouter.ai/api/v1/"
    asyncio.run(inspect_model())
