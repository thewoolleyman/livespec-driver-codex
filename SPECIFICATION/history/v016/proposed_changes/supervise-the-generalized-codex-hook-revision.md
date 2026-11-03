---
proposal: supervise-the-generalized-codex-hook.md
decision: accept
revised_at: 2026-11-03T08:47:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed. The v014 contract stated observer supervision for Linux only, and the shipped provisioner exits 0 on macOS with no supervisor, which left the MacBook Pro unprotected; the closed draft PR #921 showed the architectural failure modes (taking over launchd's observer, single-plugin coverage, runtime-generated definitions, health before the first reconcile, an Apple-Silicon-only interpreter) that the contract must rule out. The resulting text applies every proposed replacement and insertion verbatim (re-wrapped to the files' line width where the proposal gives prose rather than a verbatim block), applied on top of v015, whose spans this proposal does not touch. It adds the three scenarios with integration-tier TODO coverage rows and debt-register rows citing livespec-driver-codex-yudufr. Decided under the coordinator's R301 pre-ruling (accept #937 after #933, provided the configured Sonnet ratification review is NO BLOCKERS on the final bytes) and the project's delegated revise_decision_mode.

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
reviewed_at: 2026-11-03T08:47:09Z
verdict: NO BLOCKERS
proposal_stem: supervise-the-generalized-codex-hook
content_digest: 939600e0a8cc431ba65b8dc6dfb26f50b187da1dfc0c977c9668e79d7fefc935
