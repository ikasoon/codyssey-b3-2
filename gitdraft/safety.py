import os
import re
from pathlib import PurePosixPath

MAX_FILES = 10
MAX_LINES = 200
MAX_CHARS = 40_000


def sensitive_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        name == ".env" or name.startswith(".env.")
        or name in {"id_rsa", "id_ed25519", "credentials"}
        or name.endswith((".pem", ".key", ".p12", ".pfx"))
        or ".aws" in PurePosixPath(path).parts
    )


def redact(text: str, secrets: tuple[str, ...] = ()) -> str:
    """알려진 자격증명과 기본 토큰·이메일 패턴을 제거한다."""
    values = set(secrets)
    values.update(
        value for name, value in os.environ.items()
        if name.lower().endswith(("api_key", "token", "secret", "password"))
    )
    for value in sorted(values, key=len, reverse=True):
        if value and (value in secrets or len(value) >= 8):
            text = text.replace(value, "[REDACTED]")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    # 코드·로그에 포함된 키 대입의 값 전체를 제거한다.
    text = re.sub(
        r"(?im)((?:api[_-]?key|password|secret|access[_-]?token)[\w\"' ]*\s*[:=]\s*).+$",
        r"\1[REDACTED]", text,
    )
    return text


def limit_diff(text: str, safe_mode: bool) -> tuple[str, bool]:
    if not safe_mode:
        return text, False
    lines = text.splitlines()
    limited = "\n".join(lines[:MAX_LINES])
    truncated = len(lines) > MAX_LINES or len(limited) > MAX_CHARS
    return limited[:MAX_CHARS], truncated
