#!/usr/bin/env python3
"""Install or reversibly remove the package and its single Hermes skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGE = "aside-combination-jev"
SKILL = "aside-combination-jev"
MARKER = ".aside-combination-jev-install.json"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = PROJECT_ROOT / "hermes-skill" / "SKILL.md"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hermes_home(value: str | None) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    configured = os.environ.get("HERMES_HOME")
    return Path(configured).expanduser().resolve() if configured else Path.home() / ".hermes"


def run_pip(*arguments: str) -> None:
    subprocess.run([sys.executable, "-m", "pip", *arguments], check=True)


def install(home: Path, skip_package: bool) -> dict[str, object]:
    if not skip_package:
        run_pip("install", str(PROJECT_ROOT))
    target = home / "skills" / SKILL
    target.mkdir(parents=True, exist_ok=True)
    installed = target / "SKILL.md"
    marker_path = target / MARKER
    if installed.exists():
        if not marker_path.is_file():
            raise RuntimeError(f"refusing to replace an unmanaged skill: {target}")
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("skill_sha256") != digest(installed):
            raise RuntimeError(f"installed skill changed; refusing to replace local work: {target}")
    shutil.copyfile(SOURCE_SKILL, installed)
    marker = {
        "format": 1,
        "package": PACKAGE,
        "skill": SKILL,
        "skill_sha256": digest(installed),
    }
    marker_path.write_text(json.dumps(marker, sort_keys=True) + "\n", encoding="utf-8")
    return {"action": "install", "package_installed": not skip_package, "skill_installed": True, "skill_dir": str(target)}


def uninstall(home: Path, skip_package: bool, force_skill_remove: bool) -> dict[str, object]:
    target = home / "skills" / SKILL
    installed = target / "SKILL.md"
    marker_path = target / MARKER
    skill_removed = False
    if target.exists():
        if not marker_path.is_file() and not force_skill_remove:
            raise RuntimeError(f"refusing to remove an unmanaged skill: {target}")
        if marker_path.is_file() and installed.is_file() and not force_skill_remove:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if marker.get("skill_sha256") != digest(installed):
                raise RuntimeError(f"installed skill changed; review it or use --force-skill-remove: {target}")
        shutil.rmtree(target)
        skill_removed = True
    if not skip_package:
        run_pip("uninstall", "-y", PACKAGE)
    return {
        "action": "uninstall",
        "package_removed": not skip_package,
        "skill_removed": skill_removed,
        "receipts_preserved": True,
    }


def purge_receipts(path: Path, confirmed: bool) -> dict[str, object]:
    target = path.expanduser().resolve()
    result: dict[str, object] = {"action": "purge_receipts", "targets": [str(target)], "purged": False}
    if confirmed and target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        result["purged"] = True
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true", help="remove package and installer-owned skill; preserve receipts")
    parser.add_argument("--hermes-home", help="Hermes home; defaults to HERMES_HOME or the current user's standard location")
    parser.add_argument("--skip-package", action="store_true", help="manage only the Hermes skill")
    parser.add_argument("--force-skill-remove", action="store_true", help="remove a changed or unmanaged skill directory")
    parser.add_argument("--purge-receipts", type=Path, help="preview an explicit receipt data purge target")
    parser.add_argument("--confirm-purge", action="store_true", help="delete the path supplied by --purge-receipts")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        home = hermes_home(args.hermes_home)
        if args.purge_receipts is not None:
            result = purge_receipts(args.purge_receipts, args.confirm_purge)
        else:
            result = uninstall(home, args.skip_package, args.force_skill_remove) if args.uninstall else install(home, args.skip_package)
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"ok": True, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
