---
topic: codex-observer-no-start
author: claude-opus-5-5
created_at: 2026-11-03T09:26:16Z
spec_commitments:
  impl_followups:
    - id_hint: codex-observer-no-start
      description: |
        Filed as livespec-driver-codex-n2b3ui. Make ensure-codex-plugins never start a hook-cache observer process on any platform, report an observer not running under the installed systemd user unit on Linux (including when no unit is installed, and while a detached observer is alive) without signalling it, report a running supervised observer's reconcile error without signalling or duplicating it, and let the newer of its own reconcile result and the observer's status record govern each covered plugin's reported result, which requires each observer status record to carry a wall-clock reconcile completion time comparable with the provisioner's own.
---

## Proposal: ensure-codex-plugins never starts an observer, the newest reconcile result governs, and the supervisor scenarios cover Linux

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Close three gaps that the LLM-driven doctor post-step reported on spec v016 (`supervise-the-generalized-codex-hook`). First, `ensure-codex-plugins` MUST NOT start an observer process at all, on any platform and whether or not the supervisor's observer is running; v016 forbade only a SECOND observer while the supervised one runs, and its phrase "any observer process it did not start" implied that it may start one. Second, when `ensure-codex-plugins`' own reconcile of a covered plugin and the observer's status record for that plugin disagree, the newer of the two governs the reported result for that plugin. Third, add Linux counterparts to v016's two macOS supervisor scenarios, so that the platform-neutral supervision rules are exercised on both supported platforms. The v016 sentence and macOS scenario that made an observer error report unconditional are qualified to match, status records are required to carry a comparable completion time, and the test obligations in `non-functional-requirements.md` are amended in lockstep.

### Motivation

The doctor LLM-driven post-step on v016 (2026-11-03) returned three warnings against `contracts.md` §"Codex hook-cache compatibility".

1. A safety gap. v016 says `ensure-codex-plugins` "MUST NOT start a second observer" only "while the supervisor's observer is running", and "MUST NOT signal any observer process it did not start". Nothing forbids `ensure-codex-plugins` from starting a detached, unsupervised observer while the supervised observer is NOT running, and the "did not start" wording implies that it may. That is the takeover shape that closed draft PR livespec-driver-codex#921: an ensure path that starts its own observer leaves a process no supervisor restarts, and the next run then has two candidates to reason about. Starting the observer is the supervisor's job; `ensure-codex-plugins` checks supervision and reports.
2. An ambiguity. The section requires `ensure-codex-plugins` to run the reconciler for every covered plugin, and v016 requires it to report a reconcile error recorded by the supervised observer. When its own reconcile succeeds after the observer recorded an error, the text does not say whether the older error still fails provisioning. Either reading is harmful: a stale error fails provisioning after a successful repair, or a successful explicit repair masks a newer observer failure.
3. A coverage asymmetry. v016's contract and test obligations cover the supervisor check "on each supported platform", but all three new supervisor scenarios are macOS-only, so no scenario exercises the systemd user unit that the Linux half (livespec-driver-codex-esytmj, with livespec-driver-codex-p3oixg) ships as `dev-tooling/livespec-codex-hook-cache-observer.service` and that `ensure-codex-plugins` checks with the user service manager.

The implementation obligation is filed as livespec-driver-codex-n2b3ui. livespec-driver-codex-yudufr (the macOS half) carries a ledger note to the same effect for the shared provisioner. Ledger references: livespec epic `livespec-3rfjga` (repo livespec, plan `codex-plugin-hook-path-regression`).

### Proposed Changes

In `contracts.md` §"Codex hook-cache compatibility" (the H3 under §"Hook bundle"; no `## ` heading changes in `contracts.md`):

1. In the paragraph that begins "`ensure-codex-plugins` checks supervision; it does not take supervision over.", replace these two sentences, quoted verbatim (in the file they wrap across lines; the match is whitespace-normalized):

   ```
   While the supervisor's observer is running, `ensure-codex-plugins` MUST NOT signal that process and MUST NOT start a second observer, including when that observer's status record reports a reconcile error. It reports that error instead, as a provisioning or observer failure naming the plugin, and exits non-zero.
   ```

   with:

   > While the supervisor's observer is running, `ensure-codex-plugins` MUST NOT signal that process, including when that observer's status record reports a reconcile error. When that error is the reconcile result reported for the plugin under the newest-result rule below, it reports that error instead, as a provisioning or observer failure naming the plugin, and exits non-zero.

2. In the same paragraph, replace this sentence, quoted verbatim (whitespace-normalized):

   ```
   `ensure-codex-plugins` MUST NOT signal any observer process it did not start; where it finds a live observer not running under the installed supervisor definition, it reports it rather than terminating it.
   ```

   with:

   > `ensure-codex-plugins` MUST NOT start an observer process, on any platform, whether or not the supervisor's observer is running; starting the observer is the supervisor's job. It MUST NOT signal any observer process; where it finds a live observer not running under the installed supervisor definition, it reports it rather than terminating it.

3. Insert one new paragraph immediately after that paragraph and immediately before the paragraph that begins "Observer health is reported per covered plugin.":

   > Each observer status record for a covered plugin MUST carry the time its reconcile completed, comparable with the completion time of a reconcile that `ensure-codex-plugins` runs; when the two times are equal, the observer's status record counts as the newer. For each covered plugin, the reconcile result that `ensure-codex-plugins` reports is the newer of its own reconcile of that plugin in the current run and the observer's status record for that plugin. An observer status record that reports a reconcile error and is older than a reconcile of that plugin that `ensure-codex-plugins` completed without error in the current run MUST NOT fail provisioning for that plugin, and, provided the observer has completed at least one reconcile of that plugin, that newer reconcile satisfies the per-plugin health rule's requirement of a completed reconcile that reported no error. An observer that has completed no reconcile of that plugin is still reported unhealthy for it. An observer status record that reports a reconcile error and is newer than that reconcile MUST be reported as a provisioning or observer failure naming the plugin, with a non-zero exit. Apart from that requirement, this rule decides only which reconcile result is reported; an observer error superseded by a newer reconcile in this way is not a reconcile failure for the purposes of any other rule in this section, while every other rule in this section that reports the plugin unhealthy, including the trust-continuity and fail-closed rules, still applies.

4. In the paragraph that begins "Observer health is reported per covered plugin.", replace "MUST NOT be reported healthy for that plugin until that plugin's own status record carries a completed reconcile that reported no error;" (whitespace-normalized; it wraps across lines) with "MUST NOT be reported healthy for that plugin until that plugin's own status record carries a completed reconcile that reported no error, except as the newest-result rule above provides;".

In `constraints.md` §"Forbidden patterns", replace this bullet, quoted verbatim:

```
- Signalling the supervisor's hook-cache observer, or starting a second
  observer, from `ensure-codex-plugins` while the supervisor's observer
  is running (`contracts.md` §"Codex hook-cache compatibility").
```

with:

- "Signalling any hook-cache observer process, or starting a hook-cache observer process, from `ensure-codex-plugins` (`contracts.md` §\"Codex hook-cache compatibility\")."

In `non-functional-requirements.md`:

- §"Enforcement suite", in the `check-dev-tooling` bullet, replace "and the provisioner's supervisor check on each supported platform)", which wraps across one line break in the source, with "the provisioner's supervisor check on each supported platform, the provisioner starting no observer process, and the newest-result rule between the provisioner's own reconcile and the observer's status record)".
- §"Test discipline", in the `tests/dev-tooling/` paragraph, replace this span, quoted verbatim:

  ```
  observer with no installed definition reported, a live observer the
  provisioner did not start reported rather than signalled, and a
  running supervised observer whose status record reports a reconcile
  error reported with a non-zero exit but neither signalled nor
  duplicated);
  ```

  with:

  ```
  observer with no installed definition reported, a live observer
  reported rather than signalled, no observer process started by the
  provisioner in any run, a running supervised observer whose status
  record reports a reconcile error newer than the provisioner's own
  reconcile reported with a non-zero exit but neither signalled nor
  duplicated, and an older observer error superseded by a newer
  successful provisioner reconcile; the Linux systemd user unit
  inactive while a detached observer is alive, and no unit installed,
  are covered as well as the macOS LaunchAgent cases);
  ```

In `scenarios.md`:

- In the existing `## Scenario: on macOS ensure-codex-plugins leaves a running LaunchAgent observer alone when it reports a reconcile error` (heading unchanged), replace the line "And that observer's status record for a covered plugin reports a reconcile error" with "And that observer's status record for a covered plugin reports a reconcile error newer than any reconcile of that plugin ensure-codex-plugins completes in this run".
- Append the following two scenarios at the end of the file, after the last existing scenario `## Scenario: an observer that has not completed its first reconcile of a covered plugin is reported unhealthy for that plugin`, which is kept unchanged:

`## Scenario: on Linux ensure-codex-plugins reports an observer not running under the installed systemd user unit and starts none`

```gherkin
Given a Linux host whose host provisioning installed the Driver's shipped systemd user unit for the hook-cache observer
And that unit is not active
And a detached observer process that the user service manager did not start is alive
When ensure-codex-plugins runs
Then it exits non-zero
And its report names the hook-cache observer as not running under the installed systemd user unit
And it does not report the observer as supervised
And the detached observer process receives no signal from ensure-codex-plugins
And ensure-codex-plugins starts no observer process

Given a Linux host on which no systemd user unit for the hook-cache observer is installed
When ensure-codex-plugins runs
Then it exits non-zero
And its report names the hook-cache observer as not running under an installed systemd user unit
And ensure-codex-plugins starts no observer process
```

`## Scenario: on Linux ensure-codex-plugins leaves a running supervised observer alone when it reports a reconcile error`

```gherkin
Given a Linux host whose hook-cache observer is running under the installed systemd user unit
And that observer's status record for a covered plugin reports a reconcile error newer than any reconcile of that plugin ensure-codex-plugins completes in this run
When ensure-codex-plugins runs
Then it reports the reconcile error as an observer failure, naming that plugin
And it exits non-zero
And the supervised observer process receives no signal from ensure-codex-plugins
And no second observer process is started

Given a Linux host whose hook-cache observer is running under the installed systemd user unit
And that observer has completed a reconcile of a covered plugin whose status record reports a reconcile error
When ensure-codex-plugins runs and completes its own reconcile of that plugin without error after that record
Then the older observer error does not fail provisioning for that plugin
And ensure-codex-plugins starts no observer process
```

The resulting revise MUST add a `tests/heading-coverage.json` entry for each of the two new scenario headings, spelled `../tests/heading-coverage.json` in `resulting_files[]`. Each entry MUST map either to an integration-tier test or to a `TODO` whose `reason` explicitly names the integration tier, and MUST cite work item `livespec-driver-codex-n2b3ui`. The revise MUST also regenerate `tests/heading-coverage-debt.json`, spelled `../tests/heading-coverage-debt.json` in `resulting_files[]`, registering the two new TODO entries with `work_item: livespec-driver-codex-n2b3ui`. No other `## ` heading in any spec file is added, renamed, or removed.

Proposal notes, not resulting spec text:

- Apart from the one qualified Given line, the two macOS scenarios ratified in v016 are left unchanged. Their "no second observer process is started" line is now implied by the general no-start rule and stays correct.
- The doctor post-step also reported, as information only, that on a platform with no supported supervisor `ensure-codex-plugins` has no defined exit status, and that macOS has no observer between boot and GUI login. Both remain covered by v015's loud unhealthy report for untrusted hooks; neither is changed here.
- The overlong line in `non-functional-requirements.md` §"Test discipline" left by v016 is cosmetic and is not touched here.
