---
topic: codex-hook-cache-all-plugins
author: claude:codex-plugin-hook-path-regression
created_at: 2026-11-02T14:39:23Z
spec_commitments:
  impl_followups:
    - id_hint: codex-hook-cache-all-plugins
      description: |
        Generalize the Codex hook-cache reconciler and observer from the Driver's own payload to every hook-declaring plugin installed from a Codex-registered marketplace. Discover hooks the way Codex does, isolate per-plugin state and status, ship a supervisor definition for the observer, and prove the behaviour with the mock-cache test and the real old-session transition test.
---

## Proposal: Hook-cache compatibility for every hook-declaring Codex plugin

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Widen `contracts.md` §"Codex hook-cache compatibility" from the Driver's own payload to every plugin that a Codex host installs from a marketplace registered in its Codex configuration and whose installed payload declares hooks. Hooks are discovered by the same two routes Codex uses. Each plugin's alias state and observer status are isolated from every other plugin's. The observer ships with a service-supervisor definition, so it can run without any session having started it.

### Motivation

The ratified contract (history v007) reconciles only the `livespec-driver-codex` payload. On 2026-11-02, Codex seats on the livespec dev host showed `Hook failed / No such file or directory (os error 2)` at every turn end. `livespec-orchestrator-beads-fabro` had gained a Codex `Stop` hook in its v0.261.0 release. Each orchestrator marketplace upgrade then deleted the versioned directory that running sessions had captured: `0.274.2` was replaced by `0.275.0` at 2026-11-02T14:22:13Z with no alias, while sessions started under earlier versions were still running. The Driver cache, which the shipped observer covers, was intact.

The shipped reconciler could not simply be pointed at the orchestrator. Its payload validation refuses any payload whose `.codex-plugin/plugin.json` lacks a `hooks` entry. The orchestrator declares its hooks only in the default `hooks/hooks.json`, which Codex loads anyway; the host's `~/.codex/config.toml` `[hooks.state]` table lists the orchestrator's `hooks/hooks.json` entries. Separately, the observer's status record is located by the state file's directory. A second instance whose state file shares that directory therefore read the Driver observer's heartbeat and reported itself healthy without starting.

The ledger record is livespec bug `livespec-gqjkge`, under plan `codex-plugin-hook-path-regression` (livespec epic `livespec-3rfjga`).

### Proposed Changes

In `contracts.md` §"Codex hook-cache compatibility" (the H3 under §"Hook bundle"; no `## ` heading changes in `contracts.md`):

1. Replace the paragraph beginning "The Driver MUST provide a cache-independent host reconciler and a persistent update observer." with text stating the following.
   - The reconciler and observer cover every **covered plugin**. A covered plugin is installed in the Codex plugin cache from a marketplace registered in the host's Codex configuration, and its current installed payload declares at least one hook.
   - The covered set MUST be derived from measured Codex configuration and cache state on every reconcile, never from a list fixed in code or configuration. A plugin that first declares a hook in a later release is therefore covered with no Driver change.
   - Plugin caches that Codex manages from its own curated sources, rather than from a registered marketplace, are outside the covered set.
   - The ordinary `ensure-codex-plugins` provisioner MUST run the reconciler for every covered plugin after its successful marketplace upgrade and plugin-install sequence, and MUST verify that the observer is running and healthy.
   - The observer MUST notice Codex-native startup auto-upgrades of any covered plugin, wait until that plugin's new cache payload is complete, then run the same reconciler for that plugin.
   - The observer MUST be event-driven or, failing that, poll no more often than every 2 seconds, so that it is not a steady CPU load on the host.
2. In the following paragraph:
   - Keep the `source.path` prohibition and its §"Core-root resolution" carve-out verbatim.
   - Replace "the current payload's manifest, hooks registration, and every declared PreToolUse and Stop Python hook" with "the current payload's hook declarations and every hook entrypoint they declare, for every hook event". Hook declarations are discovered by both routes Codex honours: the manifest's `hooks` entry when present, and otherwise the payload's default `hooks/hooks.json`. A payload that declares neither is not a covered plugin. It is not a validation failure.
   - A declared hook command whose entrypoint the reconciler cannot resolve to a path inside the payload MUST fail the reconcile for that plugin loudly, naming the plugin and the command. Hook continuity MUST NOT be claimed for that plugin.
   - Replace "backfill only bounded version names recorded by the Driver's release/cache state" with "backfill only bounded version names recorded in that plugin's own version-state record".
   - Keep the sentence about `pretooluse_dispatch.py` and its guard modules: the Driver's own payload remains a covered plugin.
3. Add a paragraph stating the isolation rules.
   - Each covered plugin's durable version-state record and observer status record MUST be keyed by the plugin's marketplace and plugin name.
   - A health report for one plugin MUST NOT be satisfied by another plugin's, or another observer instance's, status record.
   - A reconcile failure for one covered plugin MUST NOT prevent reconciliation of the others, and MUST be reported as a provisioning or observer failure naming that plugin.
4. Add a paragraph on supervision.
   - The Driver MUST ship a service-supervisor definition for the observer (a systemd user unit on Linux). With it, host provisioning can keep the observer running across host reboots without any Codex or Claude session starting it.
   - `ensure-codex-plugins` MUST report, not silently tolerate, an observer that is running unsupervised.
   - Installing that definition on a host is the host-provisioning automation's responsibility, not the Driver provisioner's.

In `constraints.md`, amend the bullet "Locating the Codex hook-cache compatibility reconciler, observer executable, or its durable version-state record solely inside the Codex-managed plugin cache" so that it reads "...or any covered plugin's durable version-state or observer status record...". Add a bullet forbidding the reconciler from creating, retargeting or deleting any path inside a plugin cache directory that is not a covered plugin's version root.

In `non-functional-requirements.md`, make three edits.
- §"Test discipline": extend the `tests/dev-tooling/` sentence so the deterministic mock-cache integration test also covers:
  - a covered plugin whose hooks are declared only by the default `hooks/hooks.json`;
  - two covered plugins reconciled together with isolated state and status;
  - a covered plugin with an unresolvable hook command failing loudly while a sibling plugin still reconciles.
  
  Extend the real release-tracking transition test so it runs over every covered plugin installed on the host, not only the Driver.
- §"Enforcement suite": update the `check-dev-tooling` bullet's description to match.
- §"Repo layout": update the `dev-tooling/` row to name the shipped service-supervisor definition.

In `scenarios.md`, add `## Scenario: long-running hooks survive a cache update of any covered plugin`:

```gherkin
Given an active Codex session captured hook commands under an older version of a covered plugin that is not the Driver
And that plugin declares its hooks only in its default hooks/hooks.json
And the marketplace advances that plugin to a newer version, deleting the older version directory
When the persistent observer completes reconciliation
Then every retained hook path of that plugin resolves through latest to its validated current payload
And the session's next turn ends with no hook failure
```

The resulting revise MUST add this scenario's `tests/heading-coverage.json` entry, mapped either to an integration-tier test or to a TODO whose reason explicitly names the integration tier. The existing Driver scenario `## Scenario: long-running hooks survive a Driver cache update` is kept unchanged.

Proposal note, not resulting spec text: live-exercise evidence is the impl_followups item's post-merge acceptance evidence. It consists of a real old Codex session surviving an orchestrator marketplace upgrade with no hook failure, plus the observer running after a host reboot. That obligation belongs on the ledger work item and the livespec plan `codex-plugin-hook-path-regression`. The revise MUST NOT add it to the ratified text.
