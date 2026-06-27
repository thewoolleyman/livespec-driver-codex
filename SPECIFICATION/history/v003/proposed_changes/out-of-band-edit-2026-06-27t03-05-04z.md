---
topic: out-of-band-edit-2026-06-27t03-05-04z
author: livespec-doctor
created_at: 2026-06-27T03:05:04Z
---

## Proposal: out-of-band-edit-2026-06-27t03-05-04z

doctor detected drift between HEAD-active spec content and the
HEAD-history-vN snapshot; this auto-backfill records the active
state as the new canonical version.

### Proposed Changes

```diff
--- history/vN/contracts.md
+++ active/contracts.md
@@ -30,7 +30,7 @@
   source of truth for the description.
 
 This is the Driver-local, Codex-shaped realization of livespec core's
-`contracts.md` §"Plugin distribution", which owns the cross-cutting rule
+`contracts.md`, which owns the cross-cutting rule
 that plugin and marketplace share the value `livespec` by deliberate
 choice (renaming either flows through a core propose-change cycle). The
 subdir layout (`livespec/` plugin dir, `.codex-plugin/plugin.json`,
@@ -51,8 +51,7 @@
   have no allowed-tools surface).
 
 No extra skill directories may exist, and none of the eight may be
-missing. The operation *set* is a core contract (`livespec/SPECIFICATION/spec.md`
-§"Sub-command lifecycle"); this contract governs the Driver-local
+missing. The operation *set* is a core contract (`livespec/SPECIFICATION/spec.md`); this contract governs the Driver-local
 binding directories that realize it.
 
 Each binding body MUST carry the Codex core-resolution invocation
@@ -125,7 +124,7 @@
 parser rejects it). The bundle's *existence and wiring* are this repo's
 contract; each hook's *behavioral disciplines and postures* (the fail-open
 requirement, deny-vs-warn, the gating predicates) are owned upstream by
-`livespec/SPECIFICATION/contracts.md` §"Driver-shipped hooks", which this
+`livespec/SPECIFICATION/contracts.md`, which this
 repo realizes. The script implementations and their unit tests live in
 THIS repo (`tests/hooks/`).
 
@@ -180,9 +179,8 @@
 content embeds a markdown checkbox task queue (`[ ]`/`[x]` list items) at
 or above a mechanical threshold, instead of deriving status from the
 work-item ledger. It realizes the livespec core
-`non-functional-requirements.md` §"Planning Lane guidance" → "No shadow
-ledger" rule, per the core `contracts.md` §"Driver-shipped hooks" (v140)
-contract. WARN-ONLY: it emits a `{"systemMessage": ...}` advisory on
+`non-functional-requirements.md` "No shadow ledger" rule, per the core
+`contracts.md` (v140) contract. WARN-ONLY: it emits a `{"systemMessage": ...}` advisory on
 stdout and NEVER a blocking `decision`, NEVER exits non-zero, and NEVER
 auto-edits; it fails OPEN (silent exit 0) on any malformed stdin,
 `stop_hook_active` re-entry, or missing/unreadable transcript. The body
@@ -201,7 +199,7 @@
 
 Adding or removing a hook, renaming a hook surface, or changing the
 hook's posture requires a propose-change cycle against the upstream
-§"Driver-shipped hooks" contract; the mechanical detection internals
+contract; the mechanical detection internals
 (segment tokenization, the primary-checkout probe) are Driver
 implementation detail and MAY be tuned without a spec cycle, provided the
 postures hold.
@@ -211,6 +209,5 @@
 `plugin.json.version` is the single source of truth for the shipped
 Driver plugin's version and is auto-managed by `release-please` from
 per-commit Conventional Commits. `marketplace.json` MUST NOT carry a
-`version` field. This mirrors livespec core's `contracts.md`
-§"Plugin versioning"; the Driver follows the same release mechanism for
+`version` field. This mirrors livespec core's `contracts.md`; the Driver follows the same release mechanism for
 its own plugin artifact.
--- history/vN/non-functional-requirements.md
+++ active/non-functional-requirements.md
@@ -22,8 +22,7 @@
   → PR → merge → cleanup path; the primary checkout refuses direct
   commits/pushes. The hook body and its doctor fingerprint invariant are
   owned by `livespec/SPECIFICATION/non-functional-requirements.md`
-  §"Primary-checkout commit-refuse hook" and `livespec/SPECIFICATION/contracts.md`
-  §"`primary-checkout-commit-refuse-hook-installed`". This repo carries a
+  and `livespec/SPECIFICATION/contracts.md`. This repo carries a
   copy of the canonical scaffold under `dev-tooling/`; it does not
   re-specify it.
 - **Toolchain pinning** via `mise`; **`uv`** as the Python toolchain
--- history/vN/spec.md
+++ active/spec.md
@@ -17,8 +17,7 @@
 A **Driver** is the thin, agent-runtime-specific wrapper through which a
 human drives the livespec spec lifecycle interactively. `livespec-driver-codex`
 is the Codex-runtime Driver under livespec's contract-plus-reference-
-implementations architecture (per `livespec/SPECIFICATION/spec.md`
-§"Contract + reference implementations architecture"). It binds livespec
+implementations architecture (per `livespec/SPECIFICATION/spec.md`). It binds livespec
 core's harness-neutral material to ONE tool runtime — Codex.
 
 This repo ships exactly three things, all Codex-runtime mechanics:
@@ -60,10 +59,8 @@
 exit codes, and wire contracts; the JSON schemas; the built-in templates;
 the eight sub-command *names* and any rename (those require a core
 propose-change cycle); and the hook *disciplines and postures* (fail-open
-contract, deny-vs-warn) — those live in `livespec/SPECIFICATION/contracts.md`
-§"Driver-shipped hooks". The family-standard primary-checkout commit-refuse
-hook is likewise core-owned (`livespec/SPECIFICATION/non-functional-requirements.md`
-§"Primary-checkout commit-refuse hook"); this repo carries the scaffold but
+contract, deny-vs-warn) — those live in `livespec/SPECIFICATION/contracts.md`. The family-standard primary-checkout commit-refuse
+hook is likewise core-owned (`livespec/SPECIFICATION/non-functional-requirements.md`); this repo carries the scaffold but
 does not re-specify it.
 
 Upstream-wins: when a rule here conflicts with livespec core's
@@ -72,8 +69,7 @@
 ## Terminology
 
 The family vocabulary is defined upstream in `livespec/SPECIFICATION/spec.md`
-§"Terminology" and §"Contract + reference implementations architecture";
-this tree uses it without redefinition. The terms that recur here:
+§"Terminology"; this tree uses it without redefinition. The terms that recur here:
 
 - **Driver** — the thin, agent-runtime-specific wrapper (this repo, for
   Codex). Core is agnostic to it.
```
