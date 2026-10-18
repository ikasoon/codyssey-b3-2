import argparse
import asyncio
import math
import os
import sys
from pathlib import Path

from gitdraft.config import PROVIDERS, load_environment, resolve_config
from gitdraft.drafts import CommitDraft, bullet_section, render_commit, render_pr
from gitdraft.errors import DraftError
from gitdraft.generator import RequestStats, generate
from gitdraft.gitio import collect_changes, ensure_root


def temperature_value(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("temperature는 숫자여야 합니다.") from None
    if not math.isfinite(number) or not 0 <= number <= 1:
        raise argparse.ArgumentTypeError("temperature는 0 이상 1 이하의 유한한 수여야 합니다.")
    return number


def token_value(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("max-tokens는 정수여야 합니다.") from None
    if number < 1:
        raise argparse.ArgumentTypeError("max-tokens는 1 이상이어야 합니다.")
    return number


def parser() -> argparse.ArgumentParser:
    options = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    options.add_argument("--provider", choices=PROVIDERS, help="LLM 제공자 (기본: OpenRouter)")
    options.add_argument("--model", "-model", help="모델 이름 (--model 또는 LLM_MODEL 필수, 기본값 없음)")
    options.add_argument("--base-url", help="OpenAI 호환 API 주소")
    options.add_argument("--api-key-env", help="API 키가 들어 있는 환경변수 이름")
    options.add_argument("--temperature", "-temperature", type=temperature_value, help="생성 온도, 0~1 (기본: 0.2)")
    options.add_argument("--max-tokens", "-max-tokens", type=token_value, help="응답 토큰 한도 (기본: 2048)")
    safety = options.add_mutually_exclusive_group()
    safety.add_argument("--safe-mode", "-safe-mode", action="store_true", dest="safe_mode",
                        help="최대 10개 파일·200줄·40,000자 전송 (기본)")
    safety.add_argument("--no-safe-mode", action="store_false", dest="safe_mode",
                        help="전송량 제한 해제 (민감 파일 제외와 마스킹은 유지)")
    result = argparse.ArgumentParser(
        description="Git 변경으로 한국어 커밋 메시지와 PR 초안을 생성합니다.",
        parents=[options], allow_abbrev=False,
    )
    commands = result.add_subparsers(dest="command", required=True)
    for name, description in (("commit", "커밋 메시지 생성"), ("pr", "PR 제목과 본문 생성")):
        commands.add_parser(name, help=description, description=description,
                            parents=[options], allow_abbrev=False)
    return result


def info(message: str) -> None:
    print(f"[INFO] {message}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = vars(parser().parse_args(argv))
    command = args.pop("command")
    safe_mode = args.pop("safe_mode", True)
    stats = RequestStats()
    try:
        os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")
        root = Path.cwd()
        ensure_root(root)
        load_environment(root)
        changes = collect_changes(root, safe_mode=safe_mode)
        if not changes.total_files:
            info("변경 사항이 없습니다. 초안을 생성하지 않고 종료합니다.")
            return 0
        info(f"Git status 수집 완료: {changes.total_files}개 파일 변경, {changes.included_files}개 파일 포함")
        if changes.excluded_files:
            info(f"민감 파일 또는 읽을 수 없는 링크 {changes.excluded_files}개 제외")
        if not changes.diff.strip():
            info("요약할 diff가 없습니다. 제외된 파일이나 하위 모듈 상태를 확인하세요.")
            return 0
        info(f"Git diff 수집 완료: {len(changes.diff.splitlines())}줄")
        if changes.truncated:
            info("안전 모드 제한으로 변경 일부만 전송합니다. 초안의 누락 여부를 검토하세요.")
        config = resolve_config(**args)
        info("AI API 요청 중...")
        draft = asyncio.run(generate(changes, command, config, stats))
        # 모든 형식 검증을 마친 후 출력하여 불완전한 초안이 남지 않게 한다.
        if isinstance(draft, CommitDraft):
            rendered = "--- Commit Message ---\n" + render_commit(draft)
        else:
            title, body = render_pr(draft)
            rendered = f"--- PR Title ---\n{title}\n\n--- PR Body ---\n{body}"
        print(bullet_section("--- Change Summary ---", draft.summary))
        print("\n" + rendered + "\n----------------------")
        return 0
    except DraftError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("[ERROR] 파일 또는 환경 설정을 읽을 수 없습니다. 경로와 권한을 확인하세요.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[ERROR] 사용자가 생성을 중단했습니다.", file=sys.stderr)
        return 130
    finally:
        info(f"API 호출 시도: {stats.attempts}회")
