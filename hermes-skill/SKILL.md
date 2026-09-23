---
name: aside-combination-jev
description: Run or review policy-gated browser tasks with explicit adapters, exact completion checks, and offline-verifiable receipts.
version: 0.1.0
license: MIT
metadata:
  hermes:
    tags: [browser, safety, receipts, policy]
---

# aside-combination-jev

Use this skill when a user asks to run, dry-run, diagnose, recover, or verify a browser task through `aside_jav`.

## Safety boundary

- Begin with `aside-jav health`. `degraded` is expected when adapters are not bound; `unhealthy` blocks execution.
- Never place secret values in requests, observations, candidates, decisions, logs, or receipts. Use only an accepted external secret handle.
- Never infer permission. Denied, sensitive, and unknown actions remain stopped for a separate human decision.
- Never automatically repeat an action after durable intent, an action attempt, a crash, or an ambiguous result.
- Never add a paid retry or fallback without separate approval and a revised finite budget.
- Treat adapters as trusted local code. This package does not sandbox them.

## Automatic mode

For Hermes discovery, register the stdio command `aside-jav-mcp`. Use `check_health` and `verify_receipts` directly. The standalone `run_safe_browser_task` MCP tool intentionally refuses to act because it has no host-bound adapters.

An action-capable host must construct browser and judgment adapters itself and call:

`aside_jav.run_safe_browser_task(request, browser, judgment, receipt_dir)`

Do not dynamically import adapter names supplied by a chat message. Start with `dry_run` and require a fresh `run_id` for a real execution.

## Manual mode

1. Run `aside-jav health --receipt-dir RECEIPTS`.
2. Review the request's exact completion rules, allow/deny lists, sensitive classes, finite action/judgment/time/cost budgets, and `dry_run` value.
3. Run `aside-jav run REQUEST.json --browser package.module:Browser --judgment package.module:Judgment --receipt-dir RECEIPTS`.
4. Read the JSON result. `DENIED`, `NEEDS_HUMAN`, and `FAILED` are stopped outcomes, not invitations to bypass policy.
5. Run `aside-jav verify RECEIPTS/RUN_ID.jsonl`. Accept the receipt only when `valid` is true and both checked counts are greater than zero.

## Health and recovery

`healthy` means local checks pass and both adapters are bound. `degraded` means local checks pass but adapters are absent. `unhealthy` means execution must stop.

For an unhealthy receipt store, preserve existing bytes, check free space and permissions, and test a separate writable directory. For a crash or incomplete receipt, verify first, inspect the target state, and do not resend the action. After an action attempt, reobserve. Keep an ambiguous outcome for human review. Never edit a damaged receipt in place.

## Install and uninstall

From the project checkout, `python scripts/install.py` installs the package and this single skill. `python scripts/validate_skill.py` validates the source and installed copies deterministically.

Use `python scripts/install.py --uninstall` to remove the package and the installer-owned skill copy while preserving receipts. If the installed skill was modified, removal stops; review it before using `--force-skill-remove`. Reinstalling the package does not alter existing receipts.

## Receipt meaning

Offline verification checks receipt structure, sequence, SHA-256 links, secret patterns, intent-before-action, and terminal ordering without network access. It proves consistency of recorded bytes, not correctness of an adapter's external observation.
