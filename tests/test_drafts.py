import pytest
from pydantic import ValidationError

from gitdraft.drafts import CommitDraft, PRDraft, render_commit, render_pr


@pytest.fixture
def commit_data():
    return dict(type="feat", subject="한국어 초안 생성 기능 추가", summary=["초안 기능을 추가했다."],
                as_is=["초안 생성 기능이 없었다."], to_be=["초안을 생성한다."],
                what=["생성 모듈을 추가했다."], why=["반복 작업을 줄이기 위해 필요하다."],
                how=["Pydantic AI를 사용했다.", "테스트 미실행: 초안에서 실행하지 않았다."])


def test_commit_format_and_length(commit_data):
    commit_data["subject"] = "긴 제목 " * 50
    text = render_commit(CommitDraft(**commit_data))
    title = text.splitlines()[0]
    assert title.startswith("feat: ") and len(title) <= 72
    for section in ("As-is", "To-be", "What", "Why", "How"):
        assert f"\n\n{section}\n- " in text


@pytest.mark.parametrize("change", [
    {"type": "feature"}, {"subject": "English only"}, {"what": []},
    {"how": [" "]}, {"as_is": ["English only"]},
])
def test_invalid_commit_rejected(commit_data, change):
    with pytest.raises(ValidationError):
        CommitDraft(**(commit_data | change))


def test_missing_section_rejected(commit_data):
    del commit_data["why"]
    with pytest.raises(ValidationError):
        CommitDraft(**commit_data)


def test_pr_format():
    draft = PRDraft(title="한국어 제목 " * 50, summary=["변경 요약"], why=["변경 배경"],
                    what=["변경 내용"], how_to_test=["테스트 미실행: 실행 방법을 확인한다."])
    title, body = render_pr(draft)
    assert len(title) <= 80
    for section in ("Why", "What", "How to Test"):
        assert f"## {section}\n- " in body


def test_newlines_and_terminal_controls_normalized(commit_data):
    commit_data["subject"] = "새 기능\n추가\x1b"
    draft = CommitDraft(**commit_data)
    assert draft.subject == "새 기능 추가"
