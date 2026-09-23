# aside-combination-jev

This package is a harness between browser and judgment adapters. It enforces local policy, a durable pre-action intent, reobservation, exact completion, and hash-chained receipts. It does not promise absolute safety; it provides tested invariants at explicit adapter boundaries.

## Install

Use Python 3.10 or newer and run `python -m pip install .`. Then check `python -c "import aside_jav; print(aside_jav.__version__)"`, `aside-jav health`, and `aside-jav verify RECEIPT.jsonl`. Runtime dependencies are limited to the Python standard library.

## Run

Use `aside-jav run REQUEST.json --browser package.module:Browser --judgment package.module:Judgment --receipt-dir RECEIPTS`. Browser objects implement `observe`, `enumerate_candidates`, and `execute`; judgment objects implement `judge`. The default configuration has no adapters and cannot perform an action.

## Health and diagnosis

`aside-jav health` checks the package, receipt store, policy, and verifier self-test without account changes. Missing adapters produce `degraded`; receipt-store or policy failure produces `unhealthy`. Check directory permissions and disk health before recovery.

## Recovery

- After a crash or stale run: verify the receipt. Never automatically rerun a receipt without a terminal event.
- After durable intent with an unknown outcome: require human inspection; do not repeat the action.
- After an action crash: reobserve first. An ambiguous outcome requires human review.
- After receipt write failure or chain damage: preserve the original and investigate using a separate recovery file.
- If browser or judgment is unavailable: only cost-free, side-effect-free observation retries may occur within budget. Paid retries or fallback require separate approval.

## Offline verification

`aside-jav verify PATH` checks JSONL syntax, sequence numbers, the SHA-256 chain, intent-before-action, completion event order, and detectable secret patterns without a network. Canonical records are UTF-8 JSON with sorted keys, no whitespace, preserved non-ASCII Unicode, and no NaN. `record_hash` is lowercase SHA-256 hex over the entire record except `record_hash`. The first `prev_hash` is 64 zeroes.

## Hermes

Register `aside-jav-mcp` as a stdio MCP command. It exposes `run_safe_browser_task`, `check_health`, and `verify_receipts`. The standalone MCP server does not dynamically load host adapters, so its run tool fails closed. Optionally install `hermes-skill/SKILL.md` in a Hermes skill directory.

## Uninstall

Run `python -m pip uninstall aside-combination-jev`. Remove only the optional Hermes skill copy you installed. Receipts are preserved by default. For explicit data purge, first display and inspect the configured receipt path, then have an operator delete that path separately. External secret vaults are never owned or modified by this package.

## Verified scope

Automated tests use fake adapters only; they perform no real account, payment, deletion, or transmission operation. Release reports identify the OS and Python versions actually tested. `pathlib` tests cover Windows path semantics, but this distribution does not claim real-device Windows verification unless a Windows result is published.

한국어 문서: `README.md`.
