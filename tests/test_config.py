import pytest

from gitdraft.config import PROVIDERS, load_environment, resolve_config, resolve_settings
from gitdraft.errors import DraftError


def test_dotenv_preserves_environment_and_uppercase_key(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=file-value\nLLM_MODEL=file-model\n", encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "existing-value")
    monkeypatch.setenv("LLM_MODEL", "existing-model")
    load_environment(tmp_path)
    config = resolve_config()
    assert config.api_key == "existing-value"
    assert config.provider == "openrouter"
    assert config.model == "existing-model"
    assert "existing-value" not in repr(config)


def test_dotenv_loads_key_and_model(tmp_path):
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=file-value\nLLM_MODEL=file-model\n", encoding="utf-8",
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
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-key")
    assert resolve_config(model="custom-model").model == "custom-model"


def test_provider_switch_does_not_reuse_openrouter_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-key")
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


def test_runtime_defaults_without_model_or_key():
    settings = resolve_settings()
    assert settings.provider == "openrouter"
    assert settings.model is None
    assert settings.temperature == 0.2
    assert settings.max_tokens == 2048
    assert settings.api_timeout == 60
    assert settings.git_timeout == 30
    assert settings.safe_mode is True


@pytest.mark.parametrize("name,env,file_value,shell_value,cli_value", [
    ("temperature", "LLM_TEMPERATURE", "0.3", "0.4", 0),
    ("max_tokens", "LLM_MAX_TOKENS", "1024", "2048", 4096),
    ("api_timeout", "LLM_TIMEOUT_SECONDS", "10", "20", 0.5),
    ("git_timeout", "GITDRAFT_GIT_TIMEOUT_SECONDS", "5", "10", 0.5),
    ("safe_mode", "GITDRAFT_SAFE_MODE", "false", "true", False),
])
def test_runtime_setting_priority(tmp_path, monkeypatch, name, env, file_value,
                                  shell_value, cli_value):
    (tmp_path / ".env").write_text(f"{env}={file_value}\n")
    load_environment(tmp_path)
    expected = file_value == "true" if name == "safe_mode" else float(file_value)
    assert getattr(resolve_settings(), name) == expected
    monkeypatch.setenv(env, shell_value)
    load_environment(tmp_path)
    expected = shell_value == "true" if name == "safe_mode" else float(shell_value)
    assert getattr(resolve_settings(), name) == expected
    assert getattr(resolve_settings(**{name: cli_value}), name) == cli_value


@pytest.mark.parametrize("env,value,error", [
    ("LLM_TEMPERATURE", "nan", "temperature"),
    ("LLM_TEMPERATURE", "private-invalid-value", "temperature"),
    ("LLM_MAX_TOKENS", "1.5", "max-tokens"),
    ("LLM_MAX_TOKENS", "0", "max-tokens"),
    ("LLM_TIMEOUT_SECONDS", "inf", "api-timeout"),
    ("GITDRAFT_GIT_TIMEOUT_SECONDS", "0", "git-timeout"),
    ("GITDRAFT_SAFE_MODE", "private-invalid-value", "GITDRAFT_SAFE_MODE"),
])
def test_invalid_environment_has_safe_error(monkeypatch, env, value, error):
    monkeypatch.setenv(env, value)
    with pytest.raises(DraftError, match=error) as exc:
        resolve_settings()
    assert "private-invalid-value" not in str(exc.value)


@pytest.mark.parametrize("model", ["", " \t "])
def test_explicit_blank_model_does_not_fall_back(monkeypatch, model):
    monkeypatch.setenv("LLM_MODEL", "valid-environment-model")
    with pytest.raises(DraftError, match="--model.*LLM_MODEL"):
        resolve_config(model=model)


@pytest.mark.parametrize("provider,key_name", [
    ("openrouter", "OPENROUTER_API_KEY"),
    ("openai-compatible", "LLM_API_KEY"),
    ("anthropic", "ANTHROPIC_API_KEY"),
])
def test_provider_selects_only_its_credential(monkeypatch, provider, key_name):
    for name in ("OPENROUTER_API_KEY", "LLM_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.setenv(name, f"secret-{name}")
    config = resolve_config(provider=provider, model="test-model",
                            base_url="http://localhost:11434/v1" if provider == "openai-compatible" else None)
    assert config.provider == provider
    assert config.api_key == f"secret-{key_name}"


def test_key_presence_does_not_choose_provider(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-anthropic-key")
    monkeypatch.setenv("LLM_API_KEY", "private-generic-key")
    with pytest.raises(DraftError, match="OPENROUTER_API_KEY"):
        resolve_config(model="test-model")


@pytest.mark.parametrize("provider", PROVIDERS)
def test_custom_key_name_is_independent_of_provider(tmp_path, monkeypatch, provider):
    monkeypatch.delenv("TEAM_LLM_CREDENTIAL", raising=False)
    (tmp_path / ".env").write_text("TEAM_LLM_CREDENTIAL=private-team-key\n")
    load_environment(tmp_path)
    config = resolve_config(provider=provider, model="test-model", api_key_env="TEAM_LLM_CREDENTIAL",
                            base_url="http://localhost:11434/v1" if provider == "openai-compatible" else None)
    assert config.provider == provider
    assert config.api_key == "private-team-key"
    assert "private-team-key" not in repr(config)


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
    monkeypatch.setenv("OPENROUTER_API_KEY", "private-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    with pytest.raises(DraftError, match=error):
        resolve_config(**options)
