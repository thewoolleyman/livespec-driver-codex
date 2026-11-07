---
proposal: codex-curated-marketplace-exclusion.md
decision: modify
revised_at: 2026-11-07T14:38:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Decision: modify (accept with modifications). Decider: legacy-coordinator-agent (session 348c3d09), under R301 delegated revise authority, ruling of 2026-11-07. Proposal author: claude:codex-plugin-hook-path-regression. The payload was assembled and the wrapper driven by a dispatched Claude agent on the decider's behalf.

The proposal fixes work item livespec-driver-codex-hbi (plan livespec-3rfjga, codex-plugin-hook-path-regression). On 2026-11-06 on chads-macbook-pro, the ChatGPT desktop app 26.1007.71326 had registered its own `[marketplaces.openai-bundled]` and `openai-primary-runtime` local entries, so the previous criterion (a marketplace with no configuration entry is not covered) stopped excluding Codex-curated caches, those plugins became covered, and the trust-continuity rule failed `ensure-codex-plugins`. The refusal itself was correct; the exclusion criterion had stopped matching its intent. The ratified rule keys the exclusion on where a local marketplace's source resolves (the Codex bundled-marketplace directory under the Codex home, and `~/.cache/codex-runtimes/`), keeps third-party local marketplaces such as honeycomb-plugins covered, classifies any unresolvable source as covered so a classification failure never hides a plugin, forbids the Driver from writing inside a Codex-curated cache, and surfaces Driver-alias-shaped links there as non-failing notices rather than deleting on inference. The drift sweep amends the covered-set example sentence and both enumerations of required mock-cache test coverage; constraints.md, scenarios.md, spec.md and README.md need no change, and no `## ` heading changes, so tests/heading-coverage.json needs no co-edit.

The modifications are wording-only clarifications that keep the history out of the normative text and remove three ambiguities in the notice and the path comparison; they do not change the rule's substance.

FLEET SCOPE (rule K), measured 2026-11-07 from origin/master code: neither livespec-driver-claude (4cb7148) nor livespec-driver-pi (6b9b9a0) creates, replaces or removes anything inside a host-owned or app-curated plugin cache. livespec-driver-claude reads Claude Code's ~/.claude/plugins/cache only to resolve core's plugin root (.claude-plugin/lib/resolve_core_root.py; dev-tooling/bin/verify_guard_rollout.py, dev-tooling/just/check-doctor-static.sh and justfile reference it read-only), and livespec-driver-pi reads only the project-scope .pi/git/ clone (lib/resolve-core-root.sh). No sibling proposal is needed.

Ratification review: a fresh sonnet reviewer returned VERDICT: NO-BLOCKERS on the proposal text at head 41aec4e. Because the wrapper binds review evidence to the digest of the final resulting-file bytes, and those bytes carry the modifications below, a second separately spawned read-only sonnet reviewer reviewed the exact final bytes and returned NO BLOCKERS; that second review is the evidence recorded below.

## Modifications

Applied the proposal's four amendments (two in contracts.md §"Codex hook-cache compatibility", one identical sentence in each of the non-functional-requirements.md §"Enforcement suite" and §"Test discipline" enumerations) with these wording-only modifications:

(1) Normative text describes the ratified rule, not the pre-ratification world: "so the existence of an entry no longer separates ..." became "so the existence of an entry does not separate ...". The history (the app beginning to register its own entries) lives in this rationale and the proposal's Motivation.

(2) The non-failing notice names its channel: it is reported "in the provisioner's output and the observer's status record". The test-coverage sentence carries the same channel.

(3) The alias-shape scan is scoped: only symbolic links that are direct children of a Codex-curated plugin's `<cache>/<marketplace>/<plugin>/` directory are examined, so a link deeper in the payload (for example under `node_modules`) is not noticed. The test-coverage sentence requires the direct-child link to be noticed and a deeper link of the same shape not to be.

(5) Before comparing, the Driver MUST resolve both the local source path and the two Codex-curated directories (expanding `~`, following symbolic links), so the comparison holds when the Codex home is itself a symbolic link. The test-coverage sentence adds "a Codex home that is itself a symbolic link" to the resolution cases.

The contracts.md paragraph was re-wrapped to the file's ~72-column style; both copies of the test-coverage sentence are word-identical (the Enforcement-suite copy keeps its two-space list indent).

## Resulting Changes

- contracts.md
- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T14:38:40Z
verdict: NO BLOCKERS
proposal_stem: codex-curated-marketplace-exclusion
content_digest: 68ae208cddb4bfee272a97b4e78806420aded376c5b1ef48385b1f728e650e43
