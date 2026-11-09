---
proposal: hook-coverage-config.md
decision: accept
revised_at: 2026-11-09T20:07:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:dev-host-test-gate-load
---

## Decision and Rationale

Accepted as written. This governs the coverage gate that `check-coverage` already enforces over `livespec/hooks/` (100% line and branch, `branch = true`, `fail_under = 100`), which no clause stated. It requires that pyproject.toml's coverage configuration govern every pytest coverage run, so a bare `pytest --cov` still combines branch data with test-subprocess data. That is the defect livespec-dev-tooling-wj45qt measured on 2026-11-09 (livespec-dev-tooling#3895). It gives livespec-driver-codex-toclbe, the wj45qt execution mirror held for want of a governing heading, the scenario its References line re-points to. Co-edits: a heading-coverage TODO row for the new scenario, owned by toclbe at the integration tier, and its generated debt-register entry. Decided by the proposal's author, plan seat dev-host-test-gate-load (Claude Code session fc6809f4), under legacy-coordinator-agent's ruling that the author ratifies its own topic (the pipefail precedent); the maintainer has not ruled. Independent ratification review (sonnet, read-only) recomputed the digest and returned NO BLOCKERS on these exact bytes.

## Resulting Changes

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
reviewed_at: 2026-11-09T20:06:49Z
verdict: NO BLOCKERS
proposal_stem: hook-coverage-config
content_digest: 8c441a4b1d8feb45de9c3c9b40aa4d73338b4e836ecdb867d15c501c2726fea0
