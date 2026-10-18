import subprocess

import pytest

from conftest import git
from gitdraft.errors import DraftError
from gitdraft.gitio import collect_changes, parse_status
from gitdraft.safety import limit_diff, redact


def test_empty_repository(repo):
    result = collect_changes(repo)
    assert result.total_files == 0
    assert not result.diff


def test_staged_unstaged_untracked_and_literal_paths(repo):
    (repo / "file.py").write_text("initial\n")
    git(repo, "add", "file.py")
    (repo / "file.py").write_text("working\n")
    (repo / "[new] file.py").write_text("new content\n")
    before = git(repo, "diff", "--cached").stdout
    result = collect_changes(repo)
    assert result.total_files == 2
    assert all(s in result.diff for s in ("[Staged]", "[Unstaged]", "[Untracked]"))
    assert "new content" in result.diff
    assert git(repo, "diff", "--cached").stdout == before


def test_rename_status_with_special_filename():
    change, = parse_status("R  new\nname.py\0old name.py\0")
    assert change.path == "new\nname.py"
    assert change.original_path == "old name.py"


def test_secrets_excluded_and_limits_applied(repo, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secret-value")
    (repo / ".env").write_text("OPENROUTER_API_KEY=must-not-send\n")
    git(repo, "add", ".env")
    for i in range(12):
        (repo / f"file{i:02}.txt").write_text("sk-or-secret-value user@example.com\n" * 50)
    result = collect_changes(repo)
    assert result.included_files == 10
    assert result.excluded_files == 1
    assert result.truncated
    assert len(result.diff.splitlines()) <= 200
    assert "must-not-send" not in result.diff
    assert "sk-or-secret-value" not in result.diff
    assert "user@example.com" not in result.diff
    assert ".env" not in result.status


def test_safe_mode_off_removes_limits_but_keeps_redaction(repo):
    (repo / "long.txt").write_text("user@example.com\n" * 300)
    result = collect_changes(repo, safe_mode=False)
    assert len(result.diff.splitlines()) > 200
    assert "user@example.com" not in result.diff


def test_untracked_symlink_is_not_followed(repo, tmp_path_factory):
    outside = tmp_path_factory.mktemp("private") / "key.txt"
    outside.write_text("private-content")
    (repo / "link.txt").symlink_to(outside)
    result = collect_changes(repo)
    assert not result.diff
    assert result.excluded_files == 1


def test_subdirectory_rejected(repo):
    subdir = repo / "subdir"
    subdir.mkdir()
    with pytest.raises(DraftError, match="루트"):
        collect_changes(subdir)


def test_binary_diff(repo):
    (repo / "image.bin").write_bytes(b"\0\1\2")
    assert "Binary files" in collect_changes(repo).diff


def test_conflict_rejected(repo, monkeypatch):
    monkeypatch.setattr("gitdraft.gitio._git", lambda *a, **kw: "UU file.py\0")
    with pytest.raises(DraftError, match="충돌"):
        collect_changes(repo)


def test_git_timeout_has_safe_error(repo, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 30, stderr="private-content")
    monkeypatch.setattr("gitdraft.gitio.subprocess.run", timeout)
    with pytest.raises(DraftError, match="시간이 초과"):
        collect_changes(repo)


def test_timeout_reaches_every_git_command(repo, monkeypatch):
    (repo / "sample.py").write_text("print('hello')\n")
    calls = []
    original = subprocess.run
    def run(*args, **kwargs):
        calls.append(kwargs["timeout"])
        return original(*args, **kwargs)
    monkeypatch.setattr("gitdraft.gitio.subprocess.run", run)
    assert collect_changes(repo, timeout=7.5).diff
    assert len(calls) >= 2
    assert all(value == 7.5 for value in calls)


def test_single_long_line_is_limited():
    text, truncated = limit_diff("a" * 50_000, True)
    assert truncated and len(text) == 40_000


def test_assignment_redaction():
    assert "private-value" not in redact('+api_key = "private-value"')
