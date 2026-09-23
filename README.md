# aside-combination-jev

한국어 안내입니다. 이 패키지는 브라우저 어댑터와 판단 어댑터 사이에서 로컬 정책, 실행 전 durable intent, 재관찰, exact completion, hash-chain receipt를 강제하는 안전 하네스입니다. 보안을 절대 보장하지 않으며, 검증된 불변식과 어댑터 경계만 제공합니다.

## 설치

Python 3.10 이상에서 `python -m pip install .`을 실행합니다. 설치 뒤 `python -c "import aside_jav; print(aside_jav.__version__)"`, `aside-jav health`, `aside-jav verify RECEIPT.jsonl`로 확인합니다. 런타임 의존성은 Python 표준 라이브러리뿐입니다.

## 실행

`aside-jav run REQUEST.json --browser package.module:Browser --judgment package.module:Judgment --receipt-dir RECEIPTS`를 사용합니다. adapter 객체는 `observe`, `enumerate_candidates`, `execute` 및 `judge` 계약을 구현해야 합니다. 기본 구성은 adapter가 없어 실제 action을 허용하지 않습니다.

## Health와 장애 진단

`aside-jav health`는 실제 계정 변경 없이 package, receipt 저장소, policy와 verifier self-check를 수행합니다. adapter 미구성은 `degraded`, receipt 또는 policy 실패는 `unhealthy`입니다. `unhealthy`이면 디렉터리 권한과 디스크 상태를 먼저 확인합니다.

## Recovery

- crash 또는 stale lock: receipt를 offline verify하고 terminal event가 없으면 자동 재실행하지 않습니다.
- durable intent 이후 결과 불명: 대상 상태를 사람이 확인합니다. 같은 action을 다시 보내지 않습니다.
- action 이후 crash: 먼저 재관찰하며, 결과가 불명확하면 human review로 둡니다.
- receipt write 실패나 chain 손상: 원본을 수정하지 말고 별도 복구 파일에서 조사합니다.
- browser/Jev unavailable: 비용 없는 사전 관찰만 budget 안에서 재시도합니다. 유료 retry/fallback은 별도 승인 없이는 금지합니다.

## Offline verification

`aside-jav verify PATH`는 네트워크 없이 JSONL 문법, 순번, SHA-256 hash chain, intent-before-action, 완료 사건 순서와 탐지 가능한 secret 패턴을 검사합니다. Canonical form은 UTF-8 JSON이며 key 정렬, 공백 없음, Unicode 비ASCII 보존, NaN 금지를 적용합니다. `record_hash`는 해당 필드를 제외한 전체 record에 SHA-256을 적용한 lowercase hex입니다. 최초 `prev_hash`는 64개의 `0`입니다.

## Hermes

`aside-jav-mcp`를 stdio MCP command로 등록합니다. `run_safe_browser_task`, `check_health`, `verify_receipts` tool을 노출합니다. MCP 단독 서버는 host adapter를 임의로 로드하지 않으므로 run tool이 fail-closed합니다. `hermes-skill/SKILL.md`를 Hermes skill 디렉터리에 선택적으로 설치할 수 있습니다.

## 제거

`python -m pip uninstall aside-combination-jev`로 package를 제거합니다. Hermes skill은 설치한 사본만 별도로 제거합니다. receipt는 기본 제거 대상이 아닙니다. 데이터를 지우려면 먼저 `aside-jav` 설정에서 receipt 경로를 확인·출력한 뒤 운영자가 별도 명시 삭제해야 합니다. 외부 secret vault는 변경하지 않습니다.

## 검증 범위

자동 시험은 fake adapter만 사용하며 계정, 결제, 삭제, 외부 전송을 수행하지 않습니다. 실제 통과한 OS/Python 조합은 release 시 시험 출력으로 보고합니다. Windows 경로 의미는 `pathlib` 기반 시험으로 다루지만 이 배포에서 실기기 Windows를 검증했다고 주장하지 않습니다.

English documentation: see `README.en.md`.
