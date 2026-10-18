import pytest

from gitdraft.config import PROVIDERS, load_environment, resolve_config
from gitdraft.errors import DraftError


def test_dotenv_preserves_environment_and_lowercase_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "openrouter_api_key=file-value\nLLM_MODEL=file-model\n", encoding="utf-8",
    )
    monkeypatch.setenv("openrouter_api_key", "existing-value")
    monkeypatch.setenv("LLM_MODEL", "existing-model")
    load_environment(tmp_path)
    config = resolve_config()
    assert config.api_key == "existing-value"
    assert config.provider == "openrouter"
    assert config.model == "existing-model"
    assert "existing-value" not in repr(config)


def test_dotenv_loads_key_and_model(tmp_path):
    (tmp_path / ".env").write_text(
        "openrouter_api_key=file-value\nLLM_MODEL=file-model\n", encoding="utf-8",
    )
    load_environment(tmp_path)
    config = resolve_config()
    assert config.api_key == "file-value"
    assert config.model == "file-model"


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("model", [None, "", " \t "])
def test_missing_or_blank_model_is_rejected(provider, model, monkeypatch):
    if model is not None:
        monkeypatch.setenv("LLM_MODEL", model)
    with pytest.raises(DraftError, match="--model.*LLM_MODEL"):
        resolve_config(provider=provider)


def test_explicit_model_without_environment(monkeypatch):
    monkeypatch.setenv("openrouter_api_key", "private-key")
    assert resolve_config(model="custom-model").model == "custom-model"


def test_provider_switch_does_not_reuse_openrouter_key(monkeypatch):
    monkeypatch.setenv("openrouter_api_key", "private-key")
    with pytest.raises(DraftError, match="ANTHROPIC_API_KEY"):
        resolve_config(provider="anthropic", model="custom-model")


def test_explicit_options_override_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("LLM_MODEL", "old-model")
    monkeypatch.setenv("CUSTOM_KEY", "custom-secret")
    config = resolve_config(provider="openai-compatible", model="local-model",
                            base_url="http://localhost:11434/v1", api_key_env="CUSTOM_KEY")
    assert config.model == "local-model"
    assert config.api_key == "custom-secret"


@pytest.mark.parametrize("options,error", [
    ({"provider": "unknown"}, "지원하지 않는 LLM 제공자"),
    ({"temperature": float("nan")}, "temperature"),
    ({"temperature": 2}, "temperature"),
    ({"max_tokens": 0}, "max-tokens"),
    ({"api_key_env": "bad name"}, "API 키 환경변수 이름"),
    ({"base_url": "https://example.com"}, "openai-compatible 제공자에서만"),
    ({"provider": "openai-compatible", "base_url": "http://example.com/v1"}, "HTTPS API 주소"),
    ({"provider": "openai-compatible", "base_url": "https://user:pass@example.com"}, "HTTPS API 주소"),
])
def test_invalid_config(options, error, monkeypatch):
    monkeypatch.setenv("openrouter_api_key", "private-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    with pytest.raises(DraftError, match=error):
        resolve_config(**options)
