from dataclasses import dataclass, replace

import anthropic
import openai
from pydantic import ValidationError
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.exceptions import AgentRunError, ModelHTTPError, UserError
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from gitdraft.config import LLMConfig
from gitdraft.drafts import CommitDraft, PRDraft
from gitdraft.errors import DraftError
from gitdraft.gitio import Changes
from gitdraft.prompts import COMMIT_INSTRUCTIONS, INSTRUCTIONS, PR_INSTRUCTIONS, DraftKind, build_prompt
from gitdraft.providers import model_session
from gitdraft.safety import redact


@dataclass
class RequestStats:
    attempts: int = 0


def http_error(status: int) -> DraftError:
    reasons = {
        400: "요청 옵션 또는 모델의 출력 형식 지원을 확인하세요.",
        401: "API 인증에 실패했습니다. 환경변수의 키를 확인하세요.",
        402: "API 잔액이 부족합니다.",
        403: "API 접근 권한이 없습니다.",
        404: "모델 또는 API 주소를 찾을 수 없습니다.",
        429: "요청 한도에 도달했습니다. 잠시 후 다시 시도하세요.",
    }
    return DraftError(f"API 오류(HTTP {status}): " + reasons.get(status, "제공자 서비스 상태를 확인하세요."))


async def generate(
    changes: Changes, kind: DraftKind, config: LLMConfig, stats: RequestStats,
    *, model: Model | None = None,
) -> CommitDraft | PRDraft:
    """단일 요청으로 생성하고 제공자 오류의 원문·자격증명은 노출하지 않는다."""
    async def run(selected: Model) -> CommitDraft | PRDraft:
        output_type = CommitDraft if kind == "commit" else PRDraft
        instructions = INSTRUCTIONS + (COMMIT_INSTRUCTIONS if kind == "commit" else PR_INSTRUCTIONS)
        agent = Agent(selected, output_type=PromptedOutput(output_type),
                      instructions=instructions, retries=0,
                      model_settings={"temperature": config.temperature, "max_tokens": config.max_tokens})
        safe_changes = replace(changes, status=redact(changes.status, (config.api_key,)),
                               diff=redact(changes.diff, (config.api_key,)))
        prompt = build_prompt(safe_changes, kind)
        stats.attempts += 1
        result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=1))
        # 응답에도 입력에서 마스킹한 키나 토큰이 유출되지 않게 검증한다.
        values = result.output.model_dump()
        for key, value in values.items():
            values[key] = ([redact(item, (config.api_key,)) for item in value]
                           if isinstance(value, list) else redact(value, (config.api_key,)))
        return output_type.model_validate(values)

    try:
        if model is not None:
            return await run(model)
        async with model_session(config) as selected:
            return await run(selected)
    except (ModelHTTPError, openai.APIStatusError, anthropic.APIStatusError) as exc:
        raise http_error(exc.status_code) from None
    except (openai.APITimeoutError, anthropic.APITimeoutError, TimeoutError):
        raise DraftError("API 응답 시간이 초과되었습니다. 잠시 후 다시 시도하세요.") from None
    except (openai.APIConnectionError, anthropic.APIConnectionError):
        raise DraftError("API에 연결할 수 없습니다. 네트워크와 API 주소를 확인하세요.") from None
    except (AgentRunError, ValidationError):
        raise DraftError("LLM 응답이 한국어 초안 형식에 맞지 않습니다. 모델 또는 max-tokens를 확인하세요.") from None
    except UserError:
        raise DraftError("LLM 모델 설정이 올바르지 않습니다. 모델과 옵션 지원 여부를 확인하세요.") from None
