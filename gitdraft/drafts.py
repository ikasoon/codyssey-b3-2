import re
import unicodedata
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from gitdraft.errors import DraftError
from gitdraft.policy import COMMIT_TITLE_MAX, PR_TITLE_MAX


def korean_line(value: str) -> str:
    value = " ".join(value.split())
    value = "".join(c for c in value if not unicodedata.category(c).startswith("C"))
    value = value.lstrip("-• ")
    if not re.search(r"[가-힣]", value):
        raise ValueError("설명은 비어 있지 않은 한국어 문장이어야 합니다.")
    return value


KoreanLine = Annotated[str, AfterValidator(korean_line)]
Bullets = Annotated[list[KoreanLine], Field(min_length=1)]
CommitType = Literal["feat", "fix", "docs", "refactor", "test", "build", "ci",
                     "chore", "perf", "style", "revert"]


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: Bullets


class CommitDraft(Draft):
    type: CommitType
    subject: KoreanLine
    as_is: Bullets
    to_be: Bullets
    what: Bullets
    why: Bullets
    how: Bullets


class PRDraft(Draft):
    title: KoreanLine
    why: Bullets
    what: Bullets
    how_to_test: Bullets


def shorten_title(title: str, maximum: int) -> str:
    if len(title) > maximum:
        title = title[:maximum - 1].rstrip() + "…"
    if not re.search(r"[가-힣]", title):
        raise DraftError("제목을 길이 제한에 맞게 줄일 수 없습니다. 한국어 요약으로 다시 생성하세요.")
    return title


def bullet_section(heading: str, items: list[str]) -> str:
    return heading + "\n" + "\n".join(f"- {item}" for item in items)


def render_commit(draft: CommitDraft) -> str:
    title = shorten_title(f"{draft.type}: {draft.subject}", COMMIT_TITLE_MAX)
    sections = [("As-is", draft.as_is), ("To-be", draft.to_be),
                ("What", draft.what), ("Why", draft.why), ("How", draft.how)]
    return title + "\n\n" + "\n\n".join(bullet_section(*section) for section in sections)


def render_pr(draft: PRDraft) -> tuple[str, str]:
    title = shorten_title(draft.title, PR_TITLE_MAX)
    body = "\n\n".join(bullet_section(*section) for section in (
        ("## Why", draft.why), ("## What", draft.what), ("## How to Test", draft.how_to_test),
    ))
    return title, body
