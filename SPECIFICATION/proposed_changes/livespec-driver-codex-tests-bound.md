---
topic: livespec-driver-codex-tests-bound
author: claude-opus-5-5
created_at: 2026-11-12T22:40:00Z
---

## Proposal: A test's verdict does not depend on how fast the host runs it: waits on required progress carry no short wall-clock bound, and a worker thread's exception fails the test

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Appends one paragraph to non-functional-requirements.md, section "Test discipline", after its last paragraph. The paragraph states three rules. A test that waits for something the code under test is required to do does not fail just because that took longer than a short fixed time. A bound on such a wait is a hang guard only: one value per repository, at least 120 seconds, whose expiry fails the test as a named hang. An exception raised in a test's worker thread fails the test and is named in the report. It names the two kinds of wait the rule does not govern. No heading is added, removed or renamed, so `tests/heading-coverage.json` does not change.

### Motivation

livespec-dev-tooling's `tests/livespec_dev_tooling/test_incident_recovery_journal.py::test_exact_concurrent_reservation_survives_restart_and_conflicting_bytes` failed `assert not True` in CI run 43287363009 (livespec-dev-tooling#4359, a diff that touched no incident code). It started two `reserve()` threads behind `Barrier(2).wait(timeout=3)`, then ran `worker.join(3)` and `assert not worker.is_alive()`. On a loaded runner the file-locked reserve took longer than 3 s, so the join returned with the thread still alive and the assert fired, with nothing wrong in the code under test. legacy-coordinator-agent ordered a fleet sweep of the same shape (rule K). The livespec-dev-tooling half of the rule is proposed in livespec-dev-tooling#4395 (topic `test-exact-concurrent-reservation-survives`), which it graded PASS on 2026-11-12. That clause binds only livespec-dev-tooling, because each member's work items are tier-judged against that member's own specification. So each member carries the rule in its own specification, and this is that member's proposal.

This specification has no rule on wall-clock bounds in tests. This repository's tests bound child-process waits at 5 to 60 seconds. The sharpest case is `tests/dev-tooling/test_codex_config_write.py:94`, `assert [child.wait(timeout=60) for child in children] == [0] * 6`: a process wait whose `TimeoutExpired` fails the test whenever the host is slow enough. The 120-second floor is 40 times the bound that fired in livespec-dev-tooling, and below the 180 seconds livespec-dev-tooling already uses for its slowest guarded call.

A mechanical check is deliberately not proposed. A pattern-level check cannot tell a teardown wait or an expected-expiry window from a verdict-bearing bound without the per-line judgment the sweep below records. The same deferral is recorded in livespec-dev-tooling#4395.

The root-fix item for this repository is livespec-driver-codex-tjsdzj. It was filed through this repository's capture seam on 2026-11-12 ~21:28Z, and intake held it at the spec-change tier with this topic as its linked proposal. Its cross-tenant link to livespec-dev-tooling (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub, items livespec-dev-tooling-dqndbz and livespec-dev-tooling-rs6o3q) is recorded in prose on both sides, never as a dependency edge.

### Fleet sweep (this repository)

Swept 2026-11-12 ~21:25Z at the checked-out `HEAD`, over test files (`*test*.py`, `tests/**/*.py`, `conftest.py`), with the pattern:

```text
\.join\(\s*(timeout\s*=\s*)?[0-9][0-9.]*\s*\)|\.wait\(\s*timeout\s*=\s*[0-9]|assert\s+not\s+.*\.is_alive\(\)
```

6 pattern hits in 3 files. These are pattern hits, not per-line verdicts, because the one pattern also matches teardown waits and expected-expiry windows. The root-fix item classifies each line against the ratified rule, fixes every verdict-bearing bound and every swallowed worker exception, and records why it leaves each exempt line alone. Line numbers are as of the sweep.

- `tests/dev-tooling/test_codex_config_write.py`: 94, 195
- `tests/e2e-cli/test_codex_skill_picker.py`: 178, 182, 185
- `tests/hooks/test_supervisor_completion_gate.py`: 611

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Test discipline", append the following paragraph after the section's last paragraph, which ends "with no identifiable release tag, is reported and never trusted." No heading is added, removed or renamed in that file.

A test's verdict MUST NOT depend on how fast the host runs it. When a test waits for something the code under test is required to do — a worker thread or child process to finish, or a barrier, event or condition to be reached — it MUST wait either without a wall-clock bound or under a hang guard. A hang guard is one value the repository defines once for every such wait, MUST be no shorter than 120 seconds, and its expiry MUST fail the test as a hang that names what the test was waiting for. A test MUST NOT bound such a wait more tightly, as `join(3)` followed by `assert not worker.is_alive()`, `Barrier(2).wait(timeout=3)` or `assert event.wait(timeout=2)` do. An exception raised in a test's worker thread MUST fail that test, and the failure report MUST name that exception, never surface only as a missing or short result. Two kinds of wait are outside this rule: a teardown wait whose expiry falls through to a forced stop and decides no verdict, and a wait whose expiry is the outcome the test expects, such as a check that a blocked party has not yet proceeded. The rule applies to this repository's tests.
