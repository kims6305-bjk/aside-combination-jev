from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"
VALIDATOR = ROOT / "scripts" / "validate_skill.py"
ACCEPTANCE_MAP = ROOT / "tests" / "acceptance_map.json"


class ProductLayerTests(unittest.TestCase):
    def run_json(self, *args: str) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        output = completed.stdout.strip().splitlines()
        payload = json.loads(output[-1]) if output else {}
        return completed, payload

    def test_source_skill_validator_runs_nonzero_checks(self):
        completed, payload = self.run_json(str(VALIDATOR))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(payload["valid"])
        self.assertGreater(int(payload["checks_run"]), 0)

    def test_all_black_box_acceptance_ids_map_to_runnable_tests(self):
        spec_ids = set(re.findall(r"\*\*(AT-\d+)", (ROOT / "spec" / "BLACK_BOX_SPEC.md").read_text(encoding="utf-8")))
        mapping = json.loads(ACCEPTANCE_MAP.read_text(encoding="utf-8"))
        self.assertEqual(set(mapping), spec_ids)
        self.assertEqual(len(mapping), 44)
        runnable: list[str] = []
        for acceptance_id, node_ids in mapping.items():
            self.assertTrue(node_ids, acceptance_id)
            for node_id in node_ids:
                parts = node_id.split("::")
                self.assertEqual(len(parts), 3, f"{acceptance_id}: {node_id}")
                self.assertTrue(parts[-1].startswith("test_"), f"{acceptance_id}: {node_id}")
                runnable.append(node_id)
        unique_node_ids = sorted(set(runnable))
        self.assertGreater(len(unique_node_ids), 0)
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", *unique_node_ids],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        match = re.search(r"(\d+) passed", completed.stdout)
        if match is None:
            self.fail(completed.stdout)
        self.assertEqual(int(match.group(1)), len(unique_node_ids))

    def test_single_skill_install_validate_and_reversible_remove(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "hermes"
            installed, payload = self.run_json(str(INSTALLER), "--skip-package", "--hermes-home", str(home))
            self.assertEqual(installed.returncode, 0, installed.stderr)
            self.assertTrue(payload["skill_installed"])
            skill = home / "skills" / "aside-combination-jev" / "SKILL.md"
            self.assertTrue(skill.is_file())
            self.assertEqual([entry.name for entry in (home / "skills").iterdir()], ["aside-combination-jev"])

            checked, validation = self.run_json(str(VALIDATOR), "--skill", str(skill))
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertTrue(validation["valid"])
            self.assertGreater(int(validation["checks_run"]), 0)

            removed, result = self.run_json(
                str(INSTALLER), "--uninstall", "--skip-package", "--hermes-home", str(home)
            )
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertTrue(result["skill_removed"])
            self.assertTrue(result["receipts_preserved"])
            self.assertFalse(skill.parent.exists())

    def test_uninstall_preserves_changed_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "hermes"
            installed, _ = self.run_json(str(INSTALLER), "--skip-package", "--hermes-home", str(home))
            self.assertEqual(installed.returncode, 0)
            skill = home / "skills" / "aside-combination-jev" / "SKILL.md"
            skill.write_text(skill.read_text(encoding="utf-8") + "\nlocal note\n", encoding="utf-8")

            removed, result = self.run_json(
                str(INSTALLER), "--uninstall", "--skip-package", "--hermes-home", str(home)
            )
            self.assertNotEqual(removed.returncode, 0)
            self.assertFalse(result["ok"])
            self.assertTrue(skill.exists())

    def test_explicit_receipt_purge_previews_then_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            receipts = Path(directory) / "receipts"
            receipts.mkdir()
            (receipts / "one.jsonl").write_text("audit\n", encoding="utf-8")
            previewed, preview = self.run_json(str(INSTALLER), "--purge-receipts", str(receipts))
            self.assertEqual(previewed.returncode, 0, previewed.stderr)
            self.assertEqual(preview["targets"], [str(receipts.resolve())])
            self.assertFalse(preview["purged"])
            self.assertTrue(receipts.exists())

            purged, result = self.run_json(str(INSTALLER), "--purge-receipts", str(receipts), "--confirm-purge")
            self.assertEqual(purged.returncode, 0, purged.stderr)
            self.assertTrue(result["purged"])
            self.assertFalse(receipts.exists())

    def test_receipt_paths_with_platform_separators_remain_verifiable(self):
        from aside_jav.receipts import ReceiptLedger, verify_receipts

        with tempfile.TemporaryDirectory() as directory:
            for name in ("native/receipt.jsonl", "windows\\receipt.jsonl", "space dir/receipt.jsonl"):
                path = Path(directory) / name
                ledger = ReceiptLedger(path, "platform")
                ledger.append("request_accepted", {"ok": True})
                ledger.append("terminal_result", {"result": {"status": "FAILED"}})
                self.assertTrue(verify_receipts(path)["valid"], name)


if __name__ == "__main__":
    unittest.main()
