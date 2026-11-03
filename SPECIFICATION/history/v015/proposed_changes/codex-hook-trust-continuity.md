---
topic: codex-hook-trust-continuity
author: claude-opus-5-5
created_at: 2026-11-03T01:01:52Z
spec_commitments:
  impl_followups:
    - id_hint: codex-hook-trust-continuity
      description: |
        Filed as livespec-driver-codex-v52m6a. Extend the Codex hook-cache reconciler and observer with trust continuity. Whenever Codex does not trust a covered plugin's installed hooks, including after Codex re-materializes the same version, detect it and verify the installed payload's declared hook definitions and hook entrypoints against the plugin's release tag in its source repository, then re-establish Codex hook trust for those hooks; never trust an unverified payload, never use --dangerously-bypass-hook-trust, and never disable a hook. Detect an unrecognized Codex trust-record format and fail loudly without writing. Make ensure-codex-plugins and the observer health report name every covered plugin with installed but untrusted hooks, loudly, as a failure. Before choosing a mechanism, measure whether hooks provisioned as Codex managed hooks (managed-requirements key allow_managed_hooks_only) are exempt from per-plugin content-hash trust. Codex 0.166.0 has no setting that refuses tool execution while a configured hook is untrusted (see openai/codex#41979 and openai/codex#58011); if a later Codex release adds one, make host provisioning enable it and make ensure-codex-plugins report a host where it is not enabled. Prove it with the mock-cache integration test, the real transition test, and live evidence that an already-open session keeps running its hooks across a content-only release, with the footgun guard blocking a forbidden command again after reconciliation.
---

## Proposal: Hook continuity requires Codex hook-trust continuity for every covered plugin

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Make Codex hook trust part of the hook-continuity contract in `contracts.md` §"Codex hook-cache compatibility". Hook continuity for a covered plugin will require both path continuity, which the existing one-hop alias rules provide, and trust continuity. Because Codex's trust follows a plugin's installed bytes rather than its release, the obligation is a condition, not an upgrade event: whenever Codex does not trust a covered plugin's installed hooks, the reconciler re-establishes Codex hook trust only after verifying the installed payload's hook definitions and hook entrypoints against that plugin's release tag, never by trusting the cache. It never uses Codex's hook-trust bypass, never disables a hook, fails loudly on a trust-record format it does not recognize, and the provisioner and observer report installed-but-untrusted hooks loudly instead of reporting the plugin healthy. Trust continuity is framed as a safety invariant: at least one of release-verified re-trust, a fail-closed host setting, or (where Codex offers no such setting) a loud unhealthy report must hold. A covered plugin with no identifiable release tag is reported and never trusted by the Driver. The stale "Trust model" paragraph, which recommends the bypass, is replaced, and matching constraints, test obligations, and two scenarios are added.

### Motivation

The ratified contract (history v014) gives a covered plugin path continuity: hook paths an open session captured under an older version keep resolving, in one hop through `latest`, to the validated current payload. On 2026-11-03, on the livespec dev host running Codex 0.166.0, path continuity held and hooks still failed, because Codex no longer trusted them.

The measured facts are these.

1. Codex persists hook trust in `~/.codex/config.toml`, in tables named `[hooks.state."<plugin>@<marketplace>:hooks/hooks.json:<event>:<i>:<j>"]`. Each table carries two fields. `trusted_hash` is specific to one hook definition. `trusted_content_hash` is identical across every hook of one plugin, so it is a hash over the whole plugin's content rather than over the hook.
2. The `livespec-orchestrator-beads-fabro` marketplace upgrade from 0.276.2 to 0.277.0 (release v0.277.0, at 00:49:37Z) left the orchestrator's `hooks/` tree byte-identical, yet it invalidated trust: the recorded `trusted_content_hash` no longer matched. Three symptoms followed. An already-open session, whose 0.276.2 hook paths still resolved through the one-hop alias, showed `Hook failed — plugin contents changed; hook approval required`. Fresh `codex exec` sessions reported the orchestrator's two `SessionStart` hooks and its one `Stop` hook as Failed. A fresh interactive TUI prompted "Hooks need review — 3 hooks are new or changed", offering Review, "Trust all and continue", and "Continue without trusting (hooks won't run)".
3. Trust was then re-established after verification. The cached 0.277.0 `hooks/hooks.json` and every hook script it names were byte-compared against the git tag v0.277.0, and the hooks were trusted through Codex's own review interface; only `trusted_content_hash` changed. The SAME already-open session then ran its next turn with no hook failure. Open sessions therefore re-read trust state, and alias continuity plus re-established trust is sufficient for an open session to keep running its captured hooks.
4. Trust can be withdrawn with no version change at all. On 2026-11-03 at 02:00:30Z, on a second host (a MacBook Pro), Codex re-materialized the SAME orchestrator version 0.277.0, rewriting its `cache-manifest.json` and `api-configurable-keys.json`, and trust broke again. That host's `trusted_content_hash` for 0.277.0 (`bfa6f569…`) differs from the dev host's (`29a25c7e…`) for the same version. Codex's trust therefore follows a plugin's installed bytes, not its release, and an observer that reacts only to version changes would miss it.
5. An untrusted PreToolUse safety guard FAILS OPEN. This was measured on 2026-11-03 at 01:00Z on the same host and Codex version. A scratch `CODEX_HOME` held a copy of the real `config.toml` in which ONLY the Driver's `trusted_content_hash` values were invalidated. `codex exec` was asked to run `git commit --allow-empty --no-verify -m failopen-probe .`. It reported `hook: PreToolUse Failed` three times, and the shell command EXECUTED: git ran, and exited 1 only because of the probe's own `.` pathspec. With the real, trusted configuration, the same command was BLOCKED by `livespec_footgun_guard.py`. Codex's own prompt says the same thing in plainer words: untrusted hooks "won't run". A per-invocation `-c hooks.state....` configuration override does not affect trust evaluation, so there is no per-session workaround either. That was also measured at about 01:00Z: a calibration run with `-c hooks.state."livespec-orchestrator-beads-fabro@livespec-orchestrator-beads-fabro:hooks/hooks.json:stop:0:0".trusted_content_hash="sha256:0…"` still showed every `Stop` and `SessionStart` hook Completed, so the override was ignored by trust evaluation. After any change to a covered plugin's installed content, whether a release or a re-materialization, that plugin's safety guards are therefore silently OFF on every host until trust is re-established, and today that happens only when a human notices and re-trusts by hand. Trust continuity is a safety invariant, not a convenience.
6. Codex 0.166.0 has NO fail-closed setting for untrusted hooks; this was measured separately on the same host. Its only trust-related key is `bypass_hook_trust`, the configuration form of `--dangerously-bypass-hook-trust`, which must never be used. Upstream, openai/codex#41979 asks for opt-in fail-closed handling of PreToolUse failures, and openai/codex#58011 reports hook trust being invalidated by upgrades. Codex also has a managed-requirements key, `allow_managed_hooks_only`. If managed (administrator) hooks are exempt from per-plugin content-hash trust, provisioning the Driver's guards as managed hooks could remove the trust churn entirely, but that exemption is not yet measured.
7. Codex offers `--dangerously-bypass-hook-trust`. It is not an acceptable remedy, because it disables a safety control for every hook, not only for the hooks that were verified. The current `contracts.md` §"Hook bundle" "Trust model" paragraph nevertheless tells a headless invocation to use that flag and declares trust "a Codex runtime concern, not a Driver contract". That paragraph is stale drift once trust is part of hook continuity.

Every covered plugin is exposed, including the Driver's own payload, whose guards are the ones measured failing open above: any change to any byte of a plugin's installed payload, including a change unrelated to hooks and a re-materialization of the same version, can untrust all of that plugin's hooks on the host where it happens. Trusting whatever the cache holds would close the gap by trusting unverified code, so the remedy must verify the payload's hooks against the plugin's released artifact before trusting them.

### Proposed Changes

In `contracts.md` (no `## ` heading changes in `contracts.md`):

1. In §"Hook bundle", replace this paragraph verbatim:

   ```
   Trust model: Codex prompts once to trust a plugin's hooks in interactive
   sessions; a headless invocation needs `--dangerously-bypass-hook-trust`
   to run the guard without the trust prompt. The trust posture is a Codex
   runtime concern, not a Driver contract.
   ```

   with:

   > Trust model: Codex runs a plugin's hooks only while it trusts them, and it records that trust in the host's Codex configuration. For every covered plugin, the Driver's own payload included, re-establishing that trust whenever Codex does not trust the plugin's installed hooks is part of hook continuity and is governed by §"Codex hook-cache compatibility" below. The Driver MUST NOT use or recommend Codex's hook-trust bypass (`--dangerously-bypass-hook-trust`) in any shipped or provisioning surface as a remedy for untrusted hooks, because the bypass disables a safety control.

2. In §"Codex hook-cache compatibility" (the H3 under §"Hook bundle"), insert five new paragraphs immediately after the paragraph that ends with this text, quoted verbatim:

   ```
   version-state record. It MUST be idempotent and MUST report a failed
   repair as a provisioning/observer failure rather than claiming hook
   continuity.
   ```

   and immediately before the paragraph that begins "Each covered plugin's durable version-state record and observer status record MUST be keyed by the plugin's marketplace and plugin name." The five paragraphs are:

   > Hook continuity for a covered plugin requires both path continuity, which the one-hop alias topology above provides, and trust continuity, which means Codex trusts that plugin's currently installed hooks. Codex's trust follows a plugin's installed bytes, not its release: Codex can withdraw its trust in every hook of a plugin when any part of the installed payload changes, even when the hook definitions and hook entrypoints are byte-identical to the previously trusted release, and even with no version change, for example when Codex re-materializes the same version and rewrites the plugin's cache metadata. Trust continuity is a safety invariant: an untrusted hook does not run, so the tool call an untrusted PreToolUse guard would have guarded proceeds unguarded. Whenever Codex does not trust a covered plugin's installed hooks, at least one of the following MUST hold: (a) Codex trust in those hooks is re-established from release-verified bytes, as the next paragraph requires; (b) the host fails closed, as the fail-closed fallback paragraph below requires; (c) where (b) does not hold, the loud unhealthy report that the fail-closed fallback paragraph requires is emitted. A host MUST NOT leave Codex sessions running tools with a covered plugin's guards silently off until a human notices. The reconciler MUST NOT claim hook continuity for a covered plugin while either half is missing.
   >
   > The observer MUST detect, for every covered plugin, both lost Codex trust and cache content rewritten at an unchanged version, not only version changes and Codex-native auto-upgrades, and MUST run the reconciler for that plugin when it detects either. It MUST restore trust, or emit the report required below, within a bounded latency that the implementation states and its tests verify. Whenever Codex does not trust a covered plugin's installed hooks, the reconciler MUST attempt to re-establish Codex hook trust for those hooks, and it MUST do so only after verifying the installed payload's declared hook definitions, and every hook entrypoint they declare, against that plugin's released artifact: the release tag, in the plugin's source repository, that corresponds to the installed version. Trust MUST NOT be established on the strength of the cache contents alone. The verification applies whether or not a hook definition changed relative to the previously trusted release, and a hook whose definition changed MUST NOT be trusted on any other basis. A payload that cannot be verified, because its released artifact cannot be identified or obtained or because any declared hook definition or entrypoint differs from that artifact, MUST NOT be trusted. It MUST be reported as a provisioning or observer failure naming the plugin and each unverified hook, exactly as a failed path repair is. In particular, a covered plugin for which no release tag corresponding to its installed version can be identified, such as a third-party plugin whose source repository publishes none, MUST be reported in that way and MUST NEVER be trusted by the Driver. The reconciler MUST NOT use Codex's hook-trust bypass, and it MUST NOT disable or remove a hook to clear a trust failure.
   >
   > Re-establishing trust depends on Codex's hook-trust record format, which is an external surface that any Codex release may change. The invariant is trust continuity from release-verified bytes, not any particular mechanism: whether the Driver re-establishes trust through an interface Codex provides, by writing Codex's trust records, or by provisioning the hooks through a Codex mechanism that does not subject them to per-plugin content-hash trust is an implementation choice. Whatever the mechanism, every hook whose trust the Driver establishes or provisions MUST be byte-identical to the release-verified hook definitions and entrypoints. The reconciler, the observer, and `ensure-codex-plugins` MUST recognize the format of the host's Codex trust records before reading trust status from them or writing them. When any of them does not recognize that format, it MUST NOT write any trust state, MUST treat that plugin's hooks as untrusted, and MUST fail loudly, as a provisioning or observer failure naming the plugin. Trust that an operator grants through Codex's own review interface is not governed by this contract.
   >
   > `ensure-codex-plugins` and the observer's health report MUST report a covered plugin whose hooks are installed but not trusted by Codex loudly, as a failure, naming the plugin and each untrusted hook, and MUST NOT report that plugin healthy.
   >
   > Fail-closed fallback. If Codex exposes a setting that refuses tool execution while a configured hook is untrusted, host provisioning MUST enable it, and `ensure-codex-plugins` MUST report a host on which it is not enabled. Whenever the host does not fail closed, because Codex exposes no such setting or because the setting is not enabled, the Driver MUST report untrusted covered hooks as unhealthy through `ensure-codex-plugins` and the observer health check, naming the plugin and each untrusted hook, and each such report MUST state that Codex will run tools without that plugin's guards until trust is re-established, and the Driver MUST NOT describe those guards as active anywhere. In either case, the Driver and host provisioning MUST NOT use or recommend Codex's hook-trust bypass (`--dangerously-bypass-hook-trust`, or its configuration key `bypass_hook_trust`).

   The existing isolation rule ("A reconcile failure for one covered plugin MUST NOT prevent reconciliation of the others") is kept unchanged; because the trust step is part of reconciling a plugin, it also covers a trust failure.

In `constraints.md` §"Forbidden patterns", append four bullets after the last existing bullet, which ends "inside that directory, any entry other than the `latest` link and a bounded version-name alias link.":

- "Using Codex's hook-trust bypass (`--dangerously-bypass-hook-trust`), or disabling or removing a hook, to restore or report hook continuity for a covered plugin (`contracts.md` §\"Codex hook-cache compatibility\")."
- "Re-establishing Codex hook trust for a covered plugin's hooks without first verifying the installed payload's hook definitions and hook entrypoints against that plugin's release tag."
- "Reading trust status from, or writing, a Codex hook-trust record in a format that the reconciler, the observer, or `ensure-codex-plugins` does not recognize."
- "Leaving disabled a Codex setting that refuses tool execution while a configured hook is untrusted, on a host whose Codex exposes one."

In `non-functional-requirements.md`:

- §"Enforcement suite", in the `check-dev-tooling` bullet, after the sentence ending "verifies each retained hook path resolves to the validated current payload.", insert: "The mock-cache integration test MUST also cover trust continuity: detection and repair within the stated latency, trust lost with no content change (a trust record removed or edited) detected and repaired, trust re-established only for a payload whose hook definitions and entrypoints match the plugin's release tag, a payload that differs from or cannot be verified against that tag left untrusted and reported, lost trust detected and repaired at an unchanged version after cache content is rewritten, a covered plugin with no identifiable release tag reported and never trusted, an unrecognized trust-record format failing loudly with no trust state written, a covered plugin with installed but untrusted hooks reported rather than reported healthy, and, where Codex exposes a setting that refuses tool execution while a configured hook is untrusted, a host on which that setting is not enabled reported. The real transition test MUST also verify that Codex treats each retained hook as trusted after reconciliation."
- §"Test discipline", in the `tests/dev-tooling/` paragraph, after the sentence ending "and verifies each retained hook path resolves to the validated current payload.", insert the same two sentences.

In `scenarios.md`, amend the two existing hook-cache scenarios so they hold only for a plugin whose trust can be re-established (headings unchanged):

- In `## Scenario: long-running hooks survive a Driver cache update`, after the line "And the marketplace advances to a newer Driver version", insert the Given line "And the Driver's hook definitions and hook entrypoints match its release tag for the new version". Before the line "And the session's Stop hooks execute successfully", insert the Then line "And Codex trusts the Driver's hooks, and any trust the Driver re-established was established only after that verification".
- In `## Scenario: long-running hooks survive a cache update of any covered plugin`, after the line "And the marketplace advances that plugin to a newer version, deleting the older version directory", insert the Given line "And that plugin's hook definitions and hook entrypoints match its release tag for the new version". Before the line "And the session's next turn ends with no hook failure", insert the Then line "And Codex trusts that plugin's hooks, and any trust the Driver re-established was established only after that verification".

Then add the following two scenarios after `## Scenario: long-running hooks survive a cache update of any covered plugin`:

`## Scenario: an already-open session keeps running its hooks after a covered plugin's installed content changes but its hooks do not`

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

`## Scenario: a covered plugin whose hook trust cannot be safely re-established is reported, not trusted`

```gherkin
Given a covered plugin whose hook trust cannot be verified, because its current payload declares a hook definition or hook entrypoint that differs from the plugin's release tag for the installed version, because no release tag corresponding to the installed version can be identified, or because the host's Codex trust records are in a format the Driver does not recognize
When explicit provisioning or the persistent observer reconciles that plugin
Then the Driver establishes no Codex trust for that plugin's hooks and writes no Codex trust state for them
And the failure is reported as a provisioning or observer failure naming the plugin and each affected hook
And ensure-codex-plugins does not report that plugin healthy
And where Codex exposes a setting that refuses tool execution while a configured hook is untrusted, that setting is enabled, so no tool runs with that plugin's guards silently off
And whenever the host does not fail closed, the plugin is reported unhealthy and the report states that Codex will run tools without that plugin's guards until trust is re-established
And Codex's hook-trust bypass is neither used nor recommended
And every other covered plugin is still reconciled
```

The resulting revise MUST add a `tests/heading-coverage.json` entry for each of the two new scenario headings, spelled `../tests/heading-coverage.json` in `resulting_files[]`. Each entry MUST map either to an integration-tier test or to a `TODO` whose `reason` explicitly names the integration tier, and its `work_item` MUST be `livespec-driver-codex-v52m6a`, the work item filed for this proposal's `codex-hook-trust-continuity` impl follow-up. As in v014, the revise MUST also regenerate `tests/heading-coverage-debt.json`, spelled `../tests/heading-coverage-debt.json` in `resulting_files[]`, so any TODO entries are registered there; each debt-register row for the two new scenarios MUST cite `livespec-driver-codex-v52m6a` as its work item. The revise MUST also update the existing `reason` of the `tests/heading-coverage.json` entries for `## Scenario: long-running hooks survive a Driver cache update` and `## Scenario: long-running hooks survive a cache update of any covered plugin`, whose current text describes only path continuity, so that each names the trust assertion the amended scenario adds (Codex trusts the plugin's hooks, and any Driver-established trust followed release-tag verification) and the impl follow-up work item that owes the test for it, `livespec-driver-codex-v52m6a`; the updated entry for `## Scenario: long-running hooks survive a Driver cache update` MUST cite `livespec-driver-codex-v52m6a` as its work item. No other `## ` heading in any spec file is added, renamed, or removed.

Proposal notes, not resulting spec text:

- Live-exercise evidence is the impl follow-up's post-merge acceptance evidence. That evidence is an already-open Codex session surviving a change to a covered plugin's installed content that changed the plugin's content hash but not its hooks (an upgrade, a re-materialization of the same version, or both), with the session's next turn running the plugin's hooks with no hook failure, after the Driver's reconciliation alone re-established trust. It belongs on the ledger work item, and the revise MUST NOT add it to the ratified text.
- Codex 0.166.0 was measured to expose no setting that refuses tool execution while a configured hook is untrusted (motivation item 6). The fail-closed clause is worded conditionally so the ratified text stays correct when a later Codex release adds one, for example in response to openai/codex#41979; the loud unhealthy report is the operative fallback until then.
- Before choosing a trust-continuity mechanism, the implementation MUST measure whether hooks provisioned as Codex managed (administrator) hooks, under the managed-requirements key `allow_managed_hooks_only`, are exempt from per-plugin content-hash trust. If they are, provisioning the Driver's guards that way may remove the trust churn entirely. This is a lead to measure, not a mechanism this proposal adopts; the contract text above stays mechanism-neutral, and any chosen mechanism still has to run only release-verified bytes.
- The third-party consequence of the verification rule is now ratified text, not a note: a covered plugin with no identifiable release tag is reported and never trusted by the Driver. That is deliberate. Under clause (c), the loud unhealthy report is what satisfies the safety invariant for such a plugin on a Codex with no fail-closed setting. An untagged third-party covered plugin therefore yields a permanently unhealthy report, by design, until its source repository publishes a matching release tag or the operator removes it.
