---
topic: orchestrate-to-drive-codex-picker-refs
author: claude-opus-4-8
created_at: 2026-07-06T22:30:43Z
---

## Proposal: rename-orchestrate-skill-to-drive-in-codex-picker-refs

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/non-functional-requirements.md

### Summary

Rename the example orchestrator-plugin skill name `orchestrate` to `drive` in the three governed-spec references that use it to demonstrate the Codex TUI /skills picker behavior (spec.md §"Public surface", scenarios.md §"Scenario: /skills picker exposes plugin skills by short name", non-functional-requirements.md §"Enforcement suite" `check-codex-skill-picker`). The fleet renamed the orchestrator skill `orchestrate`→`drive` (design record: livespec-orchestrator-beads-fabro design.md §"The four surfaces"; landed in that repo's SPECIFICATION history/v031, PR #345), so the shipped `livespec-orchestrator-beads-fabro` plugin now exposes a `drive` skill and no longer exposes `orchestrate`. These picker examples must name the skill that actually ships. The plugin name `livespec-orchestrator-beads-fabro` (which contains the word "orchestrator") is preserved verbatim in every reference — only the bare skill-name token `orchestrate` changes.

### Motivation

orchestrate→drive orchestrator-skill rename (cross-repo epic livespec-bj9x, the needs-attention rollout). The rename already landed in the beads-fabro orchestrator spec (history/v031, PR #345) and in the driver-claude binding (BR1); `drive` now EXISTS in the shipped orchestrator plugin (verified: `.claude-plugin/skills/drive/SKILL.md` present, `.../orchestrate/` gone). These three governed-SPECIFICATION references in livespec-driver-codex still name the retired `orchestrate` skill as the example the Codex picker renders; a hand-edit of a governed spec file would be rejected by /livespec:doctor, so they are renamed via propose-change. This matches the exact change-vs-preserve pattern beads-fabro's v031 used for its own equivalent Codex-skills-picker scenario (rename the skill token, preserve the plugin name). The 4 NON-spec references (justfile check-codex-skill-picker gate, e2e test, standalone heading-coverage, AGENTS.md) are out of scope for this spec propose-change and are handled by the paired factory code slice (ledger item livespec-driver-codex-01a).

### Proposed Changes

Seven skill-name `orchestrate` tokens across three governed-spec files are renamed to `drive`. Each replace-target below quotes the current live text byte-for-byte; the plugin name `livespec-orchestrator-beads-fabro` is preserved intact in every case. No `## ` heading changes (all edits are within-section body text), so `tests/heading-coverage.json` needs no co-edit.

---

**1. SPECIFICATION/spec.md — §"Public surface"** (2 tokens)

Replace this exact current text (lines 98–99):

```
plugin as context, e.g. `orchestrate (livespec-orchestrator-beads-fabro)`.
The colon-qualified form (`livespec-orchestrator-beads-fabro:orchestrate`)
```

with:

```
plugin as context, e.g. `drive (livespec-orchestrator-beads-fabro)`.
The colon-qualified form (`livespec-orchestrator-beads-fabro:drive`)
```

---

**2. SPECIFICATION/scenarios.md — §"Scenario: /skills picker exposes plugin skills by short name"** (3 tokens)

2a. Replace this exact current line (line 25):

```
And searches for "orchestrate"
```

with:

```
And searches for "drive"
```

2b. Replace this exact current line (line 26):

```
Then the picker renders "orchestrate (livespec-orchestrator-beads-fabro)"
```

with:

```
Then the picker renders "drive (livespec-orchestrator-beads-fabro)"
```

2c. Replace this exact current line (line 29, note the two leading spaces):

```
  "livespec-orchestrator-beads-fabro:orchestrate" form
```

with:

```
  "livespec-orchestrator-beads-fabro:drive" form
```

(The scenario's `Given ... livespec-orchestrator-beads-fabro plugins are installed` line and the scenario `## ` heading are UNCHANGED — those are plugin-name / section-title references, not the skill-name token.)

---

**3. SPECIFICATION/non-functional-requirements.md — §"Enforcement suite", `check-codex-skill-picker` bullet** (2 tokens)

Replace this exact current text (lines 66–67):

```
  `List skills`, searches `orchestrate`, and fails unless the picker
  renders the `orchestrate (livespec-orchestrator-beads-fabro)` Skill row.
```

with:

```
  `List skills`, searches `drive`, and fails unless the picker
  renders the `drive (livespec-orchestrator-beads-fabro)` Skill row.
```

---

Rationale for what is NOT changed: the plugin name `livespec-orchestrator-beads-fabro` (spelled with "orchestrator") is retained in every reference; no incidental English use of "orchestrate/orchestration" exists in these files; there is no `orchestrate plan` composition reference in this repo (that was beads-fabro-specific) and hence no "formerly `orchestrate`" historical reference to preserve here.
