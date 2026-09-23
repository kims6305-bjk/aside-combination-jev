"""Real-browser check: drive headless Chromium through the harness.

Requires `pip install playwright && python -m playwright install chromium`.
Serves a local demo page on 127.0.0.1 only; no accounts, no network.

    python examples/playwright_live.py
"""

from __future__ import annotations

import http.server
import json
import tempfile
import threading
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from aside_jav import run_safe_browser_task
from aside_jav.receipts import fingerprint, verify_receipts

PAGE = """<!doctype html><title>demo</title>
<p id=count>0</p><p id=status>active</p><p id=note>%s</p>
<button data-testid=inc data-kind=click data-risk=reversible
  onclick="count.textContent=+count.textContent+1">Increment</button>
<button data-testid=del data-kind=submit data-risk=sensitive
  onclick="status.textContent='deleted'">Delete account</button>"""


class Browser:
    """Playwright adapter. Targets are addressed only by data-testid."""

    def __init__(self, page):
        self.page = page

    def observe(self, ctx):
        if self.page.url != ctx["url"]:
            self.page.goto(ctx["url"])
        els = self.page.eval_on_selector_all(
            "[data-testid]",
            "es => es.map(e => ({stable_id: e.dataset.testid, label: e.textContent.trim(),"
            " kind: e.dataset.kind, risk_class: e.dataset.risk}))",
        )
        return {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "location": self.page.url,
            "title": self.page.title(),
            "elements": els,
            "facts": {k: self.page.text_content(f"#{k}") for k in ("count", "status", "note")},
            "omissions": [],
        }

    def enumerate_candidates(self, obs, goal):
        return [
            {"candidate_id": e["stable_id"], "kind": e["kind"], "risk_class": e["risk_class"],
             "target": {"stable_id": e["stable_id"]}, "value": None,
             "declared_effect": e["label"], "estimated_cost": 0,
             "source_fingerprint": obs["fingerprint"]}
            for e in obs["elements"]
        ]

    def execute(self, cand, ctx):
        self.page.click(f"[data-testid={cand['target']['stable_id']}]")


class Judgment:
    """Deterministic stand-in for a model: picks the candidate named in goal['want']."""

    paid = False

    def judge(self, obs, cands, goal):
        pick = goal["want"]
        probs = {c["candidate_id"]: (1.0 if c["candidate_id"] == pick else 0.0) for c in cands}
        return {"decision_id": f"d-{obs['fingerprint'][:8]}", "selected_candidate_id": pick,
                "allow_recommendation": True, "confidence": 1.0, "probabilities": probs,
                "omitted_mass": 0.0, "reason_codes": ["goal_match"], "model_id": "rule-v1",
                "input_fingerprint": fingerprint({"observation": obs, "candidates": cands, "goal": goal})}


def request(run_id, url, want, rules, dry_run=False):
    return {"run_id": run_id, "goal": {"want": want, "completion": rules},
            "allowed_actions": ["click", "submit"], "forbidden_actions": [],
            "sensitive_classes": ["sensitive"],
            "budgets": {"max_actions": 2, "max_jev_calls": 3, "max_elapsed_seconds": 30, "max_paid_cost": 0},
            "browser_context": {"url": url}, "dry_run": dry_run}


def serve(note):
    body = (PAGE % note).encode()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/"


def main():
    out, rdir = {}, tempfile.mkdtemp(prefix="aside-jav-live-")
    srv, url = serve("hello")
    bad, bad_url = serve("card 4111 1111 1111 1111")
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        def run(name, url, *args, **kw):
            page = b.new_page()
            res = run_safe_browser_task(request(name, url, *args, **kw), Browser(page), Judgment(), rdir)
            v = verify_receipts(res["receipt_path"]) if res["receipt_path"] else {"valid": None}
            out[name] = {"status": res["status"], "error": res["error_code"],
                         "attempted": res["actions_attempted"], "receipt_valid": v["valid"],
                         "dom": {k: page.text_content(f"#{k}") for k in ("count", "status")}}
            page.close()

        run("click", url, "inc", [{"path": "facts.count", "op": "eq", "expected": "1"}])
        run("dry", url, "inc", [{"path": "facts.count", "op": "eq", "expected": "1"}], dry_run=True)
        run("sensitive", url, "del", [{"path": "facts.status", "op": "eq", "expected": "deleted"}])
        run("secret", bad_url, "inc", [{"path": "facts.count", "op": "eq", "expected": "1"}])
        b.close()
    srv.shutdown(); bad.shutdown()
    print(json.dumps(out, indent=1))

    # Independent DOM checks, not the harness's own claims.
    assert out["click"]["status"] == "COMPLETED" and out["click"]["dom"]["count"] == "1"
    assert out["dry"]["status"] == "DRY_RUN" and out["dry"]["dom"]["count"] == "0"
    assert out["sensitive"]["status"] == "NEEDS_HUMAN" and out["sensitive"]["dom"]["status"] == "active"
    assert out["secret"]["error"] == "AJV_E_SECRET_DETECTED" and out["secret"]["attempted"] == 0
    assert all(r["receipt_valid"] for r in out.values())
    print("LIVE PASS 4/4")


if __name__ == "__main__":
    main()
