---
topic: supervisor-completion-gate
author: codex:driver-supervisor-completion-gate
created_at: 2026-11-03T20:31:33Z
---

## Proposal: Topic-scoped supervisor completion gate

### Target specification files

- SPECIFICATION/spec.md
- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md
- SPECIFICATION/constraints.md

### Summary

Specify the Driver-owned supervisor completion Stop gate and its topic-scoped failure posture, preventing unrelated and legacy repository markers from continuing unsupervised sessions while preserving fail-closed supervision.

### Motivation

The maintainer authorized the owning spec amendment and ratification for livespec-driver-codex-waq5mp, the priority-1 expedited incident plan dependency. A session without an identified supervision topic must ignore repository markers; an identified supervisor must retain structured completion and independent wake-producer obligations without reading foreign runtime state.

### Proposed Changes

Apply the following contract and scenario changes atomically. The hook MUST keep topic ownership separate from marker validity; invalid owned evidence continues only its identified supervisor.

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -107,15 +107,16 @@
 ## Hook bundle
 
 The Driver SHIPS a Codex hook bundle at `livespec/hooks/`: a `hooks.json`
-registration plus four fail-open scripts — the `livespec_footgun_guard.py`
+registration with PreToolUse guards and Stop hooks, including the `livespec_footgun_guard.py`
 PreToolUse guard, the `block_auto_memory.py` PreToolUse guard, the
 `no_shadow_ledger.py` Stop hook, and the `codex_background_memory_audit.py`
-Stop hook. Codex consumes
+Stop hook, together with the `supervisor_completion_gate.py` Stop gate specified
+in §"Supervisor completion gate". Codex consumes
 the Claude hook I/O formats, so the guard reads
 `{"tool_name": "Bash", "tool_input": {"command": "..."}}` on stdin and
 emits a `hookSpecificOutput.permissionDecision: "deny"` payload to
-deny a call (empty stdout + exit 0 lets it through), and the Stop hook
-reads `{"transcript_path": "...", "stop_hook_active": ...}` on stdin and
+deny a call (empty stdout + exit 0 lets it through), and the warning Stop hooks
+read `{"transcript_path": "...", "stop_hook_active": ...}` on stdin and
 emits a `{"systemMessage": "..."}` WARNING (empty stdout passes silently).
 A guard is **Bash-matched** when any matcher it is registered on is `Bash`.
 The runtime MUST start every Bash-matched PreToolUse guard, for a `Bash` call,
@@ -154,13 +155,15 @@
 the scripts are Driver-owned and live in the Driver bundle, and the
 substitution works for Codex hooks.
 `hooks.json` MUST NOT carry a top-level `description` key. The bundle's *existence and wiring* are this repo's
-contract; each hook's *behavioral disciplines and postures* (the fail-open
+contract; each family-standard hook's *behavioral disciplines and postures* (the fail-open
 requirement, deny-vs-warn, the gating predicates) are owned upstream by
 `livespec/SPECIFICATION/contracts.md`, which this
-repo realizes. The script implementations and their unit tests live in
+repo realizes. The Driver-owned background-memory audit and supervisor
+completion gate are governed by this tree. The script implementations and their unit tests live in
 THIS repo (`tests/hooks/`).
 
-The bundle carries FOUR hooks.
+The following paragraphs specify the family-standard guards and warning hooks;
+the Driver-owned supervisor completion gate is specified separately below.
 
 A **PreToolUse** guard on `Bash` that DENIES only patterns that are never
 legitimate in the livespec family, each with an actionable message naming
@@ -298,8 +301,8 @@
 family-standard `livespec_footgun_guard.py`, `block_auto_memory.py`, and
 `no_shadow_ledger.py` hooks — whose postures are owned upstream — the cycle
 runs against the upstream `livespec/SPECIFICATION/contracts.md`; for the
-Codex-specific, Driver-owned `codex_background_memory_audit.py` hook, which
-has no upstream posture owner, the cycle runs against THIS tree. The
+Codex-specific, Driver-owned `codex_background_memory_audit.py` and
+`supervisor_completion_gate.py` hooks, the cycle runs against THIS tree. The
 mechanical detection internals
 (segment tokenization, the primary-checkout probe) are Driver
 implementation detail and MAY be tuned without a spec cycle, provided the
@@ -308,14 +311,14 @@
 ### Codex hook-cache compatibility
 
 The reconciler and persistent observer required below are NOT members
-of the four-script hook bundle above and are not shipped inside
+of the plugin hook bundle above and are not shipped inside
 `livespec/hooks/` — they are `dev-tooling/`-owned executables,
 repo-level tooling in the same location and installation path as the
 existing `ensure-codex-plugins` provisioner, never copied into or run
 from the Codex-managed plugin cache. Their operative copies are
 therefore inherently outside the replaceable
 `<cache>/<marketplace>/<plugin>/<version>` tree without requiring any
-exception to "The bundle carries FOUR hooks." above.
+exception to the plugin hook-bundle contract above.
 
 The Driver MUST provide a cache-independent host reconciler and a
 persistent update observer. The reconciler and observer cover every
@@ -558,6 +561,69 @@
 installation of the shipped definition is that host's provisioning step;
 a definition generated or hand-written for that host is not.
 
+## Supervisor completion gate
+
+The Driver MUST ship `supervisor_completion_gate.py` as a self-contained Codex
+Stop hook. It MUST emit a Codex-compatible `{"decision":"block","reason":...}`
+response when continuation is required, and otherwise emit empty stdout, always
+exiting zero. Completion evidence MUST come from structured supervisor state
+and independently checked wake-producer evidence, never assistant final-response
+text or pane text. This is Driver-owned runtime behavior.
+
+The hook MUST determine the current session's supervision topic from explicit
+runtime context (`supervisor_topic`, or the compatibility alias `topic`). The
+canonical field takes precedence whenever present, including when blank; the
+alias is consulted only when the canonical field is absent. A named supervised
+session MUST deliver its topic through Driver session-scoped context even when
+the native Stop input omits these extension fields. Repository marker discovery
+MUST NOT substitute for that transport. An absent or blank topic means
+that the session is not identified as supervising: the hook MUST allow the turn
+to end without discovering or reading repository supervisor markers. A supplied
+non-string topic or nonblank topic that is not a single path component other
+than `.` or `..` MUST continue the session without probing any marker path.
+The hook MUST NOT derive topic ownership from the mere presence of a marker.
+
+For an identified topic, the hook MUST inspect only
+`tmp/overseer/<topic>/.supervisor-state` beneath the governed repository's
+primary checkout, resolved from the configured `livespec.primaryPath` when
+available and otherwise the discovered governed project root. An identified
+topic whose governed root cannot be resolved MUST continue without probing
+marker paths. Of supervisor markers, the gate MUST read only the owned one.
+It MAY independently read the authoritative producer registry and process
+identity evidence described below. It MUST refuse path traversal and symlink escapes from that topic's
+runtime subtree. It MUST NOT read or change another topic's marker, regardless
+of whether that foreign marker is active, malformed or legacy non-JSON state.
+A marker MUST be a structured JSON object whose topic matches the identified
+topic. Missing, unreadable, malformed, legacy non-JSON or mismatched owned
+evidence MUST continue the supervised session; it MUST NOT silently disable the
+gate. A valid owned marker with `supervision_active` explicitly false permits
+completion regardless of age; freshness applies only while it is true. Missing
+or malformed activation state MUST continue the session.
+
+While the owned marker has `supervision_active` true, completion MUST require a
+fresh marker (`updated_at`), an empty `open_obligations` array, and a terminal
+`completion_disposition` object whose `kind` is either `plan-complete` without a
+`question` or `maintainer-blocking` with exactly one nonempty `question` ending
+in a single `?`. A valid freshness timestamp MUST include its timezone and MUST be no more than
+24 hours old or five minutes in the future. Unknown or malformed completion or
+producer evidence MUST continue the session. Local wake producers MUST have a
+live PID whose observed command line matches both the expected command and
+identity. Forge/CI or ledger producers MUST have their `registered_producer_identity`
+independently present in the authoritative producer registry. The registry MAY
+be shared at `tmp/overseer/.wake-producers.json` or held in the owned topic
+subtree; it MUST NOT be inferred from a foreign topic marker. Every accepted wake producer
+MUST name cold-open reentry through the owned marker and a fresh authoritative
+ledger, forge or CI query; a promise to check later is insufficient.
+
+The exact real-user command `stop supervising <topic>` for the identified topic
+MUST allow completion even when its owned evidence is missing, unreadable,
+malformed, legacy non-JSON, stale or mismatched. Assistant
+messages, tool results, ordinary user messages, and objective-replacement requests
+MUST NOT be treated as that override. On `stop_hook_active` reentry the gate MUST
+allow completion without inspecting markers, avoiding recursive Stop blocking.
+An unexpected failure while evaluating an identified topic MUST continue that
+session rather than grant completion.
+
 ## Versioning
 
 `plugin.json.version` is the single source of truth for the shipped

--- a/SPECIFICATION/spec.md
+++ b/SPECIFICATION/spec.md
@@ -28,7 +28,8 @@
    resolves livespec core at runtime, reads core's operation prose, and
    dispatches the config-named spec-side CLI.
 2. **A plugin-shipped hook bundle** under `livespec/hooks/` —
-   `hooks.json` plus a fail-open `PreToolUse` footgun guard. This is
+   `hooks.json` plus PreToolUse guards, warning Stop hooks, and a
+   topic-scoped supervisor completion Stop gate. This is
    Driver-owned runtime surface (unlike the prose and CLIs, which are
    core's).
 3. **A structural gate** (`dev-tooling/check_plugin_structure.py`) that
@@ -58,8 +59,10 @@
 restates them: the operation prose contents; the wrapper-CLI surfaces,
 exit codes, and wire contracts; the JSON schemas; the built-in templates;
 the eight sub-command *names* and any rename (those require a core
-propose-change cycle); and the hook *disciplines and postures* (fail-open
-contract, deny-vs-warn) — those live in `livespec/SPECIFICATION/contracts.md`. The family-standard primary-checkout commit-refuse
+propose-change cycle); and the family-standard hook *disciplines and postures* (fail-open
+contract, deny-vs-warn) — those live in `livespec/SPECIFICATION/contracts.md`.
+Codex-specific hook behavior, including the supervisor completion gate, is
+Driver-owned and governed by this tree. The family-standard primary-checkout commit-refuse
 hook is likewise core-owned (`livespec/SPECIFICATION/non-functional-requirements.md`); this repo carries the scaffold but
 does not re-specify it.
 

--- a/SPECIFICATION/scenarios.md
+++ b/SPECIFICATION/scenarios.md
@@ -330,3 +330,103 @@
 Then the older observer error does not fail provisioning for that plugin
 And ensure-codex-plugins starts no observer process
 ```
+
+## Scenario: an unidentified session ignores repository supervisor markers
+
+```gherkin
+Given no nonblank supervision topic identifies the current Codex session
+And the repository contains active, malformed and legacy non-JSON supervisor markers
+When the supervisor completion Stop gate evaluates the session
+Then it permits completion with empty stdout and exit zero
+And it does not discover, read or change those markers
+```
+
+## Scenario: a supervised session inspects only its owned marker
+
+```gherkin
+Given the current session is identified as supervising topic "repair"
+And another topic has a malformed legacy supervisor marker
+And the repair topic has valid completion and independently verified wake-producer evidence
+When the supervisor completion Stop gate evaluates the session
+Then it permits completion without reading or changing the foreign marker
+And it consults only the owned marker and independent authoritative producer evidence
+And an absent native Stop topic field does not lose the named session context
+And an owned marker whose topic differs from "repair" instead continues the session
+```
+
+## Scenario: invalid supervision paths never inspect foreign runtime state
+
+```gherkin
+Given explicit supervision context contains a non-string topic, a path traversal topic or a topic whose runtime subtree escapes through a symlink
+When the supervisor completion Stop gate evaluates the session
+Then it continues the session with a Codex-compatible block response and exit zero
+And an identified topic whose governed primary root is unresolved also continues without marker reads
+And it does not read or change a marker outside the identified topic's runtime subtree
+```
+
+## Scenario: missing or malformed owned evidence continues supervision
+
+```gherkin
+Given the session is identified as supervising one topic
+When its owned marker is missing, unreadable, malformed or legacy non-JSON
+Or its marker is stale while supervision_active is true
+Or its activation state or topic is missing, malformed or mismatched
+Then the supervisor completion gate continues the session with a block response and exit zero
+And a valid owned marker whose supervision_active is explicitly false permits completion regardless of age
+```
+
+## Scenario: terminal completion still requires independent wake evidence
+
+```gherkin
+Given an owned structured marker has supervision_active true
+When its freshness timestamp is absent, timezone-free, older than 24 hours or more than five minutes in the future
+Or it retains open obligations, a nonterminal disposition or malformed evidence
+Or its local producer has no matching live process or its forge or ledger producer identity is not independently registered
+Or its producer lacks cold-open reentry through the owned marker and a fresh authoritative query
+Then the supervisor completion gate continues the session
+And it accepts a fresh empty-obligation marker only with independently verified producer evidence and either plan-complete without a question or maintainer-blocking with exactly one question
+```
+
+## Scenario: only a real-user scoped stop command overrides supervision
+
+```gherkin
+Given the session is identified as supervising topic "repair" with incomplete owned evidence
+When the latest real-user message is exactly "stop supervising repair"
+Then the supervisor completion gate permits completion even when its owned marker is missing or malformed
+And assistant messages, tool results, ordinary user messages, objective-replacement requests and stop commands for another topic do not override supervision
+```
+
+## Scenario: Stop reentry does not recursively block completion
+
+```gherkin
+Given the Stop input has stop_hook_active true
+When the supervisor completion gate evaluates it
+Then it permits completion without inspecting any repository supervisor marker
+```
+
+## Scenario: canonical supervision context takes precedence over the compatibility alias
+
+```gherkin
+Given explicit runtime context contains a blank supervisor_topic and a nonblank topic alias
+When the supervisor completion gate resolves ownership
+Then it treats the session as unidentified without inspecting supervisor markers
+And it consults the topic alias only when supervisor_topic is absent
+```
+
+## Scenario: an unexpected supervised evaluation failure cannot grant completion
+
+```gherkin
+Given the session is identified as supervising one topic
+When an unexpected failure prevents evaluation of its owned completion evidence
+Then the supervisor completion gate emits a block response and exits zero
+```
+
+## Scenario: assistant and pane text cannot substitute for completion evidence
+
+```gherkin
+Given the identified supervisor retains an open obligation in its owned marker
+And assistant final-response or pane text claims completion
+When the supervisor completion gate evaluates the session
+Then it continues the session based on structured evidence
+And the completion claim supplies no evidence and no real-user override
+```

--- a/SPECIFICATION/constraints.md
+++ b/SPECIFICATION/constraints.md
@@ -25,8 +25,8 @@
   filtering, formatting, a confirmation dialogue, or an opt-in flag — all
   such logic lives in the backing core wrapper.
 - The Driver bundle ships NO `scripts/` tree and NO wrapper CLIs: those
-  are core-owned and resolved at runtime. The bundle ships bindings, the
-  footgun-guard hook, and the manifest only.
+  are core-owned and resolved at runtime. The bundle ships bindings, the hook bundle specified by contracts.md,
+  and the manifest; it MUST NOT vendor core prose or wrapper CLIs.
 
 ## Resolution-substrate constraints
 
```
