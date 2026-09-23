---
name: aside-jav-safe-browser
description: Aside 브라우저 작업을 Jev 판단과 안전 정책으로 실행·검증할 때 사용. Use for policy-gated Aside browser actions with Jev judgment and verifiable receipts.
---

Use `aside-jav health` before a run and `aside-jav verify RECEIPT` afterward.

This integration does not approve payments, secret entry, deletion, external transmission, or any sensitive/unknown action. Those actions require a separate human decision. Pass vault handles, never secret values.
