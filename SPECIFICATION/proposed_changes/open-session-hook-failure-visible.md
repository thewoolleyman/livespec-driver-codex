---
topic: open-session-hook-failure-visible
author: claude:codex-plugin-hook-path-regression
created_at: 2026-11-08T01:58:34Z
---

## Proposal: An already-open session's hook failures after a covered plugin's content change are visible, and a new session runs every hook

### Target specification files

- SPECIFICATION/scenarios.md
- SPECIFICATION/contracts.md
- SPECIFICATION/non-functional-requirements.md

### Summary

Revise the ratified scenario that says an already-open Codex session keeps running a covered plugin's hooks after the plugin's installed content changes but its hooks do not. A live measurement showed it is false on current Codex. The new rule: a session started after reconciliation runs every hook, and its PreToolUse guard denies, while each hook that an already-open session cannot run is reported in that session as a visible hook failure rather than skipped silently. The same proposal corrects the two 'long-running hooks survive' scenarios, which make the same claim for the active session. No heading is renamed, because the heading-coverage debt ratchet refuses renaming a heading that carries debt; the misnamed heading is renamed when its integration test lands. It adds a contract paragraph stating that re-established trust reaches only sessions started after it, and that the Driver MUST NOT suppress an open session's hook failure. It also clarifies the real transition test's trust check, which appears twice, so no unamended statement contradicts the change.

### Motivation

This change is filed under plan livespec-3rfjga (livespec repo, plan codex-plugin-hook-path-regression). That plan reworded its assertions 1 and 6 on 2026-11-08T01:34:53Z, as a scope decision endorsed by legacy-coordinator-agent under R301, to: a fresh session runs every hook; an already-open session's failure is visible. This proposal brings the Driver's ratified scenario into line with that decision.

The measurement is leg A of that plan, recorded in the livespec repo at plan/codex-plugin-hook-path-regression/research/leg-a-keep-original-bytes-result.md. On the dev host, an interactive Codex TUI (codex-cli 0.166.0) was opened at 19:44:53Z on 2026-11-07, before Driver 0.12.2 was published, while the vps-info codex-hook-trust stopgap was stopped. Before the upgrade, the guard probe was blocked by livespec_footgun_guard.py. After `just ensure-codex-plugins` moved the Driver from 0.12.1 to 0.12.2 with no manual step, the same session reported "Hook failed: plugin contents changed; hook approval required". A `git commit --no-verify` probe then ran unblocked, stopped only by the sandbox's read-only .git. Restoring the original 0.12.1 bytes at the superseded path changed nothing. A fresh `codex exec` in the same directory ran every hook, and the guard blocked the probe. Path continuity held for both hook-declaring plugins. The correct trust value was already in config.toml when the open session failed: a port of Codex's fingerprint gives the same sha256 as the trusted_content_hash on all nine Driver hook entries.

Codex's source at rust-v0.166.0 (codex-rs/hooks/src/engine/plugin_trust.rs) re-hashes the plugin root on every hook execution and compares it with the hash on the handler. It is unchanged at rust-v0.167.0 and on main as read on 2026-11-07. Between the 0.12.1 and 0.12.2 payloads, only .codex-plugin/plugin.json differs, so every Driver release does this to every open session. No Driver change can meet the old wording, and an upstream fix has no ETA.

The fail-open itself is tracked as livespec-driver-codex-sjwyha and is not changed by this proposal. Fleet scope: a sweep of every clone under /data/projects on its default branch found this scenario's wording only in livespec-driver-codex. No other Codex Driver consumer carries it. Downstream, after ratification, by owner edit: the host-captured bullet of livespec-driver-codex-b5rhjf, which still requires the already-open session to run its hooks with its guard blocking, is restated to the new rule. The References lines of b5rhjf and livespec-driver-codex-sjwyha and b5rhjf's governing-heading metadata name the unchanged heading and need no edit until the follow-up rename.

### Proposed Changes

### Amendment 1 — the already-open-session scenario

In `SPECIFICATION/scenarios.md`, replace this exact text (verbatim, including its line breaks):

```markdown
## Scenario: an already-open session keeps running its hooks after a covered plugin's installed content changes but its hooks do not

```gherkin
Given an already-open Codex session captured hook commands of a covered plugin
And Codex trusted that plugin's hooks
And the plugin's installed payload then changes, through a new release or through Codex re-materializing the same version, while every hook definition and hook entrypoint stays byte-identical to the plugin's release tag for the installed version
And Codex withdraws its trust in that plugin's hooks
When explicit provisioning or the persistent observer completes reconciliation
Then each retained hook path of that plugin resolves through latest to the validated current payload
And Codex trusts that plugin's hooks again, re-established only after the hook definitions and entrypoints were verified against the plugin's release tag
And the already-open session's next turn runs those hooks with no hook failure and no trust prompt
And where that plugin ships a PreToolUse safety guard, that guard denies a forbidden command in that session again rather than failing open
And Codex's hook-trust bypass was not used and no hook was disabled
```
```

with:

```markdown
## Scenario: an already-open session keeps running its hooks after a covered plugin's installed content changes but its hooks do not

```gherkin
Given an already-open Codex session captured hook commands of a covered plugin
And Codex trusted that plugin's hooks
And the plugin's installed payload then changes, through a new release or through Codex re-materializing the same version, while every hook definition and hook entrypoint stays byte-identical to the plugin's release tag for the installed version
And Codex withdraws its trust in that plugin's hooks
When explicit provisioning or the persistent observer completes reconciliation
Then each retained hook path of that plugin resolves through latest to the validated current payload
And Codex trusts that plugin's hooks again, re-established only after the hook definitions and entrypoints were verified against the plugin's release tag
And a Codex session started after that reconciliation runs those hooks with no hook failure and no trust prompt
And where that plugin ships a PreToolUse safety guard, that guard denies a forbidden command in the session started after that reconciliation
And each of those hooks that the already-open session cannot run is reported in that session as a visible hook failure, not skipped silently
And Codex's hook-trust bypass was not used and no hook was disabled
```
```

The heading does NOT change, although it still names the behaviour that was measured false. This repository's heading-coverage debt ratchet (`check-heading-coverage-debt-register`, ratified: "renaming cannot reset debt") refuses a rename of a heading that carries a registered `TODO`, and this heading does. The heading MUST be renamed to match its body in the same change that replaces its `TODO` coverage row with a real integration-tier test, which retires the debt. A follow-up work item in livespec-driver-codex carries that rename and is filed at ratification.

The revise MUST co-edit, in the same commit:

- `tests/heading-coverage.json`: in this heading's entry, keep `heading` and `test` (`TODO`), set `work_item` to `livespec-driver-codex-b5rhjf`, and replace `reason` with one naming the integration tier, for example: "TODO integration tier: an integration-tier test is owed by livespec-driver-codex-b5rhjf (a session started after a content-only change and release-tag-verified re-trust runs a covered plugin's hooks and its PreToolUse guard denies, while the already-open session reports each hook it cannot run as a visible hook failure; the test MUST capture the open session's visible output, because Codex does not write the hook-failure text to the rollout file; the heading is renamed to match the body when this test lands)". The `reason` MUST NOT cite livespec-driver-codex-v52m6a, which was regroomed into livespec-driver-codex-b5rhjf.
- `tests/heading-coverage-debt.json`: in this heading's entry, set `work_item` to `livespec-driver-codex-b5rhjf`, and keep `heading` and `first_seen` unchanged.

### Amendment 2 — the Driver cache-update scenario (drift sweep)

In `SPECIFICATION/scenarios.md`, in `## Scenario: long-running hooks survive a Driver cache update`, replace this exact line:

```text
And the session's Stop hooks execute successfully
```

with:

```text
And a Codex session started after that reconciliation runs the Driver's Stop hooks successfully
And each Driver hook that the active session cannot run is reported in that session as a visible hook failure, not skipped silently
```

### Amendment 3 — the any-covered-plugin cache-update scenario (drift sweep)

In `SPECIFICATION/scenarios.md`, in `## Scenario: long-running hooks survive a cache update of any covered plugin`, replace this exact line:

```text
And the session's next turn ends with no hook failure
```

with:

```text
And a Codex session started after that reconciliation runs that plugin's hooks with no hook failure
And each of that plugin's hooks that the active session cannot run is reported in that session as a visible hook failure, not skipped silently
```

Neither heading changes. In each, "survive" is carried by the path-continuity line ("every ... retained hook path ... resolves through latest to ... validated current payload"), which still holds. Neither amendment adds, renames or removes a `## ` heading, so neither touches a coverage manifest.

### Amendment 4 — the open-session limit of trust continuity

In `SPECIFICATION/contracts.md`, §"Codex hook-cache compatibility", replace this exact text (verbatim, including its line breaks), which ends the paragraph beginning "Hook continuity for a covered plugin requires both path continuity":

```text
reconciler MUST NOT claim hook continuity for a covered plugin while
either half is missing.
```

with:

```text
reconciler MUST NOT claim hook continuity for a covered plugin while
either half is missing.

Where Codex re-verifies a plugin's installed content before every hook
run, as codex-cli 0.166.0 does, re-established trust reaches only the
Codex sessions that start after it. In a session already open when a
covered plugin's installed content changes, that verification keeps
failing after trust is re-established, so that session cannot run the
plugin's hooks again. This was observed with a correct new trust record
and byte-identical hook definitions and entrypoints, and restoring the
original bytes at the superseded version's path was observed not to
restore them. A version bump alone changes the installed content,
because it changes the plugin manifest. The Driver MUST NOT claim hook
continuity for an already-open session. Its obligation to such a
session is that the failure stays visible: the Driver MUST NOT disable,
remove, or bypass a hook, or otherwise act, to suppress the hook
failure Codex reports in that session. A host that satisfies (a) above
for every covered plugin still leaves each already-open session running
tools without that plugin's PreToolUse guards, visibly, until the
session is restarted.
```

### Amendment 5 — the real transition test (drift sweep)

In `SPECIFICATION/non-functional-requirements.md`, replace this exact text (verbatim, including its two-space indentation and line breaks):

```text
  which that setting is not enabled reported. The real transition test
  MUST also verify that Codex treats each retained hook as trusted after
  reconciliation.
```

with:

```text
  which that setting is not enabled reported. The real transition test
  MUST also verify that a Codex session started after reconciliation
  treats each retained hook as trusted.
```

and replace this exact text (verbatim, including its line breaks):

```text
untrusted, a host on which that setting is not enabled reported. The
real transition test MUST also verify that Codex treats each retained
hook as trusted after reconciliation.
```

with:

```text
untrusted, a host on which that setting is not enabled reported. The
real transition test MUST also verify that a Codex session started after
reconciliation treats each retained hook as trusted.
```

### Not changed

The trust-continuity paragraph's (a), (b) and (c) disjuncts, the rule that a host MUST NOT leave sessions running tools with a covered plugin's guards silently off, and the scenario `a covered plugin whose hook trust cannot be safely re-established is reported, not trusted` stand as written. An already-open session's guards are off visibly, not silently, so that rule still holds.

