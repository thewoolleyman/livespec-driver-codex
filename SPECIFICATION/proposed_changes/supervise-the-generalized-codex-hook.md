---
topic: supervise-the-generalized-codex-hook
author: claude-opus-5-5
created_at: 2026-11-03T02:13:25Z
---

## Proposal: Supervise the generalized Codex hook-cache observer on every supported platform, including macOS launchd

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Generalize the observer-supervision paragraph of `contracts.md` §"Codex hook-cache compatibility" (under `## Hook bundle`) from Linux-only to every supported platform. On macOS the Driver ships a launchd user LaunchAgent beside the systemd unit; each definition supervises one observer covering every covered plugin and names no marketplace or plugin, and the macOS definition resolves its interpreter on both Apple Silicon and Intel Macs. `ensure-codex-plugins` reports, by exiting non-zero and naming the observer, an observer not running under the installed supervisor definition even while a detached observer is alive, and it never signals the supervisor's observer or starts a second one, including when that observer reports a reconcile error. Observer health becomes per covered plugin and is withheld until that plugin's own status record carries a completed first reconcile, on every platform. Installing a definition stays host provisioning's job, with an operator-run install of the shipped definition as the provisioning step for a host without automation. Matching forbidden patterns, test obligations, and three scenarios are added.

### Motivation

The ratified contract (history v014, `contracts.md` §"Codex hook-cache compatibility" under `## Hook bundle`) states supervision only for Linux: the Driver ships a systemd user unit, and "where the platform has no supervisor" `ensure-codex-plugins` says so. The shipped `dev-tooling/ensure-codex-plugins.sh` on `origin/master` does exactly that on macOS: with no `systemctl`, it prints "Codex hook-cache observer has no supported supervisor on this platform." and exits 0. A Mac therefore has no supervised observer and no failing check.

That gap was measured. The affected MacBook Pro had no hook-cache observer running, its plugin-cache aliases were lost, and one Codex thread accumulated about 1,883 references each to three missing Driver 0.8.3 Stop scripts. The same failure class had already broken every Codex tool call on the control node on 2026-10-23, while its observer was an unsupervised background process.

Draft PR livespec-driver-codex#921 tried to provision a launchd observer and was closed as superseded on 2026-11-02 after an independent review found four blockers (posted on #921). Its defects are architectural and must be ruled out by the contract, not just by one implementation: the ensure path SIGTERMed launchd's own observer and spawned a detached duplicate when the observer looked unhealthy; it covered only the Driver, with a hardcoded state root and heartbeat names; it generated the definition at runtime instead of shipping it; it accepted health before the first reconcile; and it hardcoded a `/opt/homebrew` interpreter that exists only on Apple Silicon. The health gap is not macOS-only: the shipped single-plugin observer loop writes a status record at startup, before its first reconcile, so a health check reading that record can pass before any repair has happened.

Work item `livespec-driver-codex-yudufr` was re-cut on 2026-11-02 to state these behaviours. On 2026-11-03 at 02:04Z the factory held it at the spec-change tier: its spec-stated judgement reported the asked-for behaviour partial and named `## Hook bundle` as the heading to generalize, linked to this topic. This proposal states the macOS half, the no-takeover rule for `ensure-codex-plugins`, and the per-plugin first-reconcile health rule, while keeping supervisor installation with host provisioning as v014 ratified.

Ledger references: livespec epic `livespec-3rfjga` and bug `livespec-gqjkge` (both in repo livespec, plan `codex-plugin-hook-path-regression`).

### Proposed Changes

In `contracts.md` §"Codex hook-cache compatibility" (the H3 under §"Hook bundle"; no `## ` heading changes in `contracts.md`):

1. Replace this paragraph, quoted verbatim from `origin/master` (it is the last paragraph of the H3):

   ```
   The Driver MUST ship a service-supervisor definition for the observer;
   on Linux this is a systemd user unit. With it, host provisioning can
   keep the observer running across host reboots without any Codex or
   Claude session starting it. `ensure-codex-plugins` MUST report an
   observer whose process is not running under the installed supervisor
   unit; where the platform has no supervisor, it MUST say so rather than
   report the observer as supervised. Installing that definition on a
   host, and enabling user-session lingering so that the unit runs with no
   login session, are the host-provisioning automation's responsibility,
   not the Driver provisioner's.
   ```

   with these four paragraphs:

   > The Driver MUST ship a service-supervisor definition for the observer on each supported platform: on Linux a systemd user unit, and on macOS a launchd user LaunchAgent, shipped beside the systemd unit. Each definition supervises one observer that reconciles every covered plugin, and neither names a marketplace or a plugin. With it, host provisioning can keep the observer running without any Codex or Claude session starting it: on Linux across host reboots, and on macOS from each login session onward, across reboots and logout/login. The macOS definition MUST resolve the observer's Python interpreter correctly on both Apple Silicon and Intel Macs; it MUST NOT depend on an interpreter location that exists on only one of them.
   >
   > `ensure-codex-plugins` checks supervision; it does not take supervision over. It MUST report an observer whose process is not running under the platform's installed supervisor definition by exiting non-zero and naming the hook-cache observer, including when no definition is installed on a platform that has a supported supervisor, and it MUST do so even while an observer process that the supervisor did not start is alive. Where the platform has no supported supervisor, it MUST say so rather than report the observer as supervised. While the supervisor's observer is running, `ensure-codex-plugins` MUST NOT signal that process and MUST NOT start a second observer, including when that observer's status record reports a reconcile error. It reports that error instead, as a provisioning or observer failure naming the plugin, and exits non-zero.
   >
   > Observer health is reported per covered plugin. An observer that has started but has not completed its first reconcile of a covered plugin MUST be reported unhealthy for that plugin, and MUST NOT be reported healthy for that plugin until that plugin's own status record carries a completed reconcile that reported no error; a status record written before that first reconcile, such as a startup heartbeat, MUST NOT satisfy the health report. This is a necessary condition for health, not a sufficient one: any other rule in this section that reports the plugin unhealthy still applies. This holds on every platform.
   >
   > Installing a supervisor definition on a host, and on Linux enabling user-session lingering so that the unit runs with no login session, are the host-provisioning automation's responsibility, not the Driver provisioner's: neither `ensure-codex-plugins` nor a plugin install installs, loads, or replaces a supervisor definition as a side effect. Where no provisioning automation exists for a host, an operator-run installation of the shipped definition is that host's provisioning step; a definition generated or hand-written for that host is not.

In `constraints.md` §"Forbidden patterns", insert two bullets immediately after this existing bullet, quoted verbatim:

```
- Deleting or replacing a complete real version directory while the
  reconciler is reconciling hook-cache aliases.
```

and immediately before the bullet beginning "Creating, retargeting or deleting, while reconciling hook-cache aliases". The two bullets are:

- "Signalling the supervisor's hook-cache observer, or starting a second observer, from `ensure-codex-plugins` while the supervisor's observer is running (`contracts.md` §\"Codex hook-cache compatibility\")."
- "Installing, loading or replacing a hook-cache observer supervisor definition as a side effect of `ensure-codex-plugins` or of a plugin install."

In `non-functional-requirements.md`:

- §"Repo layout", in the `dev-tooling/` row, replace "the observer's shipped service-supervisor definition (a systemd user unit on Linux)" with "the observer's shipped service-supervisor definitions (a systemd user unit on Linux and a launchd user LaunchAgent on macOS)".
- §"Enforcement suite", in the `check-dev-tooling` bullet, replace the parenthetical "(discovery, validation, one-hop retargeting, idempotent rerun)", which follows "reconciler/observer" and wraps across one line break in the source, so that it reads "(discovery, validation, one-hop retargeting, idempotent rerun, per-plugin observer health before and after the first reconcile, and the provisioner's supervisor check on each supported platform)".
- §"Test discipline", in the `tests/dev-tooling/` paragraph, replace this span, quoted verbatim:

  ```
  reconciled together with isolated state and status, and a covered
  plugin with a missing entrypoint failing loudly while a sibling plugin
  still reconciles;
  ```

  with:

  ```
  reconciled together with isolated state and status, a covered
  plugin with a missing entrypoint failing loudly while a sibling plugin
  still reconciles, an observer reported unhealthy for a covered plugin
  until that plugin's own status record carries a completed first
  reconcile, a static assertion over the shipped macOS supervisor
  definition that its interpreter resolution depends on no interpreter
  location present on only one of Apple Silicon and Intel Macs, and the
  provisioner's supervisor check on each supported platform (an
  observer not running under the installed supervisor definition
  reported even while a detached observer is alive, an observer with
  no installed definition reported, and a running supervised observer
  whose status record reports a reconcile error reported with a
  non-zero exit but neither signalled nor duplicated);
  ```

In `scenarios.md`, append the following three scenarios at the end of the file, after the last existing scenario `## Scenario: a delegating host's push gates on the remote executor and refuses on no verdict`, which is kept unchanged:

`## Scenario: on macOS ensure-codex-plugins reports an observer not running under the installed LaunchAgent`

```gherkin
Given a macOS host whose host provisioning installed the Driver's shipped LaunchAgent for the hook-cache observer
And the observer is not running under that LaunchAgent
And a detached observer process that launchd did not start is alive
When ensure-codex-plugins runs
Then it exits non-zero
And its report names the hook-cache observer as not running under the installed LaunchAgent
And it does not report the observer as supervised

Given a macOS host on which no LaunchAgent definition for the hook-cache observer is installed
When ensure-codex-plugins runs
Then it exits non-zero
And its report names the hook-cache observer as not running under an installed LaunchAgent
And it does not report the observer as supervised
```

`## Scenario: on macOS ensure-codex-plugins leaves a running LaunchAgent observer alone when it reports a reconcile error`

```gherkin
Given a macOS host whose hook-cache observer is running under the installed LaunchAgent
And that observer's status record for a covered plugin reports a reconcile error
When ensure-codex-plugins runs
Then it reports the reconcile error as an observer failure, naming that plugin
And it exits non-zero
And the LaunchAgent's observer process receives no signal from ensure-codex-plugins
And no second observer process is started
```

`## Scenario: an observer that has not completed its first reconcile of a covered plugin is reported unhealthy for that plugin`

```gherkin
Given the hook-cache observer has started under its supervisor
And it has not yet completed its first reconcile of a covered plugin
When ensure-codex-plugins reports observer health for that plugin
Then that plugin is reported unhealthy
And a status record written before the first reconcile does not make it healthy
And once that plugin's own status record carries a completed reconcile without error, the first-reconcile rule no longer reports that plugin unhealthy
```

The resulting revise MUST add a `tests/heading-coverage.json` entry for each of the three new scenario headings, spelled `../tests/heading-coverage.json` in `resulting_files[]`. Each entry MUST map either to an integration-tier test or to a `TODO` whose `reason` explicitly names the integration tier, and MUST cite work item `livespec-driver-codex-yudufr`. The revise MUST also regenerate `tests/heading-coverage-debt.json`, spelled `../tests/heading-coverage-debt.json` in `resulting_files[]`, registering the three new TODO entries with `work_item: livespec-driver-codex-yudufr`. No other `## ` heading in any spec file is added, renamed, or removed.

Proposal notes, not resulting spec text:

- No `spec_commitments.impl_followups` entry is declared, deliberately. The implementation obligation already exists as work item `livespec-driver-codex-yudufr` (Definition of Done re-cut 2026-11-02), whose factory spec-change hold is linked to this proposal's topic; declaring a follow-up would file a duplicate. The Linux half is carried by `livespec-driver-codex-esytmj`, which yudufr is sequenced after.
- Live-exercise evidence is yudufr's host-captured acceptance evidence: on the affected MacBook Pro, after host provisioning installs the LaunchAgent, the observer runs under launchd and reports healthy for every covered plugin; launchd restarts it after it is killed, with a heartbeat newer than the kill; and it is running under launchd after logout and login without any Codex or Claude session having started it. That evidence belongs on the ledger work item, and the revise MUST NOT add it to the ratified text.
- Installing the LaunchAgent on the MacBook Pro is host provisioning, tracked under livespec epic `livespec-3rfjga` (repo livespec); it is not a Driver obligation.
- Interaction with open draft PR livespec-driver-codex#933 (topic `codex-hook-trust-continuity`): none of the spans this proposal replaces is replaced by #933. #933 inserts paragraphs before the "Each covered plugin's durable version-state record" paragraph, appends to the end of §"Forbidden patterns", inserts after the final sentence of the `check-dev-tooling` bullet and of the `tests/dev-tooling/` paragraph, and adds scenarios after `## Scenario: long-running hooks survive a cache update of any covered plugin`; this proposal replaces the following "The Driver MUST ship a service-supervisor definition" paragraph, inserts mid-list in §"Forbidden patterns", edits earlier spans of the two test paragraphs, and appends its scenarios at the end of `scenarios.md`. The two can be revised in either order. The new per-plugin health rule and #933's untrusted-hooks health rule are additive: a plugin is reported healthy only when every applicable rule holds.

