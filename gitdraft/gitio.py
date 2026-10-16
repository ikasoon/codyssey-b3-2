import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from gitdraft.errors import DraftError
from gitdraft.safety import MAX_FILES, limit_diff, redact, sensitive_path


@dataclass(frozen=True)
class Change:
    status: str
    path: str
    original_path: str | None = None


@dataclass(frozen=True)
class Changes:
    status: str
    diff: str
    total_files: int
    included_files: int
    excluded_files: int = 0
    truncated: bool = False


def ensure_root(root: Path) -> None:
    if not (root / ".git").exists():
        raise DraftError("Git 저장소 루트 디렉토리에서 실행하세요.")


def _git(root: Path, *args: str, diff_exit: bool = False) -> str:
    try:
        result = subprocess.run(
            ["git", "--literal-pathspecs", "-c", "core.quotePath=false", *args],
            cwd=root, stdin=subprocess.DEVNULL, capture_output=True,
            encoding="utf-8", errors="replace", timeout=30,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except FileNotFoundError:
        raise DraftError("Git 실행 파일을 찾을 수 없습니다.") from None
    except subprocess.TimeoutExpired:
        raise DraftError("Git 변경 수집 시간이 초과되었습니다.") from None
    if result.returncode not in ({0, 1} if diff_exit else {0}):
        raise DraftError("Git 변경 수집에 실패했습니다. 저장소 권한과 Git 상태를 확인하세요.")
    return result.stdout


def parse_status(raw: str) -> list[Change]:
    records = iter(raw.rstrip("\0").split("\0")) if raw else iter(())
    changes = []
    for record in records:
        code, path = record[:2], record[3:]
        original = next(records) if any(c in code for c in "RC") else None
        changes.append(Change(code, path, original))
    return changes


def collect_changes(root: Path, *, safe_mode: bool = True) -> Changes:
    ensure_root(root)
    changes = parse_status(_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all"))
    if any(c.status in {"DD", "AU", "UD", "UA", "DU", "AA", "UU"} for c in changes):
        raise DraftError("병합 충돌을 먼저 해결한 뒤 실행하세요.")
    allowed = [c for c in changes if not sensitive_path(c.path)
               and not (c.original_path and sensitive_path(c.original_path))
               and not (c.status == "??" and (root / c.path).is_symlink())]
    selected = allowed[:MAX_FILES] if safe_mode else allowed
    paths = list(dict.fromkeys(p for c in selected if c.status != "??"
                              for p in (c.path, c.original_path) if p))
    options = ("--no-ext-diff", "--no-textconv", "--no-color", "--unified=3")
    patches = []
    if paths:
        for flags, label in ((('--cached',), 'Staged'), ((), 'Unstaged')):
            patch = _git(root, "diff", *options, *flags, "--", *paths)
            if patch:
                patches.append(f"[{label}]\n{patch}")
    for change in selected:
        if change.status == "??":
            patch = _git(root, "diff", *options, "--no-index", "--", os.devnull,
                         change.path, diff_exit=True)
            patches.append(f"[Untracked]\n{patch}")
    diff, truncated = limit_diff(redact("\n".join(patches)), safe_mode)
    status = redact("\n".join(f"{c.status} {c.path!r}" for c in selected))
    return Changes(status, diff, len(changes), len(selected), len(changes) - len(allowed),
                   truncated or len(selected) < len(allowed))
