import asyncio
import json

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from gitdraft.config import LLMConfig
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
CONFIG = LLMConfig("openrouter", "test-model", "private-test-key", temperature=0.4, max_tokens=1500)
CHANGES = Changes(" M sample.py", "+변경 내용 private-test-key", 1, 1)


@pytest.mark.parametrize("kind,data,expected", [("commit", COMMIT, CommitDraft), ("pr", PR, PRDraft)])
def test_one_request_and_settings(kind, data, expected):
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
    result = asyncio.run(generate(CHANGES, kind, CONFIG, stats, model=FunctionModel(respond)))
    assert isinstance(result, expected)
    assert stats.attempts == len(calls) == 1


def test_invalid_output_does_not_retry():
    calls = []
    async def respond(messages, info):
        calls.append(1)
        return ModelResponse(parts=[TextPart('{"invalid": "private-test-key"}')])
    with pytest.raises(DraftError, match="형식") as exc:
        asyncio.run(generate(CHANGES, "commit", CONFIG, RequestStats(), model=FunctionModel(respond)))
    assert len(calls) == 1
    assert "private-test-key" not in str(exc.value)


def test_redaction_preserves_structured_output():
    async def respond(messages, info):
        data = COMMIT | {"what": ["키 설정 api_key = private-test-key"]}
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])
    result = asyncio.run(generate(CHANGES, "commit", CONFIG, RequestStats(), model=FunctionModel(respond)))
    assert "private-test-key" not in result.model_dump_json()
    assert "[REDACTED]" in result.what[0]


def test_timeout_is_reported_without_raw_exception():
    async def fail(messages, info):
        raise TimeoutError("private-test-key")
    with pytest.raises(DraftError, match="시간이 초과") as exc:
        asyncio.run(generate(CHANGES, "commit", CONFIG, RequestStats(), model=FunctionModel(fail)))
    assert "private-test-key" not in str(exc.value)


@pytest.mark.parametrize("status,reason", [(401, "인증"), (402, "잔액"), (429, "한도"), (503, "서비스")])
def test_http_errors_are_safe(status, reason):
    async def fail(messages, info):
        raise ModelHTTPError(status, "model", {"error": "private-test-key"})
    with pytest.raises(DraftError, match=reason) as exc:
        asyncio.run(generate(CHANGES, "commit", CONFIG, RequestStats(), model=FunctionModel(fail)))
    assert "private-test-key" not in str(exc.value)


@pytest.mark.parametrize("provider,model_name,base_url", [
    ("openrouter", "openai/gpt-4.1-mini", None),
    ("openai-compatible", "local-model", "http://localhost:11434/v1"),
    ("anthropic", "test-model", None),
])
def test_provider_selection_and_retry_policy(provider, model_name, base_url):
    async def inspect_model():
        config = LLMConfig(provider, model_name, "private-test-key", base_url)
        async with model_session(config) as model:
            assert model.model_name == model_name
            assert model.client.max_retries == 0
            assert model.client.api_key == "private-test-key"
    asyncio.run(inspect_model())
