import pytest

from gitdraft.config import load_environment, resolve_config
from gitdraft.errors import DraftError


def test_dotenv_preserves_environment_and_lowercase_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("openrouter_api_key=file-value\n", encoding="utf-8")
    monkeypatch.setenv("openrouter_api_key", "existing-value")
    load_environment(tmp_path)
    config = resolve_config()
    assert config.api_key == "existing-value"
    assert config.provider == "openrouter"
    assert "existing-value" not in repr(config)


def test_dotenv_loads_key(tmp_path):
    (tmp_path / ".env").write_text("openrouter_api_key=file-value\n", encoding="utf-8")
    load_environment(tmp_path)
    assert resolve_config().api_key == "file-value"


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


@pytest.mark.parametrize("options", [
    {"provider": "unknown"}, {"temperature": float("nan")}, {"temperature": 2},
    {"max_tokens": 0}, {"api_key_env": "bad name"},
    {"provider": "anthropic"}, {"base_url": "https://example.com"},
    {"provider": "openai-compatible", "model": "model", "base_url": "http://example.com/v1"},
    {"provider": "openai-compatible", "model": "model", "base_url": "https://user:pass@example.com"},
])
def test_invalid_config(options, monkeypatch):
    monkeypatch.setenv("openrouter_api_key", "private-key")
    with pytest.raises(DraftError):
        resolve_config(**options)
