---
proposal: codex-hook-trust-continuity.md
decision: accept
revised_at: 2026-11-03T07:25:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed. The proposal's measured motivation (Codex 0.166 hook trust is a whole-plugin content hash, withdrawn on every release and same-version re-materialization, and untrusted PreToolUse guards fail open) makes trust continuity a safety half of hook continuity that the v014 contract omits, and the stale 'Trust model' paragraph recommended the bypass. The resulting text applies every proposed replacement and insertion verbatim (re-wrapped to the files' line width), adds the two scenarios with integration-tier TODO coverage rows and debt-register rows citing livespec-driver-codex-v52m6a, and updates the two existing hook-cache scenario rows to name the trust assertion and v52m6a. Decided under the coordinator's R301 pre-ruling (accept #933 first, provided the configured Sonnet ratification review is NO BLOCKERS on the final bytes) and the project's delegated revise_decision_mode.

## Resulting Changes

- contracts.md
- constraints.md
- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T07:25:12Z
verdict: NO BLOCKERS
proposal_stem: codex-hook-trust-continuity
content_digest: 0ef1ddfa1400d1acbb21e6bf85936dc1720cfdf014ccbc43a85c68e02c0b96c1
