# 한국어 Git 커밋과 PR 초안 생성기

현재 저장소의 변경을 읽어 한국어 변경 요약, 커밋 메시지 또는 PR 제목·본문을 생성하는 CLI다. OpenRouter를 기본으로 사용하고 Pydantic AI를 통해 다른 LLM 제공자로 전환할 수 있다. 생성 결과는 터미널에서 검토하고 복사해 사용한다.

## 설치

Git, [uv](https://docs.astral.sh/uv/getting-started/installation/), [just](https://just.systems/man/en/packages.html)를 설치한 뒤 저장소 루트에서 실행한다.

```sh
just setup
just test
```

uv가 `.python-version`에 지정한 Python 3.12와 `uv.lock`의 의존성으로 `.venv`를 구성한다. Python 3.10 이상을 지원하며 별도의 가상환경 활성화는 필요 없다. Pydantic AI는 필요한 제공자만 포함하는 `pydantic-ai-slim[openrouter,openai,anthropic]` 배포판을 사용한다.

## API 키 설정

루트 `.env`에 다음 항목을 설정한다. 기존 파일이 없으면 `.env.example`을 복사해서 시작할 수 있다.

```dotenv
openrouter_api_key=발급받은_OpenRouter_API_키
```

변수 이름은 소문자 `openrouter_api_key`다. `.env`는 애플리케이션 시작 시 읽으며, 이미 설정된 셸 환경변수가 우선한다. 키는 코드나 CLI 인자로 입력하지 않는다. `.env`는 Git 제외 대상이다.

## 실행

```sh
just commit
just pr
just commit --model openai/gpt-4.1-mini --temperature 0.2 --max-tokens 2048
just pr --safe-mode
```

같은 명령을 Python 진입점으로도 실행할 수 있다.

```sh
just run python main.py commit
uv run --locked python main.py pr
just commit --help
```

반드시 Git 저장소 루트에서 실행한다. 스테이징된 변경, 아직 스테이징하지 않은 변경, Git이 무시하지 않는 새 파일을 함께 수집한다. `git status`와 `git diff`만 사용하며 새 파일은 `git diff --no-index`로 읽는다. 인덱스와 작업 파일은 수정하지 않는다. 병합 충돌이 있으면 먼저 해결해야 한다.

변경이 없거나 제외 후 요약할 diff가 없으면 API 호출 없이 종료한다. 성공·변경 없음은 종료 코드 `0`, 설정·Git·API·출력 검증 오류는 `1`, 잘못된 CLI 인자는 `2`, 사용자 중단은 `130`이다. 초안은 표준 출력, 상태·오류·호출 횟수는 표준 오류로 출력한다.

| 옵션 | 기본값과 의미 |
| --- | --- |
| `--provider` | `openrouter`; 제공자 선택 |
| `--model` | OpenRouter는 `openai/gpt-4.1-mini`; 다른 제공자는 명시 필요 |
| `--temperature` | `0.2`; 제공자 공통 범위인 `0`~`1` |
| `--max-tokens` | `2048`; 응답 토큰 상한 |
| `--base-url` | OpenAI 호환 제공자의 API 주소 |
| `--api-key-env` | 키가 들어 있는 환경변수 **이름** |
| `--safe-mode` | 기본 활성화; 입력량 제한 |
| `--no-safe-mode` | 입력량 제한 해제 |

옵션은 `commit`·`pr` 앞이나 뒤에 사용할 수 있다. 과제 예시의 `-model`, `-temperature`, `-max-tokens`, `-safe-mode` 표기도 지원한다.

## LLM 제공자 변경

제공자와 모델 설정은 `CLI 옵션 > 환경변수 또는 .env > 기본값` 순서로 적용한다.

| 제공자 | 기본 키 변수 | 추가 설정 |
| --- | --- | --- |
| `openrouter` | `openrouter_api_key` | 모델 변경 시 OpenRouter 모델 ID 사용 |
| `openai-compatible` | `LLM_API_KEY` | `--model`, `--base-url` 필수 |
| `anthropic` | `ANTHROPIC_API_KEY` | `--model` 필수 |

```sh
# .env에 LLM_API_KEY를 먼저 설정한다.
just commit --provider openai-compatible --base-url https://your-provider.example/v1 --model YOUR_MODEL_ID

# .env에 ANTHROPIC_API_KEY를 먼저 설정한다.
just pr --provider anthropic --model YOUR_ANTHROPIC_MODEL_ID

# 다른 키 변수 이름을 사용하려면 이름만 전달한다.
just commit --api-key-env MY_OPENROUTER_KEY
```

`LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY_ENV`로 같은 설정을 저장할 수 있다. 제공자를 바꿀 때 해당 제공자의 모델 ID와 키 변수를 지정한다. `LLM_BASE_URL`은 `openai-compatible`에서만 사용하므로 다른 제공자로 전환할 때 제거한다. 기본 OpenRouter 키를 다른 제공자에게 자동으로 전달하지 않는다.

호환 API는 HTTPS 주소를 사용한다. 로컬 서버는 `http://localhost:11434/v1`처럼 HTTP를 사용할 수 있으며, 인증이 없는 서버도 SDK 초기화를 위해 `LLM_API_KEY=local` 같은 빈 값이 아닌 값을 설정한다. 해당 모델이 지시를 따르고 JSON 형식의 한국어 응답을 생성할 수 있어야 한다.

제공자별 SDK 생성과 인증은 `gitdraft/providers.py`, 생성 프롬프트와 출력 검증은 별도 모듈에 있다. 새 프로토콜을 추가할 때는 설정의 제공자 목록·키 매핑과 `model_session`을 확장하고 나머지 생성 흐름을 재사용한다. [Pydantic AI 제공자 구조](https://pydantic.dev/docs/ai/models/overview/)와 [OpenRouter 연동](https://pydantic.dev/docs/ai/models/openrouter/)을 따른다.

## 출력 예시

다음은 인사 함수를 추가했을 때의 축약 예시다.

```text
--- Change Summary ---
- greeting.py에 이름을 받아 인사말을 반환하는 함수를 추가했다.

--- Commit Message ---
feat: 이름을 받는 인사 함수 추가

As-is
- 인사 함수가 없었다.

To-be
- 이름을 받아 한국어 인사말을 반환한다.

What
- greeting.py에 greet 함수를 추가했다.

Why
- 인사말 생성을 재사용하려는 변경으로 추정된다.

How
- 문자열 포매팅으로 인사말을 구성했다.
- 테스트 미실행: 초안 생성 과정에서 실행하지 않음.
- greet('철수')의 반환값을 수동으로 확인한다.
----------------------
```

커밋 제목은 `<영문 종류>: <한국어 요약>`이며 50자 이내를 권장하고 최대 72자로 후처리한다. 본문은 `As-is`, `To-be`, `What`, `Why`, `How`를 모두 포함한다.

```text
--- PR Title ---
이름을 받는 인사 함수 추가

--- PR Body ---
## Why
- 인사말 생성을 재사용하려는 변경으로 추정된다.

## What
- greeting.py에 greet 함수를 추가했다.

## How to Test
- 테스트 미실행: 초안 생성 과정에서 실행하지 않음.
- greet('철수')가 한국어 인사말을 반환하는지 확인한다.
----------------------
```

PR 제목은 최대 80자이며 세 본문 섹션에 각각 하나 이상의 불릿을 포함한다. 잘못된 구조나 한국어 설명 누락은 검증 오류로 종료하고, 긴 제목은 생략 부호로 줄인다. diff만으로 배경과 테스트 결과를 확정할 수 없으므로 생성된 문구와 제안된 테스트 명령을 검토한다.

## 안전 모드와 비용

기본 안전 모드는 최대 **10개 파일, diff 200줄, 40,000자**만 전송한다. 잘린 입력은 로그와 프롬프트에 표시한다. 전송 순서는 Git 상태와 패치 순서를 따르므로 큰 변경에서는 일부 파일의 내용이 빠질 수 있다.

`.env`, `.env.*`, 개인 키 파일 등은 항상 제외하며, 알려진 환경변수의 키, 기본 토큰 패턴과 이메일은 마스킹한다. 새 심볼릭 링크는 외부 파일을 읽지 않도록 제외한다. `--no-safe-mode`는 전송량 제한만 해제한다. 패턴 기반 마스킹이 모든 개인정보나 비밀을 찾는 것은 아니므로 실행 전 변경 내용을 검토한다.

명령당 LLM 요청은 최대 **1회**다. SDK와 Agent의 자동 재시도는 꺼져 있고 호출 시도 횟수를 로그로 남긴다. 실패한 요청도 과금될 수 있으며 다시 실행하면 새 요청이다. 모델과 입력량에 따라 비용이 달라진다. 이 프로그램은 커밋, push, 원격 PR 생성을 실행하지 않는다.

## 오류 대응

- 키 누락: 선택한 제공자의 키 변수와 `.env` 위치를 확인한다.
- HTTP 401·403: 키의 유효성과 API 접근 권한을 확인한다.
- HTTP 402·429: 잔액이나 요청 한도를 확인한다.
- 연결 실패·시간 초과: 네트워크, API 주소와 제공자 상태를 확인한다.
- 응답 형식 오류: 모델의 한국어·JSON 출력 지원을 확인하고 `--max-tokens`를 늘려 재실행한다.

키, API 오류 응답 본문과 원본 diff는 오류 로그에 출력하지 않는다.

## 개발과 검증

```sh
just test                 # 실제 LLM 호출 없이 전체 pytest 실행
just test -q              # 간단한 테스트 결과
just check                # 의존성 선언과 uv.lock 일치 검사
just add PACKAGE          # 실행 의존성 추가
just add --dev PACKAGE    # 개발 의존성 추가
```

소스는 `gitdraft/`, 진입점은 `main.py`, 테스트는 `tests/`에 있다. 테스트는 임시 Git 저장소와 Pydantic AI `FunctionModel`을 사용하며 실제 모델 요청을 차단한다. 기본 요구사항은 `docs/assignment.md`, 기여 규칙은 `AGENTS.md`를 참고한다. 보너스 과제의 다른 저장소 PR 제출, 사용자 정의 템플릿과 안전 정책 설정은 포함하지 않는다.
