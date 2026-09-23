"""Command-line interface."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .core import Harness, check_health
from .receipts import verify_receipts


def _load(spec: str) -> Any:
    module_name, separator, object_name = spec.partition(":")
    if not separator:
        raise ValueError("adapter must use module:object syntax")
    value = getattr(importlib.import_module(module_name), object_name)
    return value() if isinstance(value, type) else value


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="aside-jav", description="Policy-gated browser action harness")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a request through explicit browser and judgment adapters")
    run.add_argument("request", type=Path, help="UTF-8 RunRequest JSON file")
    run.add_argument("--browser", required=True, help="browser adapter as module:object")
    run.add_argument("--judgment", required=True, help="judgment adapter as module:object")
    run.add_argument("--receipt-dir", type=Path, default=Path(".receipts"))
    health = commands.add_parser("health", help="check package, receipt store, verifier, policy, and optional adapters")
    health.add_argument("--receipt-dir", type=Path)
    verify = commands.add_parser("verify", help="offline verify a hash-chained JSONL receipt")
    verify.add_argument("receipt", type=Path)
    commands.add_parser("version", help="print the package version")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "version":
            value, failed = {"version": __version__}, False
        elif args.command == "verify":
            value = verify_receipts(args.receipt)
            failed = not value["valid"]
        elif args.command == "health":
            value = check_health(args.receipt_dir)
            failed = value["status"] == "unhealthy"
        else:
            request = json.loads(args.request.read_text(encoding="utf-8"))
            value = Harness(_load(args.browser), _load(args.judgment), args.receipt_dir).run(request)
            failed = value["status"] in {"FAILED", "DENIED", "NEEDS_HUMAN"}
    except Exception:
        value = {"error_code": "AJV_E_REQUEST_INVALID", "message": "command input or adapter configuration is invalid", "retryable": False}
        failed = True
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
