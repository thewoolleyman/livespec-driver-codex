---
proposal: re-establish-codex-hook-trust.md
decision: accept
revised_at: 2026-11-04T01:27:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:codex-plugin-hook-path-regression
---

## Decision and Rationale

Accepted under delegated decision mode (coordinator rulings R301/R493 for this plan). The proposal states the configuration-write integrity invariants that livespec-driver-codex-b5rhjf's rework note requires and that the Dispatcher's spec-change-tier check found missing from ## Hook bundle. A first independent Sonnet review found one blocker (the provisioned fail-closed setting was outside the paragraph's scope, and constraints.md lacked the forbidden pattern); the proposal was corrected and a fresh independent Sonnet review of the final bytes returned NO BLOCKERS. Its non-blocking suggestions (preserve permissions and symlink targets, key the lock to the target file, preserve comments and unrelated tables, name the fail-closed setting in a failure report) are recorded as implementation guards on b5rhjf; its note that host-provisioning writers outside this repo must take the same file-keyed lock is recorded as a follow-up on plan epic livespec-3rfjga.

## Resulting Changes

- contracts.md
- constraints.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-04T01:10:30Z
verdict: NO BLOCKERS
proposal_stem: re-establish-codex-hook-trust
content_digest: aa923b61dbfd772a34cfc211fea1bd440cd8de8c1c552aa2619fe4cfce4e793c
