# aside-combination-jev

`aside-combination-jev` is a local, policy-gated harness for browser actions. It places explicit browser and judgment adapters behind a fail-closed state machine, writes durable pre-action intent, reobserves after every action, checks exact completion rules, and produces hash-chained receipts.

It is not a browser driver or a safety guarantee. The operator supplies both adapters and remains responsible for the account, browser session, policy, and review of sensitive outcomes.

## Quick start

Python 3.10 or newer is required. From a source checkout:

```sh
python scripts/install.py
aside-jav version
aside-jav health
python scripts/validate_skill.py
```

The installer installs the Python package and one Hermes skill named `aside-combination-jev`. It resolves the skill root from `HERMES_HOME`, or from the current user's standard Hermes home when that variable is unset. It never writes secret values.

`aside-jav health` returns `degraded` until both runtime adapters are supplied. That is the expected safe state after a new installation. The receipt store, offline verifier, package, and policy components must still report `ok: true`.

## Manual operation

Create a UTF-8 request file with a unique `run_id`, structured completion rules, explicit allow and deny lists, finite budgets, a browser context containing no secret material, and `dry_run` set explicitly. Then run:

```sh
aside-jav run REQUEST.json \
  --browser package.module:Browser \
  --judgment package.module:Judgment \
  --receipt-dir RECEIPTS
```

The browser object must implement `observe(browser_context)`, `enumerate_candidates(observation, goal)`, and `execute(candidate, browser_context)`. The judgment object must implement `judge(observation, candidates, goal)`. Adapter specifications use `module:object`; classes are instantiated without arguments.

Start with `"dry_run": true`. A dry run still observes, enumerates, judges, and applies policy, but does not execute the candidate. For a real run, use a fresh `run_id`: reusing a completed identifier returns its recorded result, while reusing an incomplete or invalid receipt fails closed.

## Automatic operation with Hermes

The installed skill teaches Hermes when and how to invoke this package. The stdio MCP server can be registered as `aside-jav-mcp` and exposes:

- `check_health`: side-effect-free package and verifier checks;
- `verify_receipts`: deterministic offline receipt verification;
- `run_safe_browser_task`: a fail-closed boundary that refuses to act until a host binds explicit browser and judgment adapters.

Register the command through Hermes MCP configuration tooling, then restart Hermes so it can discover the tools. A standalone MCP process intentionally cannot import arbitrary adapters. An automated action host must call the Python API `aside_jav.run_safe_browser_task(request, browser, judgment, receipt_dir)` with preconstructed adapters. This keeps adapter loading and secret handling outside the MCP request.

Automatic mode does not weaken policy. Sensitive or unknown actions require a separate human decision; denied actions remain denied; paid retries and fallback are not performed automatically.

## Health and recovery

Run `aside-jav health --receipt-dir RECEIPTS` before enabling actions.

- `healthy`: both adapters were supplied to the Python health API and all local checks passed.
- `degraded`: local checks passed but one or both adapters are absent.
- `unhealthy`: the receipt store, verifier self-test, or policy check failed.

If health is unhealthy, stop action execution. Check free space and permissions for the selected receipt directory, preserve existing receipt bytes, and rerun health against a new writable directory. Do not repair a receipt in place.

After a crash, verify the run receipt before doing anything else. If durable intent exists without an unambiguous terminal result, inspect the target state and do not resend the action. After an action attempt, reobserve the target. Keep ambiguous outcomes for human review. Browser or judgment outages may be retried only for cost-free, side-effect-free observation within the request budget.

## Receipt verification

```sh
aside-jav verify RECEIPTS/RUN_ID.jsonl
```

The command performs no network access. It checks JSONL structure, exact fields, per-run sequence numbers, SHA-256 links, intent-before-action ordering, terminal ordering, and detectable secret patterns. A valid result has `valid: true`, `records_checked` greater than zero, and `runs_checked` greater than zero.

Receipt records use UTF-8 JSON with sorted keys, no insignificant whitespace, preserved non-ASCII text, and no NaN values. `record_hash` is lowercase SHA-256 over the full record with only the `record_hash` field omitted. The first `prev_hash` is 64 zeroes.

Verification proves consistency of the recorded bytes and enforced event ordering. It does not prove that an adapter observed the external world correctly.

## Real browser example

`examples/playwright_live.py` drives headless Chromium through the harness against a page served on `127.0.0.1`. It uses no account and no external network. It checks four cases against the page itself, not against what the harness reports: a reversible click completes, a dry run leaves the page unchanged, a sensitive submit stops at `NEEDS_HUMAN` without clicking, and a card-like number in the page is rejected before any action.

```sh
python -m pip install playwright
python -m playwright install chromium
python examples/playwright_live.py   # prints LIVE PASS 4/4
```

The judgment adapter in the example is a deterministic rule, not a model.

## Security model and limits

- The default state has no adapters and cannot perform actions.
- Deny rules take precedence over allow rules.
- Unknown action kinds and sensitive or unknown risk classes require human review.
- Raw secrets are rejected at request, observation, candidate, decision, and receipt boundaries. Pass only external secret handles accepted by the API.
- Durable intent is flushed and synchronized before action execution.
- Completion requires a fresh observation and structured `eq`, `set_eq`, `normalized_eq`, `exists`, or `absent` rules.
- The package does not isolate untrusted adapter code. Run adapters with operating-system isolation and least privilege.
- The package does not own browser sessions, secret stores, networks, or external services.
- Automated tests use local fake adapters and do not perform account changes, payments, deletion, or external transmission.

## Uninstall and rollback

```sh
python scripts/install.py --uninstall
```

The uninstaller removes the package and only the skill copy recorded by the installer. If that copy changed after installation, removal stops instead of deleting local work; use `--force-skill-remove` only after reviewing the directory. Receipts are always preserved. This makes reinstall-and-inspect the default recovery path:

```sh
python scripts/install.py
aside-jav verify RECEIPTS/RUN_ID.jsonl
```

Delete receipt data only as a separate, explicit operator action after retention and audit requirements are satisfied. Preview the resolved target first; deletion occurs only with the confirmation flag:

```sh
python scripts/install.py --purge-receipts RECEIPTS
python scripts/install.py --purge-receipts RECEIPTS --confirm-purge
```

## Validation and development

From a fresh clone, install the package in editable mode with the development tools first; the tests invoke the installed `aside_jav` package.

```sh
python -m pip install -e . pytest build
python -m pytest
python -m build
python scripts/validate_skill.py
python scripts/smoke_install.py
```

The validator is deterministic and returns JSON with a nonzero `checks_run` count. The smoke command creates an isolated environment and verifies package installation, skill installation, import, health, a nonempty receipt, deterministic validation, uninstall, and receipt preservation. The test suite also covers CLI/MCP surfaces and receipt tamper detection.

## Copyright and license

Copyright (c) 2026 aside-combination-jev contributors. The project is released under the MIT License; see `LICENSE`.

Korean documentation: `README.ko.md`.
