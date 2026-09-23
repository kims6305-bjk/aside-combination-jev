"""Fail-closed state machine for browser and judgment adapters."""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Protocol

from .receipts import INTERNAL_HASH_FIELDS, GENESIS, ReceiptLedger, ReceiptWriteError, contains_secret, fingerprint, verify_receipts

ERROR_RETRYABLE = {
    "AJV_E_REQUEST_INVALID": False,
    "AJV_E_RUN_ID_REUSED": False,
    "AJV_E_GOAL_INEXACT": False,
    "AJV_E_BUDGET_EXHAUSTED": False,
    "AJV_E_OBSERVE_FAILED": True,
    "AJV_E_OBSERVATION_STALE": True,
    "AJV_E_CANDIDATE_NONE": False,
    "AJV_E_TARGET_AMBIGUOUS": False,
    "AJV_E_JEV_UNAVAILABLE": True,
    "AJV_E_JEV_CONTRACT": False,
    "AJV_E_PROBABILITY_INVALID": False,
    "AJV_E_POLICY_DENY": False,
    "AJV_E_HUMAN_REQUIRED": False,
    "AJV_E_INTENT_NOT_DURABLE": True,
    "AJV_E_ACTION_FAILED": True,
    "AJV_E_POSTCONDITION_FAILED": False,
    "AJV_E_COMPLETION_MISMATCH": False,
    "AJV_E_RECEIPT_WRITE": True,
    "AJV_E_RECEIPT_CHAIN": False,
    "AJV_E_SECRET_DETECTED": False,
    "AJV_E_PAID_RETRY_BLOCKED": False,
    "AJV_E_INTERNAL": False,
}
TERMINAL = {"COMPLETED", "DENIED", "NEEDS_HUMAN", "FAILED"}
KNOWN_KINDS = {"navigate", "click", "type", "select", "submit", "wait", "read"}
_ALLOWED_REQUEST_KEYS = {"run_id", "goal", "allowed_actions", "forbidden_actions", "sensitive_classes", "budgets", "browser_context", "metadata", "secret_handles", "dry_run"}
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_VAULT_HANDLE = re.compile(r"^(?:vault|keychain|secret)://[A-Za-z0-9._:/-]{1,240}$")


class BrowserAdapter(Protocol):
    def observe(self, browser_context: dict[str, Any]) -> dict[str, Any]: ...
    def enumerate_candidates(self, observation: dict[str, Any], goal: dict[str, Any]) -> list[dict[str, Any]]: ...
    def execute(self, candidate: dict[str, Any], browser_context: dict[str, Any]) -> Any: ...


class JudgmentAdapter(Protocol):
    def judge(self, observation: dict[str, Any], candidates: list[dict[str, Any]], goal: dict[str, Any]) -> dict[str, Any]: ...


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _completion_rules(goal: dict[str, Any]) -> list[dict[str, Any]]:
    rules = goal.get("completion") if isinstance(goal, dict) else None
    if not isinstance(rules, list) or not rules:
        raise ContractError("AJV_E_GOAL_INEXACT", "goal requires non-empty structured completion rules")
    supported = {"eq", "set_eq", "normalized_eq", "exists", "absent"}
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("path"), str) or rule.get("op") not in supported:
            raise ContractError("AJV_E_GOAL_INEXACT", "completion rule is not exact")
        if rule["op"] not in {"exists", "absent"} and "expected" not in rule:
            raise ContractError("AJV_E_GOAL_INEXACT", "completion rule has no expected value")
    return rules


def _lookup(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        elif isinstance(current, list) and segment.isdigit() and int(segment) < len(current):
            current = current[int(segment)]
        else:
            return False, None
    return True, current


def evaluate_completion(goal: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
    evidence = []
    all_match = True
    for rule in _completion_rules(goal):
        found, observed = _lookup(observation, rule["path"])
        op = rule["op"]
        if op == "exists":
            matched = found
        elif op == "absent":
            matched = not found
        elif op == "eq":
            matched = found and type(observed) is type(rule["expected"]) and observed == rule["expected"]
        elif op == "set_eq":
            try:
                matched = found and set(observed) == set(rule["expected"])
            except (TypeError, ValueError):
                matched = False
        else:
            normalize = lambda item: " ".join(str(item).split()).casefold()
            matched = found and normalize(observed) == normalize(rule["expected"])
        evidence.append({"path": rule["path"], "op": op, "expected": rule.get("expected"), "observed": observed if found else None, "found": found, "matched": matched})
        all_match = all_match and matched
    return {"matched": all_match, "evidence": evidence, "fingerprint": fingerprint(evidence)}


def _normalize_observation(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractError("AJV_E_OBSERVE_FAILED", "adapter returned an invalid observation")
    required = {"captured_at", "location", "title", "elements", "facts", "omissions"}
    if not required.issubset(raw) or not isinstance(raw["elements"], list) or not isinstance(raw["facts"], dict) or not isinstance(raw["omissions"], list):
        raise ContractError("AJV_E_OBSERVE_FAILED", "observation contract is incomplete")
    if contains_secret(raw):
        raise ContractError("AJV_E_SECRET_DETECTED", "untrusted observation crossed the secret boundary")
    clean = dict(raw)
    clean.pop("fingerprint", None)
    clean["fingerprint"] = fingerprint(clean)
    return clean


def _validate_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict) or set(request) - _ALLOWED_REQUEST_KEYS:
        raise ContractError("AJV_E_REQUEST_INVALID", "request has unknown fields or is not an object")
    required = {"run_id", "goal", "allowed_actions", "forbidden_actions", "sensitive_classes", "budgets", "browser_context", "dry_run"}
    if not required.issubset(request) or not _RUN_ID.fullmatch(str(request.get("run_id", ""))):
        raise ContractError("AJV_E_REQUEST_INVALID", "request is missing required fields or has an invalid run_id")
    if not all(isinstance(request.get(key), list) for key in ("allowed_actions", "forbidden_actions", "sensitive_classes")):
        raise ContractError("AJV_E_REQUEST_INVALID", "action policy fields must be arrays")
    if not isinstance(request["browser_context"], dict) or not isinstance(request["dry_run"], bool):
        raise ContractError("AJV_E_REQUEST_INVALID", "browser_context or dry_run has the wrong type")
    handles = request.get("secret_handles", {})
    if not isinstance(handles, dict) or any(not isinstance(value, str) or not _VAULT_HANDLE.fullmatch(value) for value in handles.values()):
        raise ContractError("AJV_E_SECRET_DETECTED", "secret_handles must contain references only")
    untrusted_fields = {key: value for key, value in request.items() if key != "secret_handles"}
    if contains_secret(untrusted_fields):
        raise ContractError("AJV_E_SECRET_DETECTED", "request contains secret material")
    budgets = request["budgets"]
    needed = {"max_actions", "max_jev_calls", "max_elapsed_seconds", "max_paid_cost"}
    if not isinstance(budgets, dict) or not needed.issubset(budgets):
        raise ContractError("AJV_E_REQUEST_INVALID", "budgets are incomplete")
    numeric = [budgets[key] for key in needed]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) or item < 0 for item in numeric):
        raise ContractError("AJV_E_REQUEST_INVALID", "budgets must be finite non-negative numbers")
    if budgets["max_actions"] < 1 or budgets["max_jev_calls"] < 1 or budgets["max_elapsed_seconds"] <= 0:
        raise ContractError("AJV_E_REQUEST_INVALID", "budgets do not permit a bounded run")
    _completion_rules(request["goal"])
    return request


def _validate_candidates(raw: Any, observation: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ContractError("AJV_E_CANDIDATE_NONE", "candidate response is not an array")
    candidates: list[dict[str, Any]] = []
    ids: set[str] = set()
    for candidate in raw:
        required = {"candidate_id", "kind", "target", "value", "declared_effect", "estimated_cost", "source_fingerprint"}
        if not isinstance(candidate, dict) or not required.issubset(candidate):
            raise ContractError("AJV_E_JEV_CONTRACT", "candidate contract is incomplete")
        if candidate["candidate_id"] in ids or candidate["source_fingerprint"] != observation["fingerprint"]:
            raise ContractError("AJV_E_OBSERVATION_STALE", "candidate is duplicate or stale")
        if contains_secret(candidate, trusted_hash_fields=frozenset({"source_fingerprint"})):
            raise ContractError("AJV_E_SECRET_DETECTED", "candidate contains secret material")
        ids.add(candidate["candidate_id"])
        candidates.append(candidate)
    if not candidates:
        raise ContractError("AJV_E_CANDIDATE_NONE", "no candidates available")
    return candidates


def _validate_decision(raw: Any, candidates: list[dict[str, Any]], input_fingerprint: str) -> dict[str, Any]:
    required = {"decision_id", "selected_candidate_id", "allow_recommendation", "confidence", "probabilities", "omitted_mass", "reason_codes", "model_id", "input_fingerprint"}
    if not isinstance(raw, dict) or not required.issubset(raw):
        raise ContractError("AJV_E_JEV_CONTRACT", "judgment contract is incomplete")
    if (
        not isinstance(raw["decision_id"], str)
        or not raw["decision_id"]
        or not isinstance(raw["allow_recommendation"], bool)
        or not isinstance(raw["reason_codes"], list)
        or not all(isinstance(code, str) for code in raw["reason_codes"])
        or not isinstance(raw["model_id"], str)
        or not raw["model_id"]
        or not isinstance(raw["input_fingerprint"], str)
        or (raw["selected_candidate_id"] is not None and not isinstance(raw["selected_candidate_id"], str))
    ):
        raise ContractError("AJV_E_JEV_CONTRACT", "judgment fields have invalid types")
    selected = raw["selected_candidate_id"]
    if selected is not None and selected not in {item["candidate_id"] for item in candidates}:
        raise ContractError("AJV_E_JEV_CONTRACT", "judgment selected an unknown candidate")
    if raw["input_fingerprint"] != input_fingerprint or contains_secret(raw, trusted_hash_fields=frozenset({"input_fingerprint"})):
        raise ContractError("AJV_E_JEV_CONTRACT", "judgment input binding is invalid")
    numbers = [raw["confidence"], raw["omitted_mass"]]
    probabilities = raw["probabilities"]
    if not isinstance(probabilities, dict):
        raise ContractError("AJV_E_PROBABILITY_INVALID", "probabilities are not an object")
    numbers += list(probabilities.values())
    if any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 0 <= number <= 1 for number in numbers):
        raise ContractError("AJV_E_PROBABILITY_INVALID", "probability is missing, non-finite, or out of range")
    if abs(sum(probabilities.values()) + raw["omitted_mass"] - 1.0) > 1e-9:
        raise ContractError("AJV_E_PROBABILITY_INVALID", "probability mass does not sum to one")
    return raw


def _policy(request: dict[str, Any], candidate: dict[str, Any], decision: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    kind = candidate.get("kind")
    risk = candidate.get("risk_class", "unknown")
    target_id = candidate.get("target", {}).get("stable_id") if isinstance(candidate.get("target"), dict) else None
    target_count = sum(1 for item in candidates if isinstance(item.get("target"), dict) and item["target"].get("stable_id") == target_id)
    reasons: list[str] = []
    outcome = "ALLOW"
    if not target_id or target_count != 1:
        raise ContractError("AJV_E_TARGET_AMBIGUOUS", "candidate target is not unique")
    if kind not in KNOWN_KINDS or risk not in {"read_only", "reversible", "sensitive", "unknown"}:
        risk = "unknown"
    if kind in request["forbidden_actions"]:
        outcome, reasons = "DENY", ["forbidden_precedence"]
    elif isinstance(candidate.get("estimated_cost"), bool) or not isinstance(candidate.get("estimated_cost"), (int, float)) or not math.isfinite(candidate["estimated_cost"]) or candidate["estimated_cost"] < 0:
        outcome, reasons = "DENY", ["invalid_cost"]
    elif candidate["estimated_cost"] > request["budgets"]["max_paid_cost"]:
        outcome, reasons = "DENY", ["cost_budget_exceeded"]
    elif kind not in request["allowed_actions"]:
        outcome, reasons = "DENY", ["not_allowed"]
    elif risk in {"sensitive", "unknown"} or risk in request["sensitive_classes"]:
        outcome, reasons = "REQUIRE_HUMAN", ["human_for_sensitive_or_unknown"]
    elif not decision["allow_recommendation"]:
        outcome, reasons = "DENY", ["judgment_did_not_recommend"]
    else:
        reasons = ["explicit_allow", "read_or_reversible"]
    return {"outcome": outcome, "reason_codes": reasons, "matched_rules": reasons, "candidate_fingerprint": fingerprint(candidate), "decision_fingerprint": fingerprint(decision)}


def _existing_result(path: Path) -> dict[str, Any] | None:
    checked = verify_receipts(path)
    if not checked["valid"]:
        return None
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[::-1]:
            record = json.loads(line)
            if record["event_type"] == "terminal_result":
                result = dict(record["payload"]["result"])
                result["receipt_head"] = checked["head_hash"]
                return result
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return None
    return None


def _incomplete_receipt(path: Path, run_id: str) -> tuple[list[str], str] | None:
    """Return verified events for a hash-valid receipt prefix without a terminal."""
    events: list[str] = []
    previous = GENESIS
    try:
        for expected_seq, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            record = json.loads(line)
            required = {"schema_version", "run_id", "seq", "event_type", "recorded_at", "payload", "prev_hash", "record_hash"}
            supplied = record.get("record_hash") if isinstance(record, dict) else None
            unhashed = dict(record)
            unhashed.pop("record_hash", None)
            if (
                set(record) != required
                or not isinstance(supplied, str)
                or record["run_id"] != run_id
                or record["seq"] != expected_seq
                or record["prev_hash"] != previous
                or fingerprint(unhashed) != supplied
                or contains_secret(record["payload"], trusted_hash_fields=INTERNAL_HASH_FIELDS)
                or record["event_type"] == "terminal_result"
            ):
                return None
            previous = supplied
            events.append(record["event_type"])
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
    return (events, previous) if events and events[0] in {"request_accepted", "request_rejected"} else None


def _recovery_result(run_id: str, path: Path, events: list[str], head: str, after: str | None = None) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "NEEDS_HUMAN",
        "final_state": "NEEDS_HUMAN",
        "error_code": "AJV_E_HUMAN_REQUIRED",
        "retryable": False,
        "message": "incomplete prior run requires human review",
        "actions_attempted": events.count("action_attempted"),
        "actions_confirmed": 0,
        "completion": {"matched": False, "evidence": []},
        "before_fingerprint": None,
        "after_fingerprint": after,
        "receipt_path": str(path),
        "receipt_head": head,
        "warnings": ["incomplete_run_not_reexecuted"],
    }


class Harness:
    def __init__(self, browser: BrowserAdapter, judgment: JudgmentAdapter, receipt_dir: str | os.PathLike[str]):
        self.browser = browser
        self.judgment = judgment
        self.receipt_dir = Path(receipt_dir)

    def run(self, raw_request: dict[str, Any]) -> dict[str, Any]:
        run_id = str(raw_request.get("run_id", "invalid")) if isinstance(raw_request, dict) else "invalid"
        if not _RUN_ID.fullmatch(run_id):
            return _bare_error(run_id, "AJV_E_REQUEST_INVALID", "invalid run identifier")
        path = self.receipt_dir / f"{run_id}.jsonl"
        try:
            request = _validate_request(raw_request)
        except ContractError as exc:
            if path.exists():
                return _bare_error(run_id, exc.code, "request rejected before existing run lookup", str(path))
            try:
                ledger = ReceiptLedger(path, run_id)
                ledger.append("request_rejected", {"error_code": exc.code, "message": str(exc)})
                return self._finish(ledger, run_id, "FAILED", "FAILED", exc.code, 0, 0, {"matched": False, "evidence": []}, None, None)
            except (OSError, ReceiptWriteError):
                return _bare_error(run_id, "AJV_E_RECEIPT_WRITE", "cannot persist rejected request", str(path))
        if path.exists():
            prior = _existing_result(path)
            if prior is not None:
                prior["warnings"] = list(prior.get("warnings", [])) + ["run_id_reused_existing_result"]
                return prior
            incomplete = _incomplete_receipt(path, run_id)
            if incomplete is not None:
                events, head = incomplete
                if "action_attempted" in events:
                    try:
                        after = _normalize_observation(self.browser.observe(request["browser_context"]))["fingerprint"]
                    except Exception:
                        after = None
                    return _recovery_result(run_id, path, events, head, after)
                if "intent_durable" in events:
                    return _recovery_result(run_id, path, events, head)
            return _bare_error(run_id, "AJV_E_RECEIPT_CHAIN", "existing run receipt is incomplete or invalid", str(path))
        try:
            ledger = ReceiptLedger(path, run_id)
        except OSError:
            return _bare_error(run_id, "AJV_E_RECEIPT_WRITE", "cannot create receipt", str(path))
        started = time.monotonic()
        actions_attempted = actions_confirmed = jev_calls = 0
        before_fp: str | None = None
        after_fp: str | None = None
        state = "NEW"

        def transition(next_state: str) -> None:
            nonlocal state
            ledger.append("state_transition", {"from": state, "to": next_state})
            state = next_state

        try:
            ledger.append("request_accepted", {"request_fingerprint": fingerprint(request), "dry_run": request["dry_run"]})
            transition("VALIDATED")
            while True:
                if time.monotonic() - started > request["budgets"]["max_elapsed_seconds"]:
                    raise ContractError("AJV_E_BUDGET_EXHAUSTED", "elapsed time budget exhausted")
                try:
                    observation = _normalize_observation(self.browser.observe(request["browser_context"]))
                except ContractError:
                    raise
                except Exception as exc:
                    raise ContractError("AJV_E_OBSERVE_FAILED", "browser observation failed") from exc
                if before_fp is None:
                    before_fp = observation["fingerprint"]
                    transition("OBSERVED")
                    event = "observation_captured"
                else:
                    after_fp = observation["fingerprint"]
                    transition("REOBSERVED")
                    event = "reobservation_captured"
                ledger.append(event, {"observation": observation})
                completion = evaluate_completion(request["goal"], observation)
                if completion["matched"]:
                    if actions_attempted:
                        actions_confirmed += 1
                    transition("VERIFIED")
                    ledger.append("postcondition_verdict" if actions_attempted else "completion_verdict", {"completion": completion})
                    if actions_attempted:
                        ledger.append("completion_verdict", {"completion": completion})
                    transition("COMPLETED")
                    status = "COMPLETED" if actions_attempted else "ALREADY_COMPLETE"
                    return self._finish(ledger, run_id, status, state, None, actions_attempted, actions_confirmed, completion, before_fp, after_fp)
                if actions_attempted:
                    ledger.append("postcondition_verdict", {"completion": completion})
                    transition("VERIFIED")
                    if actions_attempted >= request["budgets"]["max_actions"]:
                        raise ContractError("AJV_E_COMPLETION_MISMATCH", "exact completion did not match within action budget")
                try:
                    candidates = _validate_candidates(self.browser.enumerate_candidates(observation, request["goal"]), observation)
                except ContractError:
                    raise
                except Exception as exc:
                    raise ContractError("AJV_E_CANDIDATE_NONE", "candidate enumeration failed") from exc
                transition("CANDIDATES_READY")
                ledger.append("candidates_enumerated", {"candidates": candidates, "observation_fingerprint": observation["fingerprint"]})
                if jev_calls >= request["budgets"]["max_jev_calls"]:
                    raise ContractError("AJV_E_BUDGET_EXHAUSTED", "judgment call budget exhausted")
                judgment_input_fp = fingerprint({"observation": observation, "candidates": candidates, "goal": request["goal"]})
                try:
                    decision = _validate_decision(self.judgment.judge(observation, candidates, request["goal"]), candidates, judgment_input_fp)
                    jev_calls += 1
                except ContractError:
                    ledger.append("jev_decision_rejected", {"input_fingerprint": judgment_input_fp})
                    raise
                except Exception as exc:
                    jev_calls += 1
                    code = "AJV_E_PAID_RETRY_BLOCKED" if getattr(self.judgment, "paid", True) is not False else "AJV_E_JEV_UNAVAILABLE"
                    raise ContractError(code, "judgment adapter unavailable; automatic paid retry is blocked") from exc
                transition("JUDGED")
                ledger.append("jev_decision_received", {"decision": decision})
                selected_id = decision["selected_candidate_id"]
                if selected_id is None:
                    raise ContractError("AJV_E_CANDIDATE_NONE", "judgment selected no candidate")
                candidate = next(item for item in candidates if item["candidate_id"] == selected_id)
                verdict = _policy(request, candidate, decision, candidates)
                transition("GATED")
                ledger.append("policy_verdict", {"verdict": verdict})
                if verdict["outcome"] == "DENY":
                    transition("DENIED")
                    return self._finish(ledger, run_id, "DENIED", state, "AJV_E_POLICY_DENY", actions_attempted, actions_confirmed, completion, before_fp, after_fp)
                if verdict["outcome"] == "REQUIRE_HUMAN":
                    transition("NEEDS_HUMAN")
                    return self._finish(ledger, run_id, "NEEDS_HUMAN", state, "AJV_E_HUMAN_REQUIRED", actions_attempted, actions_confirmed, completion, before_fp, after_fp)
                if request["dry_run"]:
                    ledger.append("dry_run_skipped", {"candidate_fingerprint": fingerprint(candidate)})
                    transition("VERIFIED")
                    ledger.append("completion_verdict", {"completion": completion, "dry_run": True})
                    return self._finish(ledger, run_id, "DRY_RUN", state, None, 0, 0, completion, before_fp, None)
                intent = {"run_id": run_id, "action_seq": actions_attempted, "candidate": candidate, "candidate_fingerprint": fingerprint(candidate), "source_observation_fingerprint": observation["fingerprint"], "decision_fingerprint": fingerprint(decision), "policy_verdict": verdict, "expected_effect": candidate["declared_effect"], "pre_action_completion": completion}
                try:
                    ledger.append("intent_durable", {"intent": intent, "intent_fingerprint": fingerprint(intent)})
                except ReceiptWriteError as exc:
                    raise ContractError("AJV_E_INTENT_NOT_DURABLE", "intent could not be durably stored") from exc
                transition("INTENT_DURABLE")
                try:
                    self.browser.execute(candidate, request["browser_context"])
                    actions_attempted += 1
                except Exception as exc:
                    actions_attempted += 1
                    raise ContractError("AJV_E_ACTION_FAILED", "browser action failed") from exc
                transition("ACTION_ATTEMPTED")
                ledger.append("action_attempted", {"candidate_fingerprint": fingerprint(candidate), "attempt": actions_attempted})
        except ContractError as exc:
            try:
                if state not in TERMINAL:
                    transition("FAILED")
                return self._finish(ledger, run_id, "FAILED", "FAILED", exc.code, actions_attempted, actions_confirmed, {"matched": False, "evidence": []}, before_fp, after_fp)
            except ReceiptWriteError:
                return _bare_error(run_id, "AJV_E_RECEIPT_WRITE", "receipt append failed", str(path), actions_attempted)
        except ReceiptWriteError:
            return _bare_error(run_id, "AJV_E_RECEIPT_WRITE", "receipt append failed", str(path), actions_attempted)
        except Exception:
            try:
                if state not in TERMINAL:
                    transition("FAILED")
                return self._finish(ledger, run_id, "FAILED", "FAILED", "AJV_E_INTERNAL", actions_attempted, actions_confirmed, {"matched": False, "evidence": []}, before_fp, after_fp)
            except ReceiptWriteError:
                return _bare_error(run_id, "AJV_E_RECEIPT_WRITE", "receipt append failed", str(path), actions_attempted)

    def _finish(self, ledger: ReceiptLedger, run_id: str, status: str, final_state: str, error_code: str | None, attempted: int, confirmed: int, completion: dict[str, Any], before: str | None, after: str | None) -> dict[str, Any]:
        result = {
            "run_id": run_id,
            "status": status,
            "final_state": final_state,
            "error_code": error_code,
            "retryable": ERROR_RETRYABLE.get(error_code, False) if error_code else False,
            "message": "run completed" if error_code is None else "run stopped at a fail-closed boundary",
            "actions_attempted": attempted,
            "actions_confirmed": confirmed,
            "completion": completion,
            "before_fingerprint": before,
            "after_fingerprint": after,
            "receipt_path": str(ledger.path),
            "receipt_head": ledger.head,
            "warnings": [],
        }
        ledger.append("terminal_result", {"result": result})
        verified = verify_receipts(ledger.path)
        result["receipt_head"] = verified["head_hash"]
        if not verified["valid"]:
            result.update({"status": "FAILED", "final_state": "FAILED", "error_code": "AJV_E_RECEIPT_CHAIN", "retryable": False, "message": "terminal receipt verification failed"})
        return result


def _bare_error(run_id: str, code: str, message: str, path: str = "", attempted: int = 0) -> dict[str, Any]:
    return {"run_id": run_id, "status": "FAILED", "final_state": "FAILED", "error_code": code, "retryable": ERROR_RETRYABLE.get(code, False), "message": message, "actions_attempted": attempted, "actions_confirmed": 0, "completion": {"matched": False, "evidence": []}, "before_fingerprint": None, "after_fingerprint": None, "receipt_path": path, "receipt_head": GENESIS, "warnings": []}


def run_safe_browser_task(request: dict[str, Any], browser: BrowserAdapter, judgment: JudgmentAdapter, receipt_dir: str | os.PathLike[str]) -> dict[str, Any]:
    return Harness(browser, judgment, receipt_dir).run(request)


def check_health(receipt_dir: str | os.PathLike[str] | None = None, browser: BrowserAdapter | None = None, judgment: JudgmentAdapter | None = None) -> dict[str, Any]:
    directory = Path(receipt_dir) if receipt_dir else Path(tempfile.gettempdir()) / "aside-jav-health"
    components: dict[str, dict[str, Any]] = {}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f"health-{os.getpid()}-{time.time_ns()}.jsonl"
        ledger = ReceiptLedger(probe, "health")
        ledger.append("request_accepted", {"health": True})
        completion = {"matched": True, "evidence": [], "fingerprint": fingerprint([])}
        ledger.append("completion_verdict", {"completion": completion})
        ledger.append("terminal_result", {"result": {"status": "ALREADY_COMPLETE", "completion": completion, "before_fingerprint": fingerprint({"health": True}), "after_fingerprint": None}})
        good = verify_receipts(probe)
        tampered = probe.read_bytes().replace(b'"health":true', b'"health":false', 1)
        bad_probe = probe.with_suffix(".tampered.jsonl")
        bad_probe.write_bytes(tampered)
        bad = verify_receipts(bad_probe)
        probe.unlink(missing_ok=True)
        bad_probe.unlink(missing_ok=True)
        store_ok = good["valid"] and not bad["valid"]
        components["receipt_store"] = {"ok": store_ok}
        components["offline_verifier"] = {"ok": store_ok, "valid_records_checked": good["records_checked"]}
    except Exception:
        components["receipt_store"] = {"ok": False}
        components["offline_verifier"] = {"ok": False, "valid_records_checked": 0}
    components["package"] = {"ok": True, "version": "0.1.0"}
    components["policy"] = {"ok": True, "default": "fail_closed"}
    components["browser_adapter"] = {"ok": browser is not None, "mode": "configured" if browser else "not_configured"}
    components["jev_adapter"] = {"ok": judgment is not None, "mode": "configured" if judgment else "not_configured"}
    if not components["receipt_store"]["ok"] or not components["policy"]["ok"]:
        status = "unhealthy"
    elif browser is None or judgment is None:
        status = "degraded"
    else:
        status = "healthy"
    return {"status": status, "components": components, "side_effect_actions": 0}
