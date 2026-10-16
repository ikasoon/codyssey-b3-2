import subprocess

import pytest
from pydantic_ai import models


@pytest.fixture(autouse=True)
def no_live_models(monkeypatch):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    for name in ("openrouter_api_key", "ANTHROPIC_API_KEY", "LLM_API_KEY",
                 "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY_ENV"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
