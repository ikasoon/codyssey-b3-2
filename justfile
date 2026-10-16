set positional-arguments

# 사용 가능한 명령 표시
default:
    @just --list

# 잠금 파일 기준으로 .venv 생성 및 의존성 동기화
setup:
    uv sync --locked

# 프로젝트 환경에서 명령 실행: just run python --version
run +args:
    uv run --locked -- "$@"

# 의존성 추가: just add httpx / just add --dev pytest
add +args:
    uv add "$@"

# 의존성 제거: just remove httpx / just remove --dev pytest
remove +args:
    uv remove "$@"

# pyproject.toml 변경 후 잠금 파일 갱신
lock:
    uv lock

# 의존성 선언과 잠금 파일의 일치 여부 확인
check:
    uv lock --check
