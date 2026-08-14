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

Extend `contracts.md` §"Hook bundle" with a `Codex hook-cache compatibility` contract. The Driver MUST provide a cache-independent host reconciler and a persistent update observer, both owned outside the replaceable `<cache>/<marketplace>/<plugin>/<version>` tree. The ordinary `ensure-codex-plugins` provisioner MUST run the reconciler after its successful marketplace upgrade and plugin-install sequence, and MUST verify that the observer is enabled and healthy. The observer MUST notice Codex-native startup auto-upgrades that bypass the provisioner, wait until the new Driver cache payload is complete, then run the same reconciler.

The reconciler MUST discover the actual versioned hook cache from measured cache state and declared hook commands; it MUST NOT treat `codex plugin list` `source.path` as a versioned hook location. Before changing aliases, it MUST validate the current payload's manifest, hooks registration, and every declared PreToolUse and Stop Python hook using the bare interpreter form Codex executes. It MUST maintain a one-hop topology `old-version -> latest -> current-version`, atomically retarget `latest` only after validation, preserve complete real version directories, refuse unsafe or malformed existing links loudly, and backfill only bounded version names recorded by the Driver's release/cache state. It MUST be idempotent and MUST report a failed repair as a provisioning/observer failure rather than claiming hook continuity.

Extend `constraints.md` to forbid locating the reconciler, observer executable, or its durable version-state record solely inside the Codex-managed plugin cache, and to forbid deleting or replacing a complete real version directory while reconciling. Extend `non-functional-requirements.md` §"Test discipline" so the delivery includes a deterministic mock-cache integration test plus a real release-tracking transition that starts a session with an old Driver hook path, advances the marketplace/plugin cache, and verifies each retained hook path resolves to the validated current payload. Add `## Scenario: long-running hooks survive a Driver cache update` to `scenarios.md`: Given an active session captured hook commands under an older Driver version and the marketplace advances, when explicit provisioning or the persistent observer completes reconciliation, then every declared retained hook path resolves through `latest` to the validated current payload and the session's Stop hooks execute successfully. The resulting revise MUST add the scenario's `tests/heading-coverage.json` entry, mapped to an integration-tier test or a TODO whose reason explicitly names the integration tier.
