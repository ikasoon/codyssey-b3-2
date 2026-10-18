import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from gitdraft.errors import DraftError

PROVIDERS = ("openrouter", "openai-compatible", "anthropic")
KEY_VARIABLES = {
    "openrouter": "openrouter_api_key",
    "openai-compatible": "LLM_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str = field(repr=False)
    base_url: str | None = None
    temperature: float = 0.2
    max_tokens: int = 2048


def load_environment(root: Path) -> None:
    """프로젝트의 .env만 읽고 기존 환경변수를 우선한다."""
    load_dotenv(root / ".env", override=False)


def resolve_config(
    *,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> LLMConfig:
    provider = provider or os.getenv("LLM_PROVIDER", "openrouter")
    if provider not in PROVIDERS:
        raise DraftError("지원하지 않는 LLM 제공자입니다. --help의 제공자 목록을 확인하세요.")
    model = model or os.getenv("LLM_MODEL")
    if not model or not model.strip():
        raise DraftError("모델이 설정되지 않았습니다. --model 또는 .env/환경변수의 LLM_MODEL을 지정하세요.")
    base_url = base_url or os.getenv("LLM_BASE_URL")
    if provider == "openai-compatible":
        try:
            url = urlsplit(base_url or "")
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
    elif base_url:
        raise DraftError("--base-url과 LLM_BASE_URL은 openai-compatible 제공자에서만 사용합니다.")
    if not math.isfinite(temperature) or not 0 <= temperature <= 1:
        raise DraftError("temperature는 0 이상 1 이하의 유한한 수여야 합니다.")
    if max_tokens < 1:
        raise DraftError("max-tokens는 1 이상이어야 합니다.")
    key_name = api_key_env or os.getenv("LLM_API_KEY_ENV") or KEY_VARIABLES[provider]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_name):
        raise DraftError("API 키 환경변수 이름이 올바르지 않습니다.")
    key = os.getenv(key_name, "").strip()
    if not key:
        raise DraftError(f"{key_name} 환경변수가 설정되지 않았습니다.")
    return LLMConfig(provider, model.strip(), key, base_url, temperature, max_tokens)
