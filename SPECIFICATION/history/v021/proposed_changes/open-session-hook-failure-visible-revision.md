---
proposal: open-session-hook-failure-visible.md
decision: accept
revised_at: 2026-11-08T02:06:35Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:codex-plugin-hook-path-regression
---

## Decision and Rationale

Accepted as written. Leg A of livespec plan livespec-3rfjga (livespec repo, plan/codex-plugin-hook-path-regression/research/leg-a-keep-original-bytes-result.md) measured the ratified already-open-session scenario false on codex-cli 0.166.0. After Driver 0.12.1 -> 0.12.2 the open session reported 'Hook failed: plugin contents changed; hook approval required' and its PreToolUse guard did not block, although correct re-trust was already recorded, while a fresh session ran every hook and blocked. The amendments replace the unachievable open-session continuity claim with the plan's decided split (a session started after reconciliation runs every hook; an already-open session's hook failures stay visible), drift-sweep the two sibling 'long-running hooks survive' scenarios and the real-transition test sentences, and add a contract paragraph scoped to the measured Codex behaviour. No heading is renamed: the heading-coverage debt ratchet ratified 'renaming cannot reset debt', so the already-open-session heading keeps its old wording until a real integration test retires its debt, and a follow-up livespec-driver-codex work item carries that rename. Decided by the delegated decider legacy-coordinator-agent (Claude Code session a21903eb-e670-4abd-b667-e5ee01a7aafe), under ruling R301 under R301; the maintainer has not ruled. Independent ratification review (sonnet) returned NO BLOCKERS on these exact bytes after two BLOCKERS rounds, recorded on livespec-driver-codex PR #1021. The fail-open defect stays tracked as livespec-driver-codex-sjwyha.

## Resulting Changes

- scenarios.md
- contracts.md
- non-functional-requirements.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T02:03:27Z
verdict: NO BLOCKERS
proposal_stem: open-session-hook-failure-visible
content_digest: 487f4d27b0f92ee1236eb080f245fa32c24a839dcbccd9562978b39cab40449a
