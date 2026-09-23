# aside-combination-jev Black-Box Specification

한국어 정본 / English clauses are normative where marked **MUST**, **MUST NOT**, **SHOULD**, or **MAY**.

## 1. 문서 목적과 clean-room 선언

이 문서는 Python import 이름이 `aside_jav`인 `aside-combination-jev` 제품의 외부 관찰 가능 동작만 정의한다. 구현자는 이 문서만으로 호환 구현을 만들 수 있어야 한다. 이 문서는 구현 코드, 내부 파일 구조, 내부 함수명, 특정 알고리즘을 규정하지 않는다.

작성 경계:

- 작성자는 이 카드에 주어진 요구사항만 입력으로 사용했다.
- 금지된 기존 프로젝트 디렉터리, 기존 clone, upstream 저장소, 기존 소스·테스트·문서·스킬을 열거나 검색하거나 복사하거나 인용하지 않았다.
- 아래 이름, 계약, 상태, 오류, 시험 문구는 이 명세를 위해 새로 정의한 독립 표현이다.
- 호환성의 기준은 내부 구조가 아니라 이 문서의 외부 입출력과 관찰 가능한 안전 속성이다.

## 2. 제품 범위

`aside-combination-jev`는 브라우저 자동화 시스템과 Jev 판단 서비스 사이에 놓이는 안전 하네스다. 한 작업은 다음 순서를 따른다.

1. 브라우저 상태 관찰
2. 실행 가능한 후보 수집
3. Jev 판단 요청 및 응답 수신
4. 로컬 정책 게이트 적용
5. 실행 전 intent 영속 기록
6. 정확히 한 번의 허용 행동 실행 시도
7. 브라우저 재관찰
8. 완료 조건의 exact 재검증
9. append-only receipt 기록 및 종료

하네스는 브라우저 엔진 또는 Jev 모델 자체가 아니다. 실제 브라우저와 Jev 연결은 어댑터 경계 밖에 있으며, 하네스는 그 입출력을 검증하고 실행 순서를 강제한다.

비목표:

- 범용 자율 에이전트
- CAPTCHA 우회, 인증 우회 또는 접근통제 회피
- 결제·구매·유료 API 사용의 자동 승인
- 비밀값 저장소
- 성공할 때까지 무제한 retry 또는 다른 유료 공급자로의 자동 fallback

## 3. 규범 용어

- **run**: 하나의 사용자 목표를 처리하는 격리된 실행 단위
- **observation**: 특정 시점 브라우저 상태의 정규화된 외부 표현
- **candidate**: 브라우저 어댑터가 실행 가능하다고 제시한 행동
- **decision**: Jev가 후보에 대해 반환한 선택과 불확실성 정보
- **policy verdict**: 로컬 정책 게이트의 최종 허용·거부 결과
- **intent**: 실제 행동 전에 영속 저장되는 실행 계획
- **receipt**: run의 관찰 가능한 사건을 순서대로 기록한 JSON 객체
- **fingerprint**: 원문을 복원하지 않고 동일성 또는 변화를 비교하기 위한 결정적 digest
- **secret**: 비밀번호, 세션 토큰, 인증 코드, 결제정보, 개인 키 또는 호출자가 secret으로 표시한 값
- **sensitive action**: 금전, 계정 권한, 외부 전송, 삭제, 공개, 설치, 보안 설정 또는 되돌리기 어려운 상태를 바꾸는 행동
- **exact completion**: 목표별 사전 선언된 필드와 값이 재관찰 결과에 정확히 일치하는 상태

## 4. 호환 구현의 공개 표면

호환 구현은 최소한 다음 진입점을 제공해야 한다.

### 4.1 Python package

- `import aside_jav`가 설치 후 성공해야 한다.
- package는 기계 판독 가능한 버전 문자열을 노출해야 한다.
- package는 run 요청을 받아 최종 결과를 반환하는 공개 callable 하나 이상을 제공해야 한다.
- callable 이름과 내부 객체 모델은 구현 자유다. 단, §5의 요청·결과 계약을 의미 손실 없이 수용·반환해야 한다.

### 4.2 CLI

다음 의미의 명령을 제공해야 한다. 실제 플래그 철자는 구현 자유지만 `--help`에서 대응 관계가 명확해야 한다.

- run 실행
- health 점검
- receipt offline verify
- version 출력

CLI는 성공 시 exit code `0`, 계약·정책·검증 실패 시 non-zero를 반환해야 한다. 오류의 표준 출력은 JSON 또는 JSON Lines로 선택할 수 있으나 `error_code`, `message`, `retryable`을 포함해야 한다.

### 4.3 Hermes MCP

Hermes에서 호출 가능한 MCP tool은 최소한 다음 의미를 제공해야 한다.

- `run_safe_browser_task`: run 요청 제출
- `check_health`: 의존 경계의 준비 상태 확인
- `verify_receipts`: 네트워크 없이 receipt 파일 검증

MCP 입력 스키마는 §5 요청 계약보다 권한을 넓혀서는 안 된다. MCP 결과는 §5 결과 계약을 보존해야 한다.

### 4.4 Hermes skill

배포물은 한국어와 영어 트리거를 포함한 Hermes skill 설명을 제공해야 한다.

한국어 예시 의미: "Aside 브라우저 작업을 Jev 판단과 안전 정책으로 실행·검증할 때 사용"

English example meaning: "Use for policy-gated Aside browser actions with Jev judgment and verifiable receipts."

skill은 하네스가 결제, 비밀 입력 또는 민감 행동을 자동 승인한다고 표현해서는 안 된다.

## 5. 외부 입출력 계약

### 5.1 RunRequest

run 요청은 아래 필드를 가져야 한다.

| 필드 | 형식 | 필수 | 규칙 |
|---|---|---:|---|
| `run_id` | string | 예 | 호출자가 생성한 고유 ID. 재사용 시 새 실행 금지 |
| `goal` | object | 예 | 목표 종류와 exact completion 조건 포함 |
| `allowed_actions` | array[string] | 예 | 빈 배열이면 실행 없이 거부 |
| `forbidden_actions` | array[string] | 예 | allow보다 우선 |
| `sensitive_classes` | array[string] | 예 | 호출자가 민감으로 지정한 분류 |
| `budgets` | object | 예 | 최대 행동 수, 최대 Jev 호출 수, 최대 경과시간, 최대 유료비용 |
| `browser_context` | object | 예 | 브라우저 어댑터가 이해하는 비밀 없는 연결 정보 |
| `metadata` | object | 아니오 | secret이 아닌 추적 정보만 허용 |
| `secret_handles` | object | 아니오 | 비밀 원문이 아닌 외부 vault handle만 허용 |
| `dry_run` | boolean | 예 | `true`면 실제 행동 실행 금지 |

추가 규칙:

- 알 수 없는 최상위 필드는 기본적으로 거부해야 한다. 명시적 forward-compatible 모드가 있더라도 보안 관련 필드는 무시해서는 안 된다.
- `goal`은 완료를 판정할 관찰 경로, 비교 연산, 기대값을 포함해야 한다.
- 완료 조건이 모호하거나 자유서술뿐이면 실행을 시작해서는 안 된다.
- `budgets.max_actions`는 1 이상이어야 한다. 각 행동 사이에 반드시 재관찰과 완료 검증을 수행한다.
- 유료비용 한도가 0이면 비용 발생 가능 호출 또는 fallback을 수행해서는 안 된다.

### 5.2 Observation

브라우저 어댑터의 관찰 응답은 아래 의미를 제공해야 한다.

| 필드 | 형식 | 설명 |
|---|---|---|
| `captured_at` | RFC 3339 UTC string | 관찰 시각 |
| `location` | string | 현재 URL 또는 동등한 위치 식별자. fragment와 secret query는 제거 가능 |
| `title` | string/null | 페이지 제목 |
| `elements` | array[object] | 상호작용 가능한 요소의 안정 식별자, 역할, 표시 텍스트 요약, 상태 |
| `facts` | object | 완료 판정에 사용할 구조화된 값 |
| `omissions` | array[object] | 생략한 영역과 생략 이유·규모 |
| `fingerprint` | string | 정규화 observation의 digest |

관찰 데이터는 비밀번호 입력값, 토큰, 쿠키, 인증 헤더, 결제번호 전체를 포함해서는 안 된다. secret input은 존재 여부와 handle 식별자만 표현할 수 있다.

### 5.3 CandidateAction

후보는 최소한 다음 필드를 갖는다.

| 필드 | 형식 | 설명 |
|---|---|---|
| `candidate_id` | string | observation 안에서 고유 |
| `kind` | enum | `navigate`, `click`, `type`, `select`, `submit`, `wait`, `read` 또는 명시적 확장값 |
| `target` | object | 안정 식별자와 사람이 읽을 수 있는 요약 |
| `value` | any/null | 비밀 원문 금지. secret은 handle 참조만 허용 |
| `declared_effect` | string | 예상되는 외부 상태 변화 |
| `risk_class` | enum | `read_only`, `reversible`, `sensitive`, `unknown` |
| `estimated_cost` | number | 비용 단위와 함께 사용 |
| `source_fingerprint` | string | 후보를 만든 observation fingerprint |

후보의 target이 현재 observation에서 유일하게 확인되지 않으면 실행해서는 안 된다.

### 5.4 JevDecision

Jev 응답은 최소한 다음 필드를 갖는다.

| 필드 | 형식 | 규칙 |
|---|---|---|
| `decision_id` | string | run 내 고유 |
| `selected_candidate_id` | string/null | 후보 목록 안의 ID 또는 null |
| `allow_recommendation` | boolean | 로컬 정책 허용을 대체하지 않음 |
| `confidence` | number | 0 이상 1 이하 |
| `probabilities` | object | 가능한 결과별 0..1 값 |
| `omitted_mass` | number | 모델이 열거하지 않은 가능성의 추정량, 0..1 |
| `reason_codes` | array[string] | 자유 텍스트가 아닌 안정 코드 권장 |
| `model_id` | string | alias가 아닌 관찰 가능한 정확 ID |
| `input_fingerprint` | string | 판단 입력 digest |

검증 규칙:

- 모든 확률은 유한수여야 한다.
- `sum(probabilities) + omitted_mass`는 구현이 선언한 작은 수치 허용오차 안에서 1이어야 한다.
- confidence, 확률, 생략량이 없거나 범위를 벗어나면 미분류 판단으로 취급하고 fail-closed한다.
- selected ID가 후보 집합에 없으면 계약 실패다.

### 5.5 PolicyVerdict

정책 게이트 결과는 다음을 포함해야 한다.

- `outcome`: `ALLOW`, `DENY`, `REQUIRE_HUMAN`
- `reason_codes`: 하나 이상의 안정 오류·정책 코드
- `matched_rules`: 사람이 감사 가능한 정책 식별자 목록
- `candidate_fingerprint`
- `decision_fingerprint`

강제 규칙:

1. `sensitive` 또는 `unknown` 후보는 자동 실행 금지다.
2. 분류 필드가 없거나 새 enum 값이면 `unknown`으로 취급한다.
3. forbidden과 allowed가 충돌하면 forbidden이 우선한다.
4. Jev의 allow 추천은 로컬 정책 거부를 뒤집을 수 없다.
5. `dry_run=true`이면 outcome이 ALLOW여도 실행하지 않는다.
6. 유료 retry 또는 유료 fallback은 별도 인간 승인 토큰 없이는 금지한다.
7. confidence 임계만으로 민감 행동을 허용해서는 안 된다.

### 5.6 Intent record

실제 브라우저 action 호출 전에 다음 내용이 안정 저장소에 durable하게 기록되어야 한다.

- run ID와 순번
- 선택 후보의 비밀 제거 표현과 fingerprint
- source observation fingerprint
- Jev decision fingerprint
- policy verdict와 matched rules
- 예상 effect
- pre-action completion 평가 결과
- timestamp

저장이 성공했다는 운영체제 수준 확인 없이 action을 호출해서는 안 된다. 저장 실패 후 메모리 기록만으로 계속 진행해서는 안 된다.

### 5.7 RunResult

최종 결과는 아래 필드를 포함해야 한다.

| 필드 | 형식 | 설명 |
|---|---|---|
| `run_id` | string | 요청 ID |
| `status` | enum | `COMPLETED`, `DENIED`, `NEEDS_HUMAN`, `FAILED`, `DRY_RUN`, `ALREADY_COMPLETE` |
| `final_state` | string | §6 상태 |
| `error_code` | string/null | §7 코드 |
| `actions_attempted` | integer | 실제 어댑터 호출 횟수 |
| `actions_confirmed` | integer | exact postcondition으로 확인된 횟수 |
| `completion` | object | 기대값, 관찰값, 비교 결과 |
| `before_fingerprint` | string | 첫 observation digest |
| `after_fingerprint` | string/null | 최종 observation digest |
| `receipt_path` | string | receipt 위치 |
| `receipt_head` | string | 최종 hash |
| `warnings` | array[string] | 비차단 정보 |

`COMPLETED`는 최종 재관찰에서 exact completion이 참이고 receipt chain이 즉시 검증될 때만 반환할 수 있다. action 호출 성공만으로 완료를 반환해서는 안 된다.

## 6. 상태기계

### 6.1 상태

| 상태 | 의미 |
|---|---|
| `NEW` | 요청 수신 전후, 검증 미완료 |
| `VALIDATED` | 요청 스키마와 budget 검증 완료 |
| `OBSERVED` | 현재 브라우저 상태와 before fingerprint 확보 |
| `CANDIDATES_READY` | 현재 observation에 결박된 후보 확보 |
| `JUDGED` | Jev 응답 검증 완료 |
| `GATED` | 로컬 policy verdict 확정 |
| `INTENT_DURABLE` | 실행 전 intent 영속 기록 완료 |
| `ACTION_ATTEMPTED` | 브라우저 어댑터에 정확히 한 action 전달 |
| `REOBSERVED` | action 이후 새 observation 확보 |
| `VERIFIED` | exact completion 또는 action postcondition 재검증 완료 |
| `COMPLETED` | 목표 완료와 receipt 검증 성공 |
| `DENIED` | 정책상 실행 거부 |
| `NEEDS_HUMAN` | 인간 승인 없이는 진행 불가 |
| `FAILED` | 계약, 저장, 어댑터, 검증 또는 budget 실패 |

### 6.2 허용 전이

정상 경로:

`NEW → VALIDATED → OBSERVED → CANDIDATES_READY → JUDGED → GATED → INTENT_DURABLE → ACTION_ATTEMPTED → REOBSERVED → VERIFIED`

`VERIFIED`에서 목표가 완료되면 `COMPLETED`, 미완료이며 budget이 남으면 반드시 새 observation에 기반해 `CANDIDATES_READY`로 간다.

단축 경로:

- 최초 observation이 exact completion을 만족: `OBSERVED → VERIFIED → COMPLETED`이며 status는 `ALREADY_COMPLETE`
- policy 거부: `GATED → DENIED`
- 인간 필요: `GATED → NEEDS_HUMAN`
- dry run 허용: `GATED → VERIFIED`이며 action 호출 없이 status `DRY_RUN`
- 어느 상태에서든 복구 불가능 오류 또는 budget 초과: `FAILED`

금지 전이:

- `GATED → ACTION_ATTEMPTED` 직접 전이
- `JUDGED → INTENT_DURABLE` 직접 전이
- `ACTION_ATTEMPTED → COMPLETED` 직접 전이
- 이전 observation의 candidate를 재관찰 후 재사용
- terminal 상태에서 추가 action 실행

각 상태 전이는 receipt 한 건 이상으로 관찰 가능해야 한다.

## 7. 오류 코드

오류는 안정된 `error_code`, 안전한 `message`, `retryable` boolean을 반환해야 한다. message에 secret을 포함해서는 안 된다.

| 코드 | retryable | 의미 |
|---|---:|---|
| `AJV_E_REQUEST_INVALID` | 아니오 | 요청 스키마 또는 필수값 오류 |
| `AJV_E_RUN_ID_REUSED` | 아니오 | 동일 run ID가 이미 terminal 또는 진행 중 |
| `AJV_E_GOAL_INEXACT` | 아니오 | exact completion 정의 불충분 |
| `AJV_E_BUDGET_EXHAUSTED` | 아니오 | 사전 선언 budget 소진 |
| `AJV_E_OBSERVE_FAILED` | 조건부 | 브라우저 관찰 실패 |
| `AJV_E_OBSERVATION_STALE` | 예 | 후보 source와 현재 fingerprint 불일치 |
| `AJV_E_CANDIDATE_NONE` | 아니오 | 허용 가능한 후보 없음 |
| `AJV_E_TARGET_AMBIGUOUS` | 아니오 | 대상이 유일하지 않음 |
| `AJV_E_JEV_UNAVAILABLE` | 조건부 | Jev 호출 불가 |
| `AJV_E_JEV_CONTRACT` | 아니오 | Jev 응답 계약 위반 |
| `AJV_E_PROBABILITY_INVALID` | 아니오 | 확률·생략량 제약 위반 |
| `AJV_E_POLICY_DENY` | 아니오 | 정책 거부 |
| `AJV_E_HUMAN_REQUIRED` | 아니오 | 인간 승인 필요 |
| `AJV_E_INTENT_NOT_DURABLE` | 조건부 | 실행 전 영속 기록 실패 |
| `AJV_E_ACTION_FAILED` | 조건부 | 브라우저 action 호출 실패 |
| `AJV_E_POSTCONDITION_FAILED` | 아니오 | action 후 선언 효과 불일치 |
| `AJV_E_COMPLETION_MISMATCH` | 아니오 | 최종 exact completion 불일치 |
| `AJV_E_RECEIPT_WRITE` | 조건부 | receipt append 또는 sync 실패 |
| `AJV_E_RECEIPT_CHAIN` | 아니오 | hash-chain 검증 실패 |
| `AJV_E_SECRET_DETECTED` | 아니오 | 기록 또는 출력 경계에서 secret 탐지 |
| `AJV_E_PAID_RETRY_BLOCKED` | 아니오 | 승인 없는 유료 retry/fallback 요청 |
| `AJV_E_INTERNAL` | 아니오 | 안전하게 분류되지 않은 내부 실패 |

`retryable=true`는 자동 retry 허가를 뜻하지 않는다. 자동 retry는 요청 budget과 정책이 모두 허용하고 비용이 0이며 행동이 아직 실행되지 않은 경우에만 가능하다.

## 8. Receipt 계약

### 8.1 저장 형식

receipt 저장소는 UTF-8 JSONL append-only 파일이어야 한다. 한 줄은 하나의 완전한 JSON object다. 기존 줄을 수정하거나 삭제해서는 안 된다.

각 record는 최소한 다음을 포함해야 한다.

- `schema_version`
- `run_id`
- `seq`: 0부터 시작해 1씩 증가
- `event_type`
- `recorded_at`: UTC
- `payload`: 비밀 제거된 사건 데이터
- `prev_hash`: 첫 record는 명세된 genesis 값, 이후 직전 record hash
- `record_hash`: 정규화된 현재 record 내용과 `prev_hash`로 계산한 digest

정규화 방식과 digest 알고리즘은 공개 문서에 명시되어야 하며 모든 지원 OS에서 동일 결과가 나와야 한다. 암호학적 hash는 충돌 저항성이 알려진 표준 알고리즘을 사용해야 한다.

### 8.2 필수 사건

최소 사건 종류:

- request accepted 또는 rejected
- observation captured
- candidates enumerated
- Jev decision received 또는 rejected
- policy verdict
- intent durable
- action attempted 또는 dry-run skipped
- reobservation captured
- postcondition verdict
- completion verdict
- terminal result

### 8.3 Offline verifier

offline verifier는 네트워크, 브라우저, Jev 또는 비밀 저장소 없이 다음을 검사해야 한다.

- JSONL 구문
- run별 seq 연속성
- hash-chain 연속성 및 record hash 재계산
- 필수 사건의 순서와 금지 전이
- action attempted 전에 intent durable 존재
- terminal result와 completion verdict 일치
- before/after fingerprint 존재 조건
- record payload 내 금지된 secret 형태의 탐지 가능한 위반

검증 결과는 `valid`, `records_checked`, `runs_checked`, `first_error_line`, `error_code`, `head_hash`를 반환해야 한다. 빈 파일은 성공이 아니라 실패다.

## 9. 보안 경계와 불변식

### 9.1 신뢰 경계

신뢰하지 않는 입력:

- 웹 페이지 텍스트와 DOM
- 브라우저 어댑터가 반환한 후보
- Jev 자유 텍스트와 구조화 응답
- MCP 호출자의 metadata
- 기존 receipt 파일

부분 신뢰 입력:

- 호출자가 선언한 allow/forbid/budget. 형식 검증 후에도 정책 상한을 넘을 수 없다.
- vault handle. 원문 secret이 아니라는 사실만 신뢰하며, 대상 origin과 용도를 실행 시 재검증해야 한다.

하네스가 직접 강제해야 하는 것:

- 상태 전이
- fail-closed 분류
- intent-before-action 순서
- receipt append와 hash chain
- budget
- 비밀 비기록
- post-action 재관찰
- exact completion 재검증

### 9.2 민감·미분류 행동

다음은 최소 sensitive 분류다.

- 구매, 결제, 구독, 송금, 기부
- 계정 생성·삭제, 권한 변경, 보안 설정 변경
- 파일·레코드·메시지 삭제
- 이메일·메시지·게시물·폼의 외부 전송
- 소프트웨어 설치·제거 또는 코드 실행
- 개인정보 공개 또는 다운로드
- 인증 수단 등록·해제

목록에 없고 읽기 전용임을 증명할 수 없는 행동은 `unknown`이다. sensitive와 unknown은 `REQUIRE_HUMAN` 또는 `DENY`만 가능하다.

### 9.3 비밀 입력 미기록

- 하네스는 secret 원문을 request, log, exception, receipt, fingerprint 입력, telemetry에 기록해서는 안 된다.
- secret은 외부 vault handle로만 참조한다.
- secret 입력 후보의 `value`는 handle과 목적만 포함한다.
- 브라우저 어댑터가 secret을 해석하더라도 하네스로 원문을 반환해서는 안 된다.
- redaction 실패 또는 secret 탐지 시 실행을 중단하고 `AJV_E_SECRET_DETECTED`를 반환한다.

### 9.4 유료 retry와 fallback

- 유료 호출 실패 후 다른 유료 모델·브라우저·서비스로 자동 fallback해서는 안 된다.
- 동일 유료 호출의 자동 retry도 금지한다.
- 인간이 대상, 최대 추가 비용, 횟수, 만료시각을 포함한 별도 승인 토큰을 제공한 경우에만 허용할 수 있다.
- 승인 토큰의 내용은 intent와 receipt에 비밀 없이 기록해야 한다.
- 무료이며 부작용 없는 관찰 retry도 budget 안에서만 허용한다.

### 9.5 Fingerprint

최소 fingerprint:

- 최초 observation
- 각 candidate의 source observation
- 선택 candidate
- Jev 입력과 decision
- intent
- action 후 observation
- completion evidence

동일 입력은 지원 OS와 프로세스 재시작 후에도 동일 fingerprint를 만들어야 한다. secret 원문은 fingerprint 입력에서 제외하거나 단방향 외부 참조 식별자로 대체해야 한다.

## 10. 완료 검증

완료 조건은 실행 전에 요청에 고정해야 한다. 비교기는 최소한 다음 의미를 지원해야 한다.

- 구조화 경로의 exact equality
- 집합의 exact equality
- 명시된 정규화 후 문자열 equality
- 존재 또는 부재

부분 문자열 포함, 화면이 "그럴듯함", Jev의 성공 주장만으로 완료를 판정해서는 안 된다.

완료 절차:

1. action 직후 새 observation을 얻는다.
2. before와 after fingerprint를 비교해 변화 여부를 기록한다.
3. 선언한 모든 completion 항목의 기대값과 관찰값을 receipt에 기록한다.
4. 모든 필수 항목이 exact match일 때만 완료한다.
5. 불일치 시 성공으로 보정하지 말고 budget이 남으면 새 관찰 기반의 새 판단 사이클을 시작한다.
6. 최종 terminal receipt를 append한 뒤 즉시 offline verifier와 동등한 chain 검사를 수행한다.

## 11. 동시성·복구·멱등성

- 동일 `run_id`의 동시 실행은 하나만 허용한다.
- 이미 terminal인 run ID를 다시 제출하면 기존 결과 위치를 반환하고 새 action을 실행하지 않는다.
- 프로세스가 `INTENT_DURABLE` 후 `ACTION_ATTEMPTED` 확인 전에 중단되면 자동 재실행해서는 안 된다. 상태는 인간 검토가 필요한 불확정으로 복구한다.
- `ACTION_ATTEMPTED` 후 중단되면 먼저 재관찰하고 exact postcondition을 검사한다. 결과가 명확하지 않으면 재실행하지 않는다.
- 손상되거나 chain이 끊긴 receipt가 있으면 해당 run을 계속하지 않는다.
- 복구는 기존 receipt를 수정하지 않고 recovery 사건을 새 append로 남긴다. 단, chain 자체가 손상된 파일에는 기록을 덧붙여 정상으로 가장해서는 안 되며 별도 복구 파일을 만든다.

## 12. Health 계약

health는 최소 구성요소별 상태를 반환해야 한다.

| 구성요소 | 검사 의미 |
|---|---|
| package | import와 version 노출 성공 |
| receipt_store | 생성·append·sync·read 권한과 작은 self-check 성공 |
| browser_adapter | 연결 가능 및 무부작용 관찰 가능 |
| jev_adapter | 계약 버전 확인. 유료 호출이 필요한 경우 실제 추론 없이 구성만 점검 가능 |
| policy | 정책 로드와 fail-closed 기본값 확인 |
| offline_verifier | 합성 정상 chain은 PASS, 변조 chain은 FAIL |

전체 상태는 `healthy`, `degraded`, `unhealthy` 중 하나다. browser 또는 Jev가 없어도 offline verifier만 실행 가능한 설치는 `degraded`일 수 있다. receipt 저장소 또는 policy가 실패하면 `unhealthy`다.

health는 실제 계정 변경, 메시지 전송, 구매, 삭제를 수행해서는 안 된다.

## 13. 설치·recovery·uninstall

### 13.1 범용 설치

배포물은 가능한 범위에서 macOS, Linux, Windows를 지원해야 한다.

- 표준 Python package 설치 경로를 제공한다.
- OS별 shell에 종속된 절차가 있으면 세 OS별 명령을 분리해 문서화한다.
- 설치 직후 `import aside_jav`, version, health, offline verifier self-check를 실행할 수 있어야 한다.
- 브라우저 또는 Jev credential이 없어도 package 설치와 offline verifier 검증은 가능해야 한다.
- 기본 구성은 실제 action을 허용하지 않는 fail-closed 상태여야 한다.

### 13.2 Recovery

복구 문서는 최소한 다음 상황을 다뤄야 한다.

- process crash
- stale run lock
- intent 이후 결과 불명
- receipt write 실패
- receipt chain 손상
- browser adapter 재연결
- Jev unavailable

복구 절차는 action 중복보다 인간 확인을 우선해야 한다.

### 13.3 Uninstall

- package와 선택적 Hermes integration 제거 절차를 제공한다.
- uninstall은 receipt와 감사 자료를 기본 삭제해서는 안 된다.
- 데이터 삭제는 별도 명시적 명령이어야 하고 삭제 대상 경로를 먼저 출력해야 한다.
- secret vault는 이 제품 소유가 아니므로 제거하거나 변경해서는 안 된다.

## 14. Acceptance tests

아래 시험은 구현 언어 내부가 아니라 공개 표면에서 실행한다. 각 시험은 독립된 임시 저장소와 fake browser/Jev adapter를 사용하며 실제 계정·결제·삭제·전송을 수행하지 않는다.

### A. 설치와 공개 표면

- **AT-001 Package import**: 깨끗한 지원 환경에서 설치 후 `import aside_jav`와 version 조회가 성공한다.
- **AT-002 CLI discoverability**: CLI help에서 run, health, offline verify, version의 대응 명령을 찾을 수 있다.
- **AT-003 MCP schema**: 세 MCP tool의 입력·출력 스키마가 §4.3과 §5를 만족한다.
- **AT-004 Bilingual docs**: 설치, health, recovery, uninstall, Hermes skill 사용법이 한국어와 영어로 제공된다.

### B. 정상 상태기계

- **AT-010 Read-only success**: fake observation에서 유일한 read-only candidate를 Jev가 선택하고 policy가 허용한다. intent receipt가 action adapter 호출보다 먼저 저장되며 재관찰 exact completion 후 `COMPLETED`가 된다.
- **AT-011 Already complete**: 최초 observation이 완료 조건과 일치하면 action 호출 0회, status `ALREADY_COMPLETE`다.
- **AT-012 Multi-step budgeted run**: 두 행동이 필요한 목표에서 각 행동 사이 재관찰·새 candidate·새 judgment가 존재하고 최종 완료한다.
- **AT-013 Dry run**: 허용 후보라도 action 호출은 0회이며 intent 이전 단계의 판단 근거와 `DRY_RUN` terminal receipt가 남는다.

### C. Fail-closed 정책

- **AT-020 Sensitive denied**: 구매 candidate는 Jev confidence 1.0이어도 자동 실행되지 않고 `NEEDS_HUMAN` 또는 `DENIED`다.
- **AT-021 Unknown denied**: 알 수 없는 action kind 또는 risk class는 실행 0회다.
- **AT-022 Conflict precedence**: 같은 행동이 allowed와 forbidden 모두에 있으면 거부된다.
- **AT-023 Missing classification**: risk field가 없으면 계약 실패 또는 unknown 거부다.
- **AT-024 Ambiguous target**: 동일 target 후보가 둘 이상이면 실행하지 않는다.
- **AT-025 Stale observation**: candidate source fingerprint와 현재 observation이 다르면 재판단 전 실행하지 않는다.

### D. Jev 계약과 확률

- **AT-030 Probability recorded**: 정상 decision의 confidence, probabilities, omitted mass, model ID, input fingerprint가 receipt에 남는다.
- **AT-031 Invalid probability**: 음수, NaN, 1 초과 또는 합 제약 위반 응답은 `AJV_E_PROBABILITY_INVALID`로 거부된다.
- **AT-032 Candidate injection**: 존재하지 않는 candidate ID 선택은 `AJV_E_JEV_CONTRACT`이며 action 0회다.
- **AT-033 Missing omission**: omitted mass가 없으면 fail-closed한다.

### E. Durable intent와 receipt

- **AT-040 Intent ordering**: fake store와 action adapter의 호출 순서를 기록해 durable intent 확인이 항상 action보다 앞섬을 assert한다.
- **AT-041 Intent failure**: store sync 실패를 주입하면 action 호출 0회, `AJV_E_INTENT_NOT_DURABLE`이다.
- **AT-042 Append-only**: run 전후 기존 receipt line byte가 바뀌지 않고 새 line만 추가된다.
- **AT-043 Hash chain**: 정상 receipt를 offline verify하면 valid이며 records checked가 1 이상이다.
- **AT-044 Tamper detection**: 중간 한 byte 변경, line 삭제, 순서 교환 각각이 `AJV_E_RECEIPT_CHAIN` 또는 명확한 검증 실패를 낸다.
- **AT-045 Empty ledger fails**: 빈 JSONL은 성공으로 판정되지 않는다.
- **AT-046 Required events**: action이 있는 성공 run은 §8.2 필수 사건을 모두 올바른 순서로 포함한다.

### F. 완료 재검증

- **AT-050 Adapter success is insufficient**: action adapter가 success를 반환해도 postcondition이 불일치하면 `COMPLETED`가 아니다.
- **AT-051 Exact means exact**: 기대값 `submitted`에 관찰값 `not submitted`가 부분 문자열 또는 유사도 때문에 통과하지 않는다.
- **AT-052 Before/after evidence**: action run은 서로 독립적으로 계산 가능한 before/after fingerprint를 반환한다.
- **AT-053 Reobserve required**: action 후 observation 없이 완료하려는 구현은 acceptance 실패다.

### G. Secret과 redaction

- **AT-060 Secret handle only**: secret 입력 run의 request·receipt·log·exception·fingerprint 원자료 어디에도 원문 secret이 없다.
- **AT-061 Secret leak fail**: fake adapter가 observation에 secret marker를 반환하면 redaction하거나 `AJV_E_SECRET_DETECTED`로 중단하며 원문을 기록하지 않는다.
- **AT-062 Error redaction**: 예외 message에 포함된 secret marker가 외부 오류와 receipt에 나타나지 않는다.

### H. Retry·fallback·복구

- **AT-070 Paid retry blocked**: 유료 Jev 실패를 주입해도 승인 토큰 없이 두 번째 유료 호출은 0회이며 `AJV_E_PAID_RETRY_BLOCKED`다.
- **AT-071 Paid fallback blocked**: 1차 유료 provider 실패 후 다른 유료 provider가 자동 호출되지 않는다.
- **AT-072 Free observe retry bounded**: 무료 observation retry는 선언 횟수를 넘지 않는다.
- **AT-073 Crash after intent**: durable intent 직후 crash 상태를 재기동하면 동일 action을 자동 재실행하지 않는다.
- **AT-074 Crash after action**: action 호출 후 terminal receipt 전 crash 상태를 재기동하면 재관찰이 먼저이며 결과가 불명확하면 인간 검토로 간다.
- **AT-075 Run ID idempotency**: terminal run ID 재제출은 action 0회이며 기존 결과를 가리킨다.

### I. Health·uninstall·cross-platform

- **AT-080 Health can fail**: receipt store 쓰기 불가를 주입하면 health가 `unhealthy`이고 exit code가 non-zero다.
- **AT-081 Verifier self-check**: health가 정상 합성 chain PASS와 변조 chain FAIL을 모두 실제 확인한다.
- **AT-082 No side effect health**: health 실행 중 fake action adapter 호출 0회다.
- **AT-083 Uninstall preserves receipts**: 기본 uninstall 후 receipt 데이터가 남는다.
- **AT-084 Explicit purge**: 데이터 삭제는 별도 명시 동작이고 대상 경로를 사전 표시한다.
- **AT-085 Platform path handling**: macOS/Linux/Windows 경로 표현에서 receipt 생성·검증 결과가 동일 의미를 가진다.

### J. Acceptance 판정 규칙

- 실행된 acceptance test 수가 0이면 PASS가 아니다.
- 모든 hard safety test(AT-020~025, AT-031~033, AT-040~046, AT-050~053, AT-060~062, AT-070~075)는 전부 PASS해야 한다.
- OS 미지원은 숨기지 않고 해당 OS 시험을 FAIL 또는 명시적 unsupported로 보고한다. "가능한 범위" 주장은 실제 통과한 OS만 열거한다.
- 시험 결과에는 실행 건수, pass/fail/skip, skip 이유, package version, OS, Python version을 포함한다.

## 15. 구현 자유와 금지 사항

구현자는 다음을 자유롭게 선택할 수 있다.

- 내부 파일·모듈·함수·클래스 구조
- 동기 또는 비동기 실행 모델
- 표준 규격을 만족하는 digest와 정규화 방식
- 브라우저·Jev adapter protocol의 구체적 전송 방식
- CLI framework 및 packaging backend

단, 다음은 허용되지 않는다.

- 이 명세보다 약한 fail-open 기본값
- intent와 action 순서의 교환
- receipt 기존 line 수정
- Jev 판단만으로 sensitive 또는 unknown 자동 실행
- action adapter 성공을 완료로 간주
- secret 원문 기록
- 승인 없는 유료 retry/fallback
- 내부 구현 편의를 이유로 acceptance test의 의미 축소

## 16. 최소 배포 문서 체크리스트

호환 배포는 최소한 다음 문서를 제공해야 한다.

- 한국어 README
- English README
- 설치와 업그레이드
- health와 장애 진단
- crash·불확정 action recovery
- offline receipt verification
- uninstall과 선택적 data purge
- Hermes MCP 등록
- Hermes skill 설치·트리거·권한 한계
- 실제 검증된 OS/Python 조합과 미검증 범위

문서는 "안전"을 절대 보장으로 표현해서는 안 된다. 검증된 불변식, 통과한 시험, 남은 한계를 구분해 보고해야 한다.
