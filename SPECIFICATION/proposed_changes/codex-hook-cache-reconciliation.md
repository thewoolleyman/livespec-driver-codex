---
topic: codex-hook-cache-reconciliation
author: codex
created_at: 2026-08-14T04:19:39Z
spec_commitments:
  impl_followups:
    - id_hint: codex-hook-cache-reconciliation
      description: |
        Implement and release the Codex Driver's cache-independent compatibility reconciler and host watcher, wire it into explicit provisioning, and prove both deterministic cache and real old-session upgrade behavior.
---

## Proposal: Cache-independent hook compatibility reconciliation

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Require the Codex Driver to preserve declared hook paths for long-running sessions across explicit and startup marketplace updates by reconciling bounded version aliases from a host location that is not itself replaced by Codex's plugin-cache update.

### Motivation

Codex startup auto-upgrade can load hook commands from a versioned cache and then delete or replace that cache during the same session. On 2026-08-14 an active livespec Driver session retained Stop-hook paths under 0.6.0 after the cache advanced to 0.6.1, causing every Stop hook to fail until a compatibility chain was restored manually. The Driver provisioner currently has no post-update reconciliation.

### Proposed Changes

Extend `contracts.md` §"Hook bundle" with a new `### Codex hook-cache compatibility` H3 subsection nested under that existing H2 (not a new top-level `## ` heading, so this edit needs no additional `tests/heading-coverage.json` entry beyond the scenario heading below). This subsection MUST state plainly that the reconciler and observer are NOT members of the four-script hook bundle the H2's opening enumeration and "The bundle carries FOUR hooks." sentence describe, and MUST NOT touch either of those two sentences. The Driver MUST provide a cache-independent host reconciler and a persistent update observer, delivered as `dev-tooling/`-owned executables — repo-level tooling in the same location and installation path as the existing `ensure-codex-plugins` provisioner, never copied into or run from the Codex-managed plugin cache — so their operative copies are inherently outside the replaceable `<cache>/<marketplace>/<plugin>/<version>` tree without requiring any bundle-contents exception. The ordinary `ensure-codex-plugins` provisioner MUST run the reconciler after its successful marketplace upgrade and plugin-install sequence, and MUST verify that the observer is enabled and healthy. The observer MUST notice Codex-native startup auto-upgrades that bypass the provisioner, wait until the new Driver cache payload is complete, then run the same reconciler.

For its own hook-cache discovery step only, the reconciler MUST discover the actual versioned hook cache from measured cache state and declared hook commands, and MUST NOT treat `codex plugin list` `source.path` as a versioned hook location; this prohibition governs the reconciler's discovery step alone and does not alter the Driver's existing core-root resolution order (`contracts.md` §"Core-root resolution"), which legitimately reads `source.path` for a different purpose. Before changing aliases, the reconciler MUST validate the current payload's manifest, hooks registration, and every declared PreToolUse and Stop Python hook using the bare interpreter form Codex executes. It MUST maintain a one-hop topology `old-version -> latest -> current-version`, atomically retarget `latest` only after validation, preserve complete real version directories, refuse unsafe or malformed existing links loudly, and backfill only bounded version names recorded by the Driver's release/cache state. It MUST be idempotent and MUST report a failed repair as a provisioning/observer failure rather than claiming hook continuity.

Extend `constraints.md` to forbid locating the reconciler, observer executable, or its durable version-state record solely inside the Codex-managed plugin cache, and to forbid deleting or replacing a complete real version directory while reconciling. Because the reconciler and observer are `dev-tooling/`-owned rather than plugin-bundle contents (per the contracts.md edit above), the existing "The Driver bundle ships NO `scripts/` tree and NO wrapper CLIs... The bundle ships bindings, the footgun-guard hook, and the manifest only" sentence stays UNAMENDED and remains true — this proposal MUST NOT edit that sentence or the `non-functional-requirements.md` repo-layout row describing the `livespec/` bundle, since neither describes `dev-tooling/` and neither is contradicted by executables that live outside the bundle.

Extend `non-functional-requirements.md` §"Test discipline" as a standing suite requirement (not a one-time delivery note). Re-derive and update the section's opening "Two test surfaces back the enforcement suite" sentence to "Three test surfaces" and name the new `tests/dev-tooling/` surface (mirroring `tests/e2e-cli/` and `tests/hooks/`, matching the reconciler/observer's `dev-tooling/` location): it MUST include a deterministic mock-cache integration test covering discovery, validation, one-hop retargeting, and idempotent rerun, plus a real release-tracking transition test — starting a session against an old Driver hook path, advancing the marketplace/plugin cache, and verifying each retained hook path resolves to the validated current payload — gated host-aware in the same manner as the existing live TUI picker acceptance test (skipped on GitHub-hosted CI unless the runner explicitly opts in, run where Codex is present and authenticated). In the same edit, update §"Repo layout"'s `dev-tooling/` row to add the reconciler and observer executables alongside the existing `check_plugin_structure.py` entry, and add a `tests/dev-tooling/` row for the new test surface — both rows currently omit these paths, which do not yet exist.

Proposal note, not resulting spec text: live-exercise evidence from running the real-transition test against an actual old-session upgrade is separately required as the impl_followups item's post-merge acceptance evidence per this repo's "done means rolled out and exercised live" discipline. This obligation belongs on the ledger work item, not in the ratified `non-functional-requirements.md` text, and the resulting revise MUST NOT add it there.

Add `## Scenario: long-running hooks survive a Driver cache update` to `scenarios.md`: Given an active session captured hook commands under an older Driver version and the marketplace advances, when explicit provisioning or the persistent observer completes reconciliation, then every declared retained hook path resolves through `latest` to the validated current payload and the session's Stop hooks execute successfully. The resulting revise MUST add the scenario's `tests/heading-coverage.json` entry, mapped to an integration-tier test or a TODO whose reason explicitly names the integration tier.
