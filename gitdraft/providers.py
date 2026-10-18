from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
from pydantic_ai.models.openrouter import OpenRouterModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from gitdraft.config import LLMConfig
from gitdraft.errors import DraftError
from gitdraft.policy import MAX_RETRIES


@asynccontextmanager
async def model_session(config: LLMConfig) -> AsyncIterator[Model]:
    """제공자별 SDK 수명과 인증을 관리하고 공통 Model 인터페이스를 제공한다."""
    if config.provider == "anthropic":
        async with AsyncAnthropic(api_key=config.api_key, max_retries=MAX_RETRIES,
                                  timeout=config.api_timeout) as client:
            yield AnthropicModel(config.model, provider=AnthropicProvider(anthropic_client=client))
    elif config.provider in {"openrouter", "openai-compatible"}:
        async with AsyncOpenAI(api_key=config.api_key, base_url=config.base_url,
                               max_retries=MAX_RETRIES, timeout=config.api_timeout) as client:
            if config.provider == "openrouter":
                yield OpenRouterModel(config.model, provider=OpenRouterProvider(openai_client=client))
            else:
                yield OpenAIChatModel(
                    config.model, provider=OpenAIProvider(openai_client=client),
                    profile=OpenAIModelProfile(supports_json_object_output=False),
                )
    else:
        raise DraftError("지원하지 않는 LLM 제공자입니다.")
