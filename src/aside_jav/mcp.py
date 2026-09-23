"""Small stdio JSON-RPC MCP server with no third-party dependency."""

from __future__ import annotations

import json
import sys
from typing import Any

from . import __version__
from .core import check_health
from .receipts import verify_receipts

TOOLS = [
    {"name": "run_safe_browser_task", "description": "Run a policy-gated browser task (host adapters required).", "inputSchema": {"type": "object", "required": ["request"], "properties": {"request": {"type": "object"}}, "additionalProperties": False}},
    {"name": "check_health", "description": "Check local package and verifier health without side effects.", "inputSchema": {"type": "object", "properties": {"receipt_dir": {"type": "string"}}, "additionalProperties": False}},
    {"name": "verify_receipts", "description": "Verify a receipt file offline.", "inputSchema": {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}, "additionalProperties": False}},
]


def dispatch(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    if method == "notifications/initialized":
        return None
    request_id = message.get("id")
    if method == "initialize":
        result = {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "aside-jav", "version": __version__}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = message.get("params", {})
        name, arguments = params.get("name"), params.get("arguments", {})
        if name == "check_health":
            value = check_health(arguments.get("receipt_dir"))
        elif name == "verify_receipts":
            value = verify_receipts(arguments.get("path", ""))
        elif name == "run_safe_browser_task":
            value = {"error_code": "AJV_E_REQUEST_INVALID", "message": "MCP host must bind browser and judgment adapters", "retryable": False}
        else:
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Unknown tool"}}
        result = {"content": [{"type": "text", "text": json.dumps(value, ensure_ascii=False)}], "structuredContent": value, "isError": bool(value.get("error_code"))}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    for line in sys.stdin:
        try:
            response = dispatch(json.loads(line))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
        except Exception:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": "Internal error"}}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
