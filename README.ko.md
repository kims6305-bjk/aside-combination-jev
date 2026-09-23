# aside-combination-jev

`aside-combination-jev`는 브라우저 동작을 로컬 정책으로 통제하는 하네스입니다. 명시적인 브라우저·판단 어댑터를 fail-closed 상태 기계 뒤에 두고, 동작 전 durable intent 기록, 동작 후 재관찰, 정확한 완료 조건, hash-chain receipt를 강제합니다.

이 패키지는 브라우저 드라이버가 아니며 절대적인 안전을 보장하지 않습니다. 운영자는 두 어댑터, 브라우저 세션, 정책, 민감한 결과의 검토에 책임을 집니다.

## 빠른 시작

Python 3.10 이상이 필요합니다. 소스 checkout에서 다음을 실행합니다.

```sh
python scripts/install.py
aside-jav version
aside-jav health
python scripts/validate_skill.py
```

설치기는 Python 패키지와 `aside-combination-jev`라는 Hermes 스킬 하나를 설치합니다. 스킬 루트는 `HERMES_HOME`에서 찾고, 이 변수가 없으면 현재 사용자의 표준 Hermes 홈을 사용합니다. secret 값은 기록하지 않습니다.

새 설치에서 런타임 어댑터가 없으면 `aside-jav health`는 `degraded`를 반환합니다. 이는 예상된 안전 상태입니다. 다만 receipt 저장소, offline verifier, package, policy 구성 요소는 모두 `ok: true`여야 합니다.

## 수동 운전

고유한 `run_id`, 구조화된 완료 조건, 명시적인 허용·거부 목록, 유한한 budget, secret이 없는 browser context, 명시적인 `dry_run` 값을 가진 UTF-8 요청 파일을 작성합니다. 다음 명령으로 실행합니다.

```sh
aside-jav run REQUEST.json \
  --browser package.module:Browser \
  --judgment package.module:Judgment \
  --receipt-dir RECEIPTS
```

브라우저 객체는 `observe(browser_context)`, `enumerate_candidates(observation, goal)`, `execute(candidate, browser_context)`를 구현해야 합니다. 판단 객체는 `judge(observation, candidates, goal)`을 구현해야 합니다. 어댑터 표기는 `module:object` 형식이며, class는 인수 없이 생성됩니다.

먼저 `"dry_run": true`로 시작합니다. dry run도 관찰, 후보 생성, 판단, policy 적용은 수행하지만 후보를 실행하지 않습니다. 실제 실행에는 새 `run_id`를 사용합니다. 완료된 식별자를 재사용하면 기록된 결과를 반환하고, 불완전하거나 손상된 receipt의 식별자를 재사용하면 fail-closed로 중단합니다.

## Hermes 자동 운전

설치된 스킬은 Hermes가 이 패키지를 언제, 어떻게 호출할지 설명합니다. stdio MCP 서버 `aside-jav-mcp`는 다음 tool을 제공합니다.

- `check_health`: 부작용 없는 package·verifier 검사
- `verify_receipts`: 결정적인 offline receipt 검증
- `run_safe_browser_task`: host가 명시적인 브라우저·판단 어댑터를 연결할 때까지 동작을 거부하는 fail-closed 경계

Hermes MCP 설정 도구로 command를 등록한 뒤 Hermes를 재시작하여 tool을 발견하게 합니다. 단독 MCP process는 임의의 어댑터를 import하지 않습니다. 자동 실행 host는 미리 생성한 어댑터와 함께 Python API `aside_jav.run_safe_browser_task(request, browser, judgment, receipt_dir)`를 호출해야 합니다. 이 경계는 adapter load와 secret 처리를 MCP 요청 밖에 둡니다.

자동 운전도 policy를 약화하지 않습니다. 민감하거나 알 수 없는 동작은 별도 사람 결정을 요구합니다. 거부된 동작은 계속 거부되며, 유료 retry와 fallback은 자동 수행하지 않습니다.

## Health와 복구

동작을 허용하기 전에 `aside-jav health --receipt-dir RECEIPTS`를 실행합니다.

- `healthy`: Python health API에 두 어댑터가 제공되었고 모든 로컬 검사가 통과했습니다.
- `degraded`: 로컬 검사는 통과했지만 하나 이상의 어댑터가 없습니다.
- `unhealthy`: receipt 저장소, verifier self-test 또는 policy 검사가 실패했습니다.

`unhealthy`이면 실행을 중단합니다. 선택한 receipt 디렉터리의 여유 공간과 권한을 검사하고 기존 receipt byte를 보존한 뒤, 별도의 쓰기 가능한 디렉터리에서 health를 다시 실행합니다. receipt를 제자리에서 고치지 않습니다.

Crash 뒤에는 다른 조치보다 run receipt를 먼저 검증합니다. 명확한 terminal result 없이 durable intent가 있으면 대상 상태를 직접 확인하고 동작을 다시 보내지 않습니다. 동작 시도가 있었다면 먼저 재관찰합니다. 결과가 불명확하면 사람 검토 상태로 유지합니다. 브라우저 또는 판단 장애 때는 요청 budget 안에서 비용과 부작용이 없는 관찰만 다시 시도할 수 있습니다.

## Receipt 검증

```sh
aside-jav verify RECEIPTS/RUN_ID.jsonl
```

이 명령은 network를 사용하지 않습니다. JSONL 구조, 정확한 field, run별 sequence, SHA-256 link, intent-before-action 순서, terminal 순서, 탐지 가능한 secret 패턴을 검사합니다. 유효한 결과는 `valid: true`이며 `records_checked`와 `runs_checked`가 모두 0보다 큽니다.

Receipt record는 key가 정렬되고 불필요한 공백이 없으며 비ASCII 문자를 보존하고 NaN을 금지하는 UTF-8 JSON입니다. `record_hash`는 `record_hash` field만 제외한 전체 record의 lowercase SHA-256입니다. 첫 `prev_hash`는 64개의 0입니다.

검증은 기록된 byte의 일관성과 강제된 event 순서를 증명합니다. 어댑터가 외부 상태를 정확히 관찰했다는 사실은 증명하지 않습니다.

## 실제 브라우저 예제

`examples/playwright_live.py`는 `127.0.0.1`에서 띄운 페이지를 대상으로 headless Chromium을 하네스를 거쳐 조작한다. 계정이나 외부 네트워크는 쓰지 않는다. 하네스가 보고한 결과가 아니라 페이지 DOM을 직접 읽어 네 가지를 확인한다: 되돌릴 수 있는 클릭은 완료되고, dry run은 페이지를 바꾸지 않고, 민감한 submit은 클릭 없이 `NEEDS_HUMAN`에서 멈추고, 페이지에 카드번호 형태의 숫자가 있으면 행동 전에 거부된다.

```sh
python -m pip install playwright
python -m playwright install chromium
python examples/playwright_live.py   # LIVE PASS 4/4 출력
```

예제의 판단 adapter는 모델이 아니라 결정적 규칙이다.

## 보안 모델과 제약

- 기본 상태에는 어댑터가 없으므로 동작할 수 없습니다.
- 거부 규칙은 허용 규칙보다 우선합니다.
- 알 수 없는 action kind와 민감하거나 알 수 없는 risk class는 사람 검토가 필요합니다.
- Raw secret은 request, observation, candidate, decision, receipt 경계에서 거부됩니다. API가 허용하는 외부 secret handle만 전달합니다.
- Durable intent는 동작 실행 전에 flush와 동기화를 마칩니다.
- 완료 판정은 새 observation과 구조화된 `eq`, `set_eq`, `normalized_eq`, `exists`, `absent` 규칙을 요구합니다.
- 이 패키지는 신뢰할 수 없는 adapter code를 격리하지 않습니다. 운영체제 격리와 최소 권한을 적용합니다.
- 이 패키지는 browser session, secret store, network, 외부 service를 소유하지 않습니다.
- 자동 시험은 로컬 fake adapter만 사용하며 계정 변경, 결제, 삭제, 외부 전송을 수행하지 않습니다.

## 제거와 rollback

```sh
python scripts/install.py --uninstall
```

제거기는 package와 설치기가 기록한 skill 사본만 제거합니다. 설치 뒤 skill 사본이 변경되었다면 로컬 작업을 지우지 않고 중단합니다. 디렉터리를 검토한 뒤에만 `--force-skill-remove`를 사용합니다. Receipt는 항상 보존되므로 기본 복구 절차는 재설치 후 검사입니다.

```sh
python scripts/install.py
aside-jav verify RECEIPTS/RUN_ID.jsonl
```

Receipt 데이터는 보존·감사 조건을 확인한 운영자가 별도 명시 동작으로만 삭제합니다. 먼저 해석된 대상 경로를 preview하고, 확인 flag가 있을 때만 삭제합니다.

```sh
python scripts/install.py --purge-receipts RECEIPTS
python scripts/install.py --purge-receipts RECEIPTS --confirm-purge
```

## 검증과 개발

Fresh clone에서는 먼저 package를 editable 모드로 개발 도구와 함께 설치합니다. 테스트는 설치된 `aside_jav` package를 호출합니다.

```sh
python -m pip install -e . pytest build
python -m pytest
python -m build
python scripts/validate_skill.py
python scripts/smoke_install.py
```

Validator는 결정적이며 0보다 큰 `checks_run`을 JSON으로 반환합니다. Smoke command는 격리된 환경에서 package 설치, skill 설치, import, health, 비어 있지 않은 receipt, 결정적 검증, 제거, receipt 보존을 확인합니다. Test suite는 CLI/MCP surface와 receipt 변조 탐지도 포함합니다.

## 저작권과 라이선스

Copyright (c) 2026 aside-combination-jev contributors. 이 프로젝트는 MIT License로 배포됩니다. `LICENSE`를 확인하십시오.

English documentation: `README.md`.
