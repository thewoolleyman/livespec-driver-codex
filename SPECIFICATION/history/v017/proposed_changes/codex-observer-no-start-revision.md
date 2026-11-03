---
proposal: codex-observer-no-start.md
decision: accept
revised_at: 2026-11-03T10:41:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as filed (PR #945, head 38314f7). It closes the three warnings the LLM doctor raised on v016: ensure-codex-plugins MUST NOT start an observer on any platform (closing the takeover shape of draft PR #921 that v016 left legal by omission), the newer of its own reconcile and the observer status record governs each plugin's reported result (with a required comparable completion time, an equal-time rule, and an explicit exception in the per-plugin first-reconcile health rule), and Linux counterparts to the v016 macOS supervisor scenarios against the shipped systemd user unit. The first fresh review's two blockers (contradiction with unconditional v016 text; missing non-functional-requirements test obligations) were fixed and the second returned NO BLOCKERS. The resulting text applies every replacement and insertion verbatim, re-wrapping the two amended contracts.md paragraphs to the file's width, and adds two integration-tier TODO coverage rows and debt-register rows citing livespec-driver-codex-n2b3ui. Decided under the coordinator's pre-ruling and the project's delegated revise_decision_mode.

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
reviewed_at: 2026-11-03T10:41:42Z
verdict: NO BLOCKERS
proposal_stem: codex-observer-no-start
content_digest: 843cfd75ef6bf2b38f3a797c2ccdb17ca1a25669ed7e6c496a265abf4feaa1b0
