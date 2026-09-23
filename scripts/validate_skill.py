#!/usr/bin/env python3
"""Deterministically validate the product documentation and Hermes skill."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "aside-combination-jev"
REQUIRED_SKILL_PHRASES = (
    "name: aside-combination-jev",
    "## Automatic mode",
    "## Manual mode",
    "## Health and recovery",
    "## Install and uninstall",
    "## Receipt meaning",
    "aside-jav health",
    "aside-jav verify",
    "--uninstall",
)
REQUIRED_ENGLISH_PHRASES = (
    "## Quick start",
    "## Manual operation",
    "## Automatic operation with Hermes",
    "## Health and recovery",
    "## Receipt verification",
    "## Security model and limits",
    "## Uninstall and rollback",
    "## Copyright and license",
)
REQUIRED_KOREAN_PHRASES = (
    "## 빠른 시작",
    "## 수동 운전",
    "## Hermes 자동 운전",
    "## Health와 복구",
    "## Receipt 검증",
    "## 보안 모델과 제약",
    "## 제거와 rollback",
    "## 저작권과 라이선스",
)
FORBIDDEN_PUBLIC_PATTERNS = (
    ("personal_absolute_path", re.compile(r"/(?:Users|home)/[^/\s`]+/")),
    ("sensitive_auth_term", re.compile(r"c" + r"redential", re.IGNORECASE)),
    ("source_lineage_term", re.compile(r"up" + r"stream|App" + r"caster|원" + r"작", re.IGNORECASE)),
)


def check(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def validate(skill_path: Path) -> dict[str, object]:
    failures: list[str] = []
    checks = 0
    files = {
        "skill": skill_path,
        "english": ROOT / "README.md",
        "korean": ROOT / "README.ko.md",
        "license": ROOT / "LICENSE",
    }
    texts: dict[str, str] = {}
    for label, path in files.items():
        checks += 1
        check(path.is_file(), f"missing_{label}", failures)
        texts[label] = path.read_text(encoding="utf-8") if path.is_file() else ""

    for phrase in REQUIRED_SKILL_PHRASES:
        checks += 1
        check(phrase in texts["skill"], f"skill_missing:{phrase}", failures)
    for phrase in REQUIRED_ENGLISH_PHRASES:
        checks += 1
        check(phrase in texts["english"], f"english_missing:{phrase}", failures)
    for phrase in REQUIRED_KOREAN_PHRASES:
        checks += 1
        check(phrase in texts["korean"], f"korean_missing:{phrase}", failures)

    frontmatter = texts["skill"].split("---", 2)
    checks += 2
    check(len(frontmatter) == 3, "invalid_frontmatter", failures)
    names = re.findall(r"(?m)^name:\s*(\S+)\s*$", texts["skill"])
    check(names == [SKILL_NAME], "skill_name_not_unique", failures)

    public_text = "\n".join(texts.values())
    for label, pattern in FORBIDDEN_PUBLIC_PATTERNS:
        checks += 1
        check(pattern.search(public_text) is None, f"forbidden:{label}", failures)

    checks += 3
    check("Copyright (c) 2026 aside-combination-jev contributors" in texts["license"], "project_copyright_missing", failures)
    check("MIT License" in texts["license"], "license_missing", failures)
    check(not (ROOT / "README.en.md").exists(), "legacy_english_readme_present", failures)

    return {"valid": not failures, "checks_run": checks, "failures": failures, "skill": str(skill_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", type=Path, default=ROOT / "hermes-skill" / "SKILL.md")
    args = parser.parse_args()
    result = validate(args.skill)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
