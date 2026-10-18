import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import Field, StringConstraints, TypeAdapter, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from gitdraft.errors import DraftError


@dataclass(frozen=True)
class ProviderDefinition:
    api_key_env: str
    base_url: str | None


PROVIDER_DEFINITIONS = {
    "openrouter": ProviderDefinition("openrouter_api_key", "https://openrouter.ai/api/v1"),
    "openai-compatible": ProviderDefinition("LLM_API_KEY", None),
    "anthropic": ProviderDefinition("ANTHROPIC_API_KEY", None),
}
PROVIDERS = tuple(PROVIDER_DEFINITIONS)
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Temperature = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
TokenCount = Annotated[int, Field(ge=1)]
Timeout = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Settings(BaseSettings):
    """기본값과 검증의 단일 정의. .env 로딩은 load_environment에서 한 번 수행한다."""

    model_config = SettingsConfigDict(
        case_sensitive=True, extra="forbid", frozen=True,
        hide_input_in_errors=True, loc_by_alias=False,
    )

    provider: Literal["openrouter", "openai-compatible", "anthropic"] = Field(
        default="openrouter", validation_alias="LLM_PROVIDER",
    )
    # None은 미지정 상태다. 변경이 있을 때 resolve_config가 모델과 키를 요구한다.
    model: NonEmptyString | None = Field(default=None, validation_alias="LLM_MODEL")
    base_url: NonEmptyString | None = Field(default=None, validation_alias="LLM_BASE_URL")
    api_key_env: Annotated[str, Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")] | None = Field(
        default=None, validation_alias="LLM_API_KEY_ENV",
    )
    temperature: Temperature = Field(default=0.2, validation_alias="LLM_TEMPERATURE")
    max_tokens: TokenCount = Field(default=2048, validation_alias="LLM_MAX_TOKENS")
    api_timeout: Timeout = Field(default=60.0, validation_alias="LLM_TIMEOUT_SECONDS")
    git_timeout: Timeout = Field(default=30.0, validation_alias="GITDRAFT_GIT_TIMEOUT_SECONDS")
    safe_mode: bool = Field(default=True, validation_alias="GITDRAFT_SAFE_MODE")


SETTING_ERRORS = {
    "provider": "지원하지 않는 LLM 제공자입니다. --help의 제공자 목록을 확인하세요.",
    "model": "모델이 설정되지 않았습니다. --model 또는 .env/환경변수의 LLM_MODEL을 지정하세요.",
    "base_url": "--base-url 또는 LLM_BASE_URL에 빈 값이 아닌 API 주소를 지정하세요.",
    "api_key_env": "API 키 환경변수 이름이 올바르지 않습니다.",
    "temperature": "temperature는 0 이상 1 이하의 유한한 수여야 합니다.",
    "max_tokens": "max-tokens는 1 이상의 정수여야 합니다.",
    "api_timeout": "api-timeout은 0보다 큰 유한한 초 단위 수여야 합니다.",
    "git_timeout": "git-timeout은 0보다 큰 유한한 초 단위 수여야 합니다.",
    "safe_mode": "GITDRAFT_SAFE_MODE는 true 또는 false로 지정하세요.",
}


@dataclass(frozen=True)
class LLMConfig:
    """검증을 마치고 선택한 제공자의 인증값까지 채운 실행 설정."""

    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str | None
    temperature: float
    max_tokens: int
    api_timeout: float


def load_environment(root: Path) -> None:
    """프로젝트의 .env만 읽고 기존 환경변수를 우선한다."""
    load_dotenv(root / ".env", override=False)


def setting_default(name: str) -> Any:
    """CLI 도움말과 직접 호출도 설정 스키마의 기본값을 참조한다."""
    return Settings.model_fields[name].default


def parse_setting(name: str, value: str) -> Any:
    """CLI 인자도 환경변수와 같은 타입·범위로 검증한다."""
    try:
        return TypeAdapter(Settings.model_fields[name].rebuild_annotation()).validate_python(value)
    except ValidationError:
        raise DraftError(SETTING_ERRORS[name]) from None


def resolve_settings(**options: Any) -> Settings:
    """명시적 CLI 인자 > 환경변수(셸 > .env) > 스키마 기본값."""
    try:
        values = {Settings.model_fields[name].validation_alias: value for name, value in options.items()}
        return Settings(**values)
    except KeyError:
        raise DraftError("지원하지 않는 설정 항목입니다.") from None
    except ValidationError as exc:
        name = exc.errors(include_input=False, include_context=False)[0]["loc"][0]
        raise DraftError(SETTING_ERRORS.get(name, "설정값이 올바르지 않습니다.")) from None


def resolve_config(settings: Settings | None = None, **options: Any) -> LLMConfig:
    settings = settings if settings is not None else resolve_settings(**options)
    if settings.model is None:
        raise DraftError(SETTING_ERRORS["model"])
    if settings.provider == "openai-compatible":
        try:
            url = urlsplit(settings.base_url or "")
            valid = (
                bool(url.hostname)
                and not (url.username or url.password or url.query or url.fragment)
                and (url.scheme == "https" or (
                    url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
                ))
            )
            _ = url.port
        except ValueError:
            valid = False
        if not valid:
            raise DraftError("--base-url에 HTTPS API 주소를 지정하세요. 로컬 서버만 HTTP를 허용합니다.")
    elif settings.base_url:
        raise DraftError("--base-url과 LLM_BASE_URL은 openai-compatible 제공자에서만 사용합니다.")
    definition = PROVIDER_DEFINITIONS[settings.provider]
    key_name = settings.api_key_env if settings.api_key_env is not None else definition.api_key_env
    key = os.getenv(key_name, "").strip()
    if not key:
        raise DraftError(f"{key_name} 환경변수가 설정되지 않았습니다.")
    return LLMConfig(
        settings.provider, settings.model, key, settings.base_url or definition.base_url,
        settings.temperature, settings.max_tokens, settings.api_timeout,
    )
