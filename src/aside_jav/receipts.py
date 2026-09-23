"""Append-only, hash-chained JSONL receipts and offline verification."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENESIS = "0" * 64
SCHEMA_VERSION = "1"
_SECRET_KEYS = re.compile(r"(?:password|passwd|secret|token|cookie|authorization|private[_-]?key|cvc|cvv)", re.I)
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{8,}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def contains_secret(value: Any, *, trusted_handle: bool = False) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEYS.search(key_text) and not (trusted_handle and key_text.endswith("handle")):
                if item not in (None, "", False, [], {}):
                    return True
            if contains_secret(item, trusted_handle=trusted_handle or key_text in {"secret_handles", "handle"}):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item, trusted_handle=trusted_handle) for item in value)
    if isinstance(value, str) and not trusted_handle:
        return bool(_CARD.search(value) or _BEARER.search(value))
    return False


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _SECRET_KEYS.search(str(key)) and not str(key).endswith("handle"):
                clean[str(key)] = "[REDACTED]"
            else:
                clean[str(key)] = redact(item)
        return clean
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        text = _CARD.sub("[REDACTED]", value)
        return _BEARER.sub("[REDACTED]", text)
    if isinstance(value, float) and not math.isfinite(value):
        return "[NON_FINITE]"
    return value


class ReceiptWriteError(RuntimeError):
    pass


class ReceiptLedger:
    """One append-only file per run; every append is flushed and fsynced."""

    def __init__(self, path: str | os.PathLike[str], run_id: str):
        self.path = Path(path)
        self.run_id = run_id
        self.seq = 0
        self.head = GENESIS
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size:
            raise FileExistsError(str(self.path))

    def append(self, event_type: str, payload: dict[str, Any]) -> str:
        safe_payload = redact(payload)
        if contains_secret(safe_payload):
            raise ReceiptWriteError("payload failed secret boundary")
        record = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "seq": self.seq,
            "event_type": event_type,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": safe_payload,
            "prev_hash": self.head,
        }
        record["record_hash"] = fingerprint(record)
        encoded = canonical_bytes(record) + b"\n"
        try:
            with self.path.open("ab", buffering=0) as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        except OSError as exc:
            raise ReceiptWriteError("durable receipt append failed") from exc
        self.head = record["record_hash"]
        self.seq += 1
        return self.head


def _invalid(line: int | None, code: str = "AJV_E_RECEIPT_CHAIN", records: int = 0, runs: int = 0, head: str | None = None) -> dict[str, Any]:
    return {"valid": False, "records_checked": records, "runs_checked": runs, "first_error_line": line, "error_code": code, "head_hash": head}


def verify_receipts(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Verify a receipt without network or adapter access."""
    receipt = Path(path)
    if not receipt.exists() or receipt.stat().st_size == 0:
        return _invalid(1, records=0)
    previous: dict[str, str] = {}
    next_seq: dict[str, int] = {}
    events: dict[str, list[str]] = {}
    terminal_status: dict[str, str | None] = {}
    records = 0
    final_head: str | None = None
    try:
        with receipt.open("r", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    record = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return _invalid(line_number, records=records, runs=len(events), head=final_head)
                required = {"schema_version", "run_id", "seq", "event_type", "recorded_at", "payload", "prev_hash", "record_hash"}
                if set(record) != required or contains_secret(record.get("payload")):
                    code = "AJV_E_SECRET_DETECTED" if contains_secret(record.get("payload")) else "AJV_E_RECEIPT_CHAIN"
                    return _invalid(line_number, code, records, len(events), final_head)
                run_id = record["run_id"]
                expected_previous = previous.get(run_id, GENESIS)
                expected_seq = next_seq.get(run_id, 0)
                supplied_hash = record["record_hash"]
                unhashed = dict(record)
                del unhashed["record_hash"]
                if record["prev_hash"] != expected_previous or record["seq"] != expected_seq or fingerprint(unhashed) != supplied_hash:
                    return _invalid(line_number, records=records, runs=len(events), head=final_head)
                previous[run_id] = supplied_hash
                next_seq[run_id] = expected_seq + 1
                events.setdefault(run_id, []).append(record["event_type"])
                if record["event_type"] == "terminal_result":
                    result = record.get("payload", {}).get("result", {})
                    terminal_status[run_id] = result.get("status") if isinstance(result, dict) else None
                final_head = supplied_hash
                records += 1
    except OSError:
        return _invalid(1, records=records, runs=len(events), head=final_head)

    for run_id, run_events in events.items():
        if not run_events or run_events[0] not in {"request_accepted", "request_rejected"} or "terminal_result" not in run_events:
            return _invalid(None, records=records, runs=len(events), head=final_head)
        if "action_attempted" in run_events:
            if "intent_durable" not in run_events or run_events.index("intent_durable") > run_events.index("action_attempted"):
                return _invalid(None, records=records, runs=len(events), head=final_head)
            full_order = ["observation_captured", "candidates_enumerated", "jev_decision_received", "policy_verdict", "intent_durable", "action_attempted", "reobservation_captured", "postcondition_verdict", "completion_verdict", "terminal_result"]
            required_order = full_order if terminal_status.get(run_id) == "COMPLETED" else [item for item in full_order if item in run_events]
            cursor = -1
            for item in required_order:
                try:
                    cursor = run_events.index(item, cursor + 1)
                except ValueError:
                    return _invalid(None, records=records, runs=len(events), head=final_head)
    return {"valid": True, "records_checked": records, "runs_checked": len(events), "first_error_line": None, "error_code": None, "head_hash": final_head}
