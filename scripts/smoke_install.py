#!/usr/bin/env python3
"""Run a fresh-environment install, operation, and uninstall smoke test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    if completed.returncode != expect:
        raise RuntimeError(
            f"command returned {completed.returncode}, expected {expect}: {command!r}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed


def decode_last(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    lines = completed.stdout.strip().splitlines()
    return json.loads(lines[-1]) if lines else {}


def main() -> int:
    scratch = os.environ.get("TMPDIR")
    with tempfile.TemporaryDirectory(prefix="aside-jav-smoke-", dir=scratch) as directory:
        root = Path(directory)
        environment = root / "venv"
        home = root / "hermes"
        receipts = root / "receipts"
        receipt = receipts / "smoke.jsonl"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

        installed = decode_last(run([str(python), "scripts/install.py", "--hermes-home", str(home)]))
        version = decode_last(run([str(python), "-m", "aside_jav.cli", "version"]))
        health = decode_last(
            run([str(python), "-m", "aside_jav.cli", "health", "--receipt-dir", str(root / "health")])
        )
        skill = home / "skills" / "aside-combination-jev" / "SKILL.md"
        validation = decode_last(run([str(python), "scripts/validate_skill.py", "--skill", str(skill)]))

        helper = root / "make_receipt.py"
        helper.write_text(
            "from aside_jav.receipts import ReceiptLedger\n"
            "import sys\n"
            "ledger = ReceiptLedger(sys.argv[1], 'smoke')\n"
            "ledger.append('request_accepted', {'ok': True})\n"
            "completion = {'matched': True, 'evidence': []}\n"
            "ledger.append('completion_verdict', {'completion': completion})\n"
            "ledger.append('terminal_result', {'result': {'status': 'ALREADY_COMPLETE', 'completion': completion, 'before_fingerprint': 'a' * 64, 'after_fingerprint': None}})\n",
            encoding="utf-8",
        )
        run([str(python), str(helper), str(receipt)])
        verification = decode_last(run([str(python), "-m", "aside_jav.cli", "verify", str(receipt)]))
        removed = decode_last(
            run([str(python), "scripts/install.py", "--uninstall", "--hermes-home", str(home)])
        )
        probe = root / "probe_import.py"
        probe.write_text("import aside_jav\n", encoding="utf-8")
        import_after_remove = run([str(python), str(probe)], expect=1)

        checks = {
            "installer_ok": installed.get("ok") is True,
            "version": version.get("version"),
            "health_status": health.get("status"),
            "health_records_checked": health.get("components", {}).get("offline_verifier", {}).get("valid_records_checked") if isinstance(health.get("components"), dict) else None,
            "skill_valid": validation.get("valid") is True,
            "skill_checks_run": validation.get("checks_run"),
            "receipt_valid": verification.get("valid") is True,
            "receipt_records_checked": verification.get("records_checked"),
            "uninstaller_ok": removed.get("ok") is True,
            "skill_removed": not skill.parent.exists(),
            "package_removed": import_after_remove.returncode != 0,
            "receipt_preserved": receipt.is_file() and receipt.stat().st_size > 0,
        }
        valid = all(
            (
                checks["installer_ok"],
                checks["version"] == "0.1.0",
                checks["health_status"] == "degraded",
                isinstance(checks["health_records_checked"], int) and checks["health_records_checked"] > 0,
                checks["skill_valid"],
                isinstance(checks["skill_checks_run"], int) and checks["skill_checks_run"] > 0,
                checks["receipt_valid"],
                isinstance(checks["receipt_records_checked"], int) and checks["receipt_records_checked"] > 0,
                checks["uninstaller_ok"],
                checks["skill_removed"],
                checks["package_removed"],
                checks["receipt_preserved"],
            )
        )
        print(json.dumps({"valid": valid, "checks": checks}, sort_keys=True))
        return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
