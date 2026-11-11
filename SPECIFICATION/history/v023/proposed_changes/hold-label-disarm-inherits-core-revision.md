---
proposal: hold-label-disarm-inherits-core.md
decision: modify
revised_at: 2026-11-11T00:04:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified under delegated revise authority (legacy-coordinator-agent R301, 2026-11-10, standing grade, --only-topic hold-label-disarm-inherits-core). The bullet is appended to ## Inherited from livespec of non-functional-requirements.md, citing livespec non-functional-requirements.md §"Shared content sync — copier template" (ratified in livespec v240, livespec#3163) rather than restating the behaviour. MODIFY: 'byte-identical to livespec's root copy' becomes 'identical to livespec's root copy except that the App-token input key matches this repository's auto-enable-merge.yml', because this repository's auto-enable-merge.yml mints with app-id: while livespec's disarm copy uses client-id: (verified by diff).

## Modifications



## Resulting Changes

- non-functional-requirements.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T23:54:50Z
verdict: NO BLOCKERS
proposal_stem: hold-label-disarm-inherits-core
content_digest: 623f43c0c7140540827e816ff1516a84a21c0605d62c05a9e254074f55d8180f
