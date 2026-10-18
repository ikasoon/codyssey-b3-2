import subprocess

import pytest
from pydantic_ai import models
from gitdraft.config import Settings


@pytest.fixture(autouse=True)
def no_live_models(monkeypatch):
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    for name in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY",
                 *(field.validation_alias for field in Settings.model_fields.values())):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
