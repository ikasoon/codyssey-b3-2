import json
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart
from pydantic_ai.models.function import FunctionModel

from gitdraft.cli import main, parser
from gitdraft.drafts import CommitDraft
from gitdraft.errors import DraftError
from test_generator import COMMIT, PR


def test_clean_repository_does_not_need_key(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    assert main(["commit"]) == 0
    output = capsys.readouterr()
    assert "변경 사항이 없습니다" in output.err
    assert "API 호출 시도: 0회" in output.err
    assert not output.out


def test_missing_key_returns_error(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    (repo / "main.py").write_text("print('hello')\n")
    assert main(["commit", "--model", "custom-model"]) == 1
    output = capsys.readouterr()
    assert "openrouter_api_key" in output.err
    assert "API 호출 시도: 0회" in output.err
    assert not output.out


@pytest.mark.parametrize("command", ["commit", "pr"])
def test_missing_model_returns_error_without_api_call(repo, monkeypatch, capsys, command):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("openrouter_api_key", "private-test-key")
    (repo / "sample.py").write_text("print('hello')\n")
    assert main([command]) == 1
    output = capsys.readouterr()
    assert "모델이 설정되지 않았습니다" in output.err
    assert "--model" in output.err and "LLM_MODEL" in output.err
    assert "API 호출 시도: 0회" in output.err
    assert "private-test-key" not in output.out + output.err
    assert not output.out


@pytest.mark.parametrize("command,data,heading", [
    ("commit", COMMIT, "--- Commit Message ---"), ("pr", PR, "--- PR Body ---"),
])
@pytest.mark.parametrize("model_args,expected_model", [
    ([], "file-model"), (["--model", "custom-model"], "custom-model"),
])
def test_full_cli_with_fake_model(repo, monkeypatch, capsys, command, data, heading,
                                  model_args, expected_model):
    monkeypatch.chdir(repo)
    (repo / ".env").write_text("openrouter_api_key=private-test-key\nLLM_MODEL=file-model\n")
    (repo / "sample.py").write_text("print('hello')\n")
    async def respond(messages, info):
        assert info.model_settings["temperature"] == 0.3
        return ModelResponse(parts=[TextPart(json.dumps(data, ensure_ascii=False))])
    @asynccontextmanager
    async def session(config):
        assert config.api_key == "private-test-key"
        assert config.model == expected_model
        yield FunctionModel(respond)
    monkeypatch.setattr("gitdraft.generator.model_session", session)
    assert main([*model_args, command, "--temperature", "0.3"]) == 0
    output = capsys.readouterr()
    assert heading in output.out
    assert "--- Change Summary ---" in output.out
    assert "API 호출 시도: 1회" in output.err
    assert "private-test-key" not in output.out + output.err
    assert "제외" in output.err


def test_only_sensitive_files_skip_model(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    (repo / ".env").write_text("openrouter_api_key=private-test-key\n")
    assert main(["pr"]) == 0
    assert "API 호출 시도: 0회" in capsys.readouterr().err


@pytest.mark.parametrize("overrides,safe_mode,temperature,api_timeout,git_timeout", [
    ([], False, 0.7, 12.5, 7.5),
    (["--safe-mode", "--temperature", "0", "--api-timeout", "2", "--git-timeout", "3"],
     True, 0, 2, 3),
])
def test_runtime_settings_reach_collection_and_generation(
    repo, monkeypatch, capsys, overrides, safe_mode, temperature, api_timeout, git_timeout,
):
    monkeypatch.chdir(repo)
    (repo / ".env").write_text(
        "openrouter_api_key=private-test-key\nLLM_MODEL=file-model\n"
        "LLM_TEMPERATURE=0.7\nLLM_MAX_TOKENS=1024\nLLM_TIMEOUT_SECONDS=12.5\n"
        "GITDRAFT_GIT_TIMEOUT_SECONDS=7.5\nGITDRAFT_SAFE_MODE=false\n"
    )
    monkeypatch.setenv("LLM_MAX_TOKENS", "4096")
    (repo / "sample.txt").write_text("변경 내용\n" * 300)
    from gitdraft.gitio import collect_changes
    def collect(root, **options):
        assert options == {"safe_mode": safe_mode, "timeout": git_timeout}
        return collect_changes(root, **options)
    async def generate(changes, kind, config, stats):
        assert changes.truncated is safe_mode
        assert config.model == "file-model"
        assert config.temperature == temperature
        assert config.max_tokens == 4096
        assert config.api_timeout == api_timeout
        stats.attempts += 1
        return CommitDraft(**COMMIT)
    monkeypatch.setattr("gitdraft.cli.collect_changes", collect)
    monkeypatch.setattr("gitdraft.cli.generate", generate)
    assert main(["commit", *overrides]) == 0
    output = capsys.readouterr()
    assert "--- Commit Message ---" in output.out
    assert "API 호출 시도: 1회" in output.err
    assert "private-test-key" not in output.out + output.err


def test_invalid_environment_fails_without_api_call(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("LLM_TEMPERATURE", "private-invalid-value")
    (repo / "sample.txt").write_text("hello\n")
    assert main(["commit"]) == 1
    output = capsys.readouterr()
    assert "temperature" in output.err
    assert "API 호출 시도: 0회" in output.err
    assert "private-invalid-value" not in output.out + output.err


def test_wrong_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["pr"]) == 1
    assert "루트" in capsys.readouterr().err


@pytest.mark.parametrize("args", [
    ["commit", "--temperature", "nan"], ["pr", "--temperature", "2"],
    ["commit", "--max-tokens", "0"], ["commit", "--provider", "invalid"],
    ["commit", "--api-timeout", "inf"], ["pr", "--git-timeout", "0"],
])
def test_invalid_options_fail_before_collection(args):
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2


def test_legacy_option_spelling_and_safe_mode():
    args = parser().parse_args(["commit", "-model", "model", "-temperature", "0.5",
                               "-max-tokens", "1000", "-safe-mode"])
    assert args.model == "model"
    assert args.safe_mode
    assert args.max_tokens == 1000


def test_generation_failure_has_no_partial_output(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("openrouter_api_key", "private-test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    (repo / "sample.txt").write_text("hello\n")
    async def fail(changes, kind, config, stats):
        stats.attempts += 1
        raise DraftError("API 인증에 실패했습니다.")
    monkeypatch.setattr("gitdraft.cli.generate", fail)
    assert main(["commit"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "인증에 실패" in output.err
    assert "API 호출 시도: 1회" in output.err


def test_python_entrypoint_help():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, str(root / "main.py"), "--help"],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0
    assert "commit" in result.stdout and "pr" in result.stdout
