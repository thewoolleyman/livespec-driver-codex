---
proposal: single-process-pretooluse-guard-dispatch.md
decision: modify
revised_at: 2026-11-02T01:07:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:anthropic-burn-mitigation
---

## Decision and Rationale

Accepted in modified form; delegated decider legacy-coordinator-agent (R301 ruling 2026-11-02 ~01:02Z, accept in both Drivers; MODIFY accepted ~01:15Z). The decider objected that a fail-open dispatcher self-failure would silently drop a fail-closed guard's deny-on-failure guarantee; resolved by falling back to the standalone guards on dispatcher self-failure, which keeps every declared posture exactly as in the standalone layout without denying calls the standalone guards would allow (the decider's suggested blanket deny would refuse every Bash call while the dispatcher is broken, which is stricter than standalone). Modifications resolve the independent Sonnet ratification reviewer's blockers without changing the ruling's substance: one process per Bash call, per-guard failure isolation, a refusal byte-identical to the standalone guard, standalone runnability, plus scenarios. Measured saving about 0.8-1.0 CPU-s per Bash call on the dev host (plan anthropic-burn-mitigation, epic bd-ib-b2jzxw). tests/heading-coverage.json entries for the new scenario headings are co-edited in the same change outside resulting_files because that file lies outside the spec target. Delegated decider confirmed "MODIFY OK" on this exact digest (~01:20Z). Independent read-only Sonnet 5.5 ratification reviewer returned NO BLOCKERS on this exact digest after three rounds.

## Modifications

Modified for parity with the livespec-driver-claude twin after its independent ratification review: each guard's failure boundary discharges its DECLARED failure posture (fail-open by default, fail-closed for any upstream fail-closed guard or guard check, such as the footgun guard's tmux check), "Bash-matched" is defined, a guard also registered on other tools keeps its own entry there, "times out" is dropped in favour of the runtime's whole-process hook timeout, and a third scenario covers a crashing fail-closed guard.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T01:06:26Z
verdict: NO BLOCKERS
proposal_stem: single-process-pretooluse-guard-dispatch
content_digest: abd585dee57c52eecac7b90a20c59e1a5e36e66c905e849ce043943b9522b3e6
