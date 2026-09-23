from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aside_jav import Harness, __version__, check_health, verify_receipts
from aside_jav.core import evaluate_completion
from aside_jav.mcp import TOOLS, dispatch
from aside_jav.receipts import ReceiptLedger, ReceiptWriteError, fingerprint


def observation(step: int = 0, *, facts=None, extra=None):
    value = {
        "captured_at": "2026-01-01T00:00:00Z",
        "location": "https://example.invalid/task",
        "title": "Fake",
        "elements": [{"stable_id": f"button-{step}", "role": "button", "text": "Continue", "state": "enabled"}],
        "facts": facts if facts is not None else {"status": "pending", "step": step},
        "omissions": [{"region": "canvas", "reason": "not_interactive", "size": 0}],
    }
    if extra:
        value.update(extra)
    return value


def request(run_id="run-1", **changes):
    value = {
        "run_id": run_id,
        "goal": {"kind": "fake", "completion": [{"path": "facts.status", "op": "eq", "expected": "done"}]},
        "allowed_actions": ["click"],
        "forbidden_actions": [],
        "sensitive_classes": [],
        "budgets": {"max_actions": 2, "max_jev_calls": 2, "max_elapsed_seconds": 10, "max_paid_cost": 0},
        "browser_context": {"session": "fake"},
        "metadata": {"trace": "test"},
        "secret_handles": {},
        "dry_run": False,
    }
    value.update(changes)
    return value


class FakeBrowser:
    def __init__(self, done_after=1, risk="read_only", kind="click", duplicate_target=False, stale=False, leak=False, fail_action=False):
        self.step = 0
        self.done_after = done_after
        self.risk = risk
        self.kind = kind
        self.duplicate_target = duplicate_target
        self.stale = stale
        self.leak = leak
        self.fail_action = fail_action
        self.actions = 0
        self.calls = []

    def observe(self, context):
        self.calls.append("observe")
        facts = {"status": "done" if self.step >= self.done_after else "pending", "step": self.step}
        extra = {"token": "Bearer abcdefghijklmnop"} if self.leak else None
        return observation(self.step, facts=facts, extra=extra)

    def enumerate_candidates(self, current, goal):
        self.calls.append("candidates")
        source = "f" * 64 if self.stale else current["fingerprint"]
        item = {
            "candidate_id": f"candidate-{self.step}",
            "kind": self.kind,
            "target": {"stable_id": "same" if self.duplicate_target else f"button-{self.step}", "summary": "Continue"},
            "value": None,
            "declared_effect": "advance fake state",
            "risk_class": self.risk,
            "estimated_cost": 0,
            "source_fingerprint": source,
        }
        if self.duplicate_target:
            other = dict(item)
            other["candidate_id"] = "candidate-other"
            return [item, other]
        return [item]

    def execute(self, candidate, context):
        self.calls.append("execute")
        self.actions += 1
        if self.fail_action:
            raise RuntimeError("adapter contained Bearer abcdefghijklmnop")
        self.step += 1
        return {"accepted": True}


class FakeJudgment:
    def __init__(self, mutation=None, fail=False, paid=True):
        self.calls = 0
        self.mutation = mutation or {}
        self.fail = fail
        self.paid = paid

    def judge(self, current, candidates, goal):
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider failed")
        value = {
            "decision_id": f"decision-{self.calls}",
            "selected_candidate_id": candidates[0]["candidate_id"],
            "allow_recommendation": True,
            "confidence": 0.9,
            "probabilities": {"success": 0.8, "failure": 0.1},
            "omitted_mass": 0.1,
            "reason_codes": ["goal_progress"],
            "model_id": "fake-model-1",
            "input_fingerprint": fingerprint({"observation": current, "candidates": candidates, "goal": goal}),
        }
        value.update(self.mutation)
        return value


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_harness(self, req=None, browser=None, judgment=None):
        browser = browser or FakeBrowser()
        judgment = judgment or FakeJudgment()
        result = Harness(browser, judgment, self.temp.name).run(req or request())
        return result, browser, judgment

    def test_read_only_success_and_order(self):
        result, browser, _ = self.run_harness()
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(browser.actions, 1)
        self.assertTrue(verify_receipts(result["receipt_path"])["valid"])
        events = [json.loads(line)["event_type"] for line in Path(result["receipt_path"]).read_text().splitlines()]
        self.assertLess(events.index("intent_durable"), events.index("action_attempted"))
        self.assertLess(events.index("action_attempted"), events.index("reobservation_captured"))

    def test_already_complete_has_no_action(self):
        result, browser, judgment = self.run_harness(browser=FakeBrowser(done_after=0))
        self.assertEqual(result["status"], "ALREADY_COMPLETE")
        self.assertEqual((browser.actions, judgment.calls), (0, 0))

    def test_two_step_run_rejudges(self):
        result, browser, judgment = self.run_harness(browser=FakeBrowser(done_after=2))
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual((browser.actions, judgment.calls), (2, 2))
        self.assertGreaterEqual(browser.calls.count("observe"), 3)

    def test_dry_run(self):
        result, browser, _ = self.run_harness(req=request(dry_run=True))
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(browser.actions, 0)

    def test_sensitive_needs_human_even_high_confidence(self):
        result, browser, _ = self.run_harness(browser=FakeBrowser(risk="sensitive"))
        self.assertEqual(result["status"], "NEEDS_HUMAN")
        self.assertEqual(browser.actions, 0)

    def test_unknown_kind_needs_human(self):
        result, browser, _ = self.run_harness(browser=FakeBrowser(kind="teleport", risk="new-risk"), req=request(allowed_actions=["teleport"]))
        self.assertEqual(result["status"], "NEEDS_HUMAN")
        self.assertEqual(browser.actions, 0)

    def test_forbidden_precedes_allowed(self):
        result, browser, _ = self.run_harness(req=request(forbidden_actions=["click"]))
        self.assertEqual(result["status"], "DENIED")
        self.assertEqual(browser.actions, 0)

    def test_ambiguous_target_fails(self):
        result, browser, _ = self.run_harness(browser=FakeBrowser(duplicate_target=True))
        self.assertEqual(result["error_code"], "AJV_E_TARGET_AMBIGUOUS")
        self.assertEqual(browser.actions, 0)

    def test_stale_candidate_fails(self):
        result, browser, _ = self.run_harness(browser=FakeBrowser(stale=True))
        self.assertEqual(result["error_code"], "AJV_E_OBSERVATION_STALE")
        self.assertEqual(browser.actions, 0)

    def test_probability_fail_closed_variants(self):
        variants = [
            {"confidence": -0.1},
            {"confidence": float("nan")},
            {"omitted_mass": 1.1},
            {"probabilities": {"success": 0.8}},
        ]
        for index, mutation in enumerate(variants):
            with self.subTest(mutation=mutation):
                result, browser, _ = self.run_harness(req=request(f"prob-{index}"), browser=FakeBrowser(), judgment=FakeJudgment(mutation))
                self.assertEqual(result["error_code"], "AJV_E_PROBABILITY_INVALID")
                self.assertEqual(browser.actions, 0)

    def test_unknown_candidate_injection(self):
        result, browser, _ = self.run_harness(judgment=FakeJudgment({"selected_candidate_id": "injected"}))
        self.assertEqual(result["error_code"], "AJV_E_JEV_CONTRACT")
        self.assertEqual(browser.actions, 0)

    def test_missing_omitted_mass(self):
        class Missing(FakeJudgment):
            def judge(self, current, candidates, goal):
                value = super().judge(current, candidates, goal)
                del value["omitted_mass"]
                return value
        result, browser, _ = self.run_harness(judgment=Missing())
        self.assertEqual(result["error_code"], "AJV_E_JEV_CONTRACT")
        self.assertEqual(browser.actions, 0)

    def test_intent_write_failure_prevents_action(self):
        original = ReceiptLedger.append
        def broken(ledger, event, payload):
            if event == "intent_durable":
                raise ReceiptWriteError("injected")
            return original(ledger, event, payload)
        with patch.object(ReceiptLedger, "append", broken):
            result, browser, _ = self.run_harness()
        self.assertEqual(result["error_code"], "AJV_E_INTENT_NOT_DURABLE")
        self.assertEqual(browser.actions, 0)

    def test_secret_observation_stops_without_leaking(self):
        marker = "abcdefghijklmnop"
        result, browser, _ = self.run_harness(browser=FakeBrowser(leak=True))
        self.assertEqual(result["error_code"], "AJV_E_SECRET_DETECTED")
        self.assertEqual(browser.actions, 0)
        self.assertNotIn(marker, Path(result["receipt_path"]).read_text())

    def test_action_exception_is_redacted(self):
        marker = "abcdefghijklmnop"
        result, _, _ = self.run_harness(browser=FakeBrowser(fail_action=True))
        self.assertEqual(result["error_code"], "AJV_E_ACTION_FAILED")
        self.assertNotIn(marker, json.dumps(result))
        self.assertNotIn(marker, Path(result["receipt_path"]).read_text())

    def test_paid_failure_is_not_retried_or_fallen_back(self):
        judge = FakeJudgment(fail=True)
        result, browser, _ = self.run_harness(judgment=judge)
        self.assertEqual(result["error_code"], "AJV_E_JEV_UNAVAILABLE")
        self.assertEqual(judge.calls, 1)
        self.assertEqual(browser.actions, 0)

    def test_cost_budget_is_enforced(self):
        class CostlyBrowser(FakeBrowser):
            def enumerate_candidates(self, current, goal):
                candidates = super().enumerate_candidates(current, goal)
                candidates[0]["estimated_cost"] = 1
                return candidates
        result, browser, _ = self.run_harness(browser=CostlyBrowser())
        self.assertEqual(result["status"], "DENIED")
        self.assertEqual(browser.actions, 0)

    def test_secret_handles_require_external_reference(self):
        bad, browser, _ = self.run_harness(req=request(secret_handles={"login": "plain-password"}))
        self.assertEqual(bad["error_code"], "AJV_E_SECRET_DETECTED")
        self.assertEqual(browser.actions, 0)
        good, _, _ = self.run_harness(req=request("handle-run", secret_handles={"login": "vault://example/login"}))
        self.assertEqual(good["status"], "COMPLETED")

    def test_run_id_is_idempotent(self):
        first, browser, judgment = self.run_harness()
        second = Harness(browser, judgment, self.temp.name).run(request())
        self.assertEqual(second["status"], first["status"])
        self.assertEqual(browser.actions, 1)
        self.assertIn("run_id_reused_existing_result", second["warnings"])

    def test_unknown_request_field_rejected(self):
        result, browser, _ = self.run_harness(req=request(extra=True))
        self.assertEqual(result["error_code"], "AJV_E_REQUEST_INVALID")
        self.assertEqual(browser.actions, 0)

    def test_inexact_goal_rejected(self):
        result, browser, _ = self.run_harness(req=request(goal={"description": "looks done"}))
        self.assertEqual(result["error_code"], "AJV_E_GOAL_INEXACT")
        self.assertEqual(browser.actions, 0)

    def test_adapter_success_without_completion_is_failure(self):
        req = request(budgets={"max_actions": 1, "max_jev_calls": 1, "max_elapsed_seconds": 10, "max_paid_cost": 0})
        result, browser, _ = self.run_harness(req=req, browser=FakeBrowser(done_after=2))
        self.assertEqual(result["error_code"], "AJV_E_COMPLETION_MISMATCH")
        self.assertEqual(browser.actions, 1)

    def test_exact_not_substring(self):
        goal = {"completion": [{"path": "facts.status", "op": "eq", "expected": "submitted"}]}
        outcome = evaluate_completion(goal, observation(facts={"status": "not submitted"}))
        self.assertFalse(outcome["matched"])


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def make_receipt(self, name="ledger.jsonl"):
        path = Path(self.temp.name) / name
        ledger = ReceiptLedger(path, "r")
        ledger.append("request_accepted", {"ok": True})
        ledger.append("terminal_result", {"result": {"status": "ALREADY_COMPLETE"}})
        return path

    def test_valid_chain_nonempty(self):
        result = verify_receipts(self.make_receipt())
        self.assertTrue(result["valid"])
        self.assertGreater(result["records_checked"], 0)

    def test_append_does_not_modify_existing_bytes(self):
        path = Path(self.temp.name) / "append.jsonl"
        ledger = ReceiptLedger(path, "append")
        ledger.append("request_accepted", {"ok": True})
        original = path.read_bytes()
        ledger.append("terminal_result", {"result": {"status": "ALREADY_COMPLETE"}})
        self.assertEqual(path.read_bytes()[:len(original)], original)

    def test_empty_fails(self):
        path = Path(self.temp.name) / "empty.jsonl"
        path.touch()
        self.assertFalse(verify_receipts(path)["valid"])

    def test_byte_tamper_fails(self):
        path = self.make_receipt()
        path.write_bytes(path.read_bytes().replace(b'"ok":true', b'"ok":false', 1))
        self.assertFalse(verify_receipts(path)["valid"])

    def test_line_delete_and_swap_fail(self):
        for mode in ("delete", "swap"):
            with self.subTest(mode=mode):
                path = self.make_receipt(f"{mode}.jsonl")
                lines = path.read_text().splitlines()
                changed = lines[1:] if mode == "delete" else list(reversed(lines))
                path.write_text("\n".join(changed) + "\n")
                self.assertFalse(verify_receipts(path)["valid"])


class SurfaceTests(unittest.TestCase):
    def test_version_and_tools(self):
        self.assertRegex(__version__, r"^\d+\.\d+\.\d+$")
        self.assertEqual({tool["name"] for tool in TOOLS}, {"run_safe_browser_task", "check_health", "verify_receipts"})

    def test_mcp_list_dispatch(self):
        response = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(len(response["result"]["tools"]), 3)

    def test_health_self_check_and_no_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            value = check_health(directory)
        self.assertEqual(value["status"], "degraded")
        self.assertTrue(value["components"]["offline_verifier"]["ok"])
        self.assertGreater(value["components"]["offline_verifier"]["valid_records_checked"], 0)
        self.assertEqual(value["side_effect_actions"], 0)

    def test_cli_help_discovers_commands(self):
        completed = subprocess.run([sys.executable, "-m", "aside_jav.cli", "--help"], text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0)
        for word in ("run", "health", "verify", "version"):
            self.assertIn(word, completed.stdout)


if __name__ == "__main__":
    unittest.main()
