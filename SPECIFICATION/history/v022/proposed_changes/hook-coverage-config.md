---
topic: hook-coverage-config
author: claude:dev-host-test-gate-load
created_at: 2026-11-09T19:38:14Z
---

## Proposal: The hook coverage gate is stated and combines under any pytest coverage spelling

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

State, in §"Enforcement suite", the 100% line and branch coverage gate that `check-coverage` already holds `livespec/hooks/` to. Require that pyproject.toml's coverage configuration governs every pytest coverage run, so a bare `pytest --cov` spelling still combines branch data. Add a scenario for it.

### Motivation

Work item livespec-driver-codex-toclbe is an execution mirror of livespec-dev-tooling-wj45qt (plan livespec-dev-tooling-6vuiwe, dev-host-test-gate-load). It is HELD because no H2 heading here governs this repository's Python coverage run. §"Enforcement suite" lists check-plugin-structure, check-hooks, check-e2e-cli and the rest, but not `check-coverage`. "Coverage" elsewhere in the spec means fixture or heading coverage. The justfile's `check-coverage` already gates `livespec/hooks` at `fail_under = 100` with `branch = true`, with no ratified clause behind it.

The defect it must exclude, measured in livespec-dev-tooling on 2026-11-09: pytest-cov hands its test subprocesses the coverage configuration by path only when `--cov-config` names an existing file. With a bare `pytest --cov` the default `.coveragerc` is assumed, and it does not exist. A subprocess whose cwd has no pyproject in view then measures statements only, and pytest-cov's combine step fails ("Can't combine statement coverage data with branch data") after the whole suite has passed. This repository's pytest section carries no `addopts`, so it has the same latent gap. Its own recipe passes `--cov-config=pyproject.toml` and does not meet it; a gate Job or ad-hoc bare spelling would. The livespec-dev-tooling fix (livespec-dev-tooling#3895) pins `--cov-config=pyproject.toml` in pytest addopts, and that is the expected means here. The clause states the behaviour, not that means.

After this revise, toclbe's References line is re-pointed to "## Scenario: the hook coverage gate combines under any pytest coverage spelling", and its hold is lifted.

### Proposed Changes

Two co-edits. One adds an H2 heading to scenarios.md, so the revise that accepts this MUST also add a `tests/heading-coverage.json` entry for it in the same commit. A spec-first `"test": "TODO"` row is acceptable there, naming work item livespec-driver-codex-toclbe as its owner and the tier of the owed test.

1. SPECIFICATION/non-functional-requirements.md §"Enforcement suite": in the bullet list under "`just check` aggregates the gates that guard the `contracts.md` seam:", insert after the **`check-hooks`** bullet:

```
- **`check-coverage`** — holds the plugin-shipped hook code under
  `livespec/hooks/` to 100% line and branch coverage, measured by
  `tests/hooks/`. The coverage configuration in `pyproject.toml` MUST
  govern every pytest coverage run in this repository, whether or not
  the run names that configuration, so that a run's branch data and the
  data its test subprocesses record always combine. A run that is given
  `--cov` without `--cov-config` MUST end with pytest's own exit status
  and a coverage report, never with a failure to combine statement data
  with branch data.
```

2. SPECIFICATION/scenarios.md: add this scenario, placed with the other enforcement-suite scenarios (after "## Scenario: a delegating host's push gates on the remote executor and refuses on no verdict"):

```
## Scenario: the hook coverage gate combines under any pytest coverage spelling

Given pyproject.toml configures branch coverage for `livespec/hooks/`

And a hook test starts a Python subprocess whose working directory has no pyproject.toml in view

When pytest runs `tests/hooks/` with `--cov` and no `--cov-config` argument

Then the run MUST end with pytest's own exit status

And it MUST print a coverage report

And it MUST NOT fail combining statement coverage data with branch data
```

The scenario uses the plain-paragraph Given/And/When/Then form of its neighbours in scenarios.md.
