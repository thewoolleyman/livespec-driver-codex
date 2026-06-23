# tests/e2e-cli/

The CLI end-to-end harness CONSUMER for this Codex Driver repo,
adapted from the Claude Driver. The harness itself ships from
`livespec-dev-tooling` (`livespec_dev_tooling.testing.cli_e2e`, pinned
in pyproject.toml); this directory only wires it into pytest.

- `test_cli_e2e.py` — the consumer. The CI-safe DEFAULT (`mock` tier)
  runs: real structural skill discovery against the in-repo Codex
  plugin (`livespec/skills/`), real fixture loading, the real
  fail-closed coverage gate (`discover_fixtures` + `assert_coverage`),
  manifest well-formedness, and static binding assertions (every
  SKILL.md carries the verbatim Codex core-resolution invocation and
  the correct `$LIVESPEC_CORE_ROOT/scripts/bin/<op>.py` dispatch line).
  NO live agent subprocess runs in the mock tier — the `codex` CLI is
  not guaranteed in CI. The `real`-tier round-trip test (marker
  `real_only`) drives the canonical harness with a manifest shim and is
  skipped by default and in CI.
- `fixtures/<skill>/prompt.md` (+ optional `expected_files.txt`) —
  one fixture per discovered skill, using the Codex name-based
  invocation form (`livespec:<op>`). A skill added to
  `livespec/skills/` without a fixture here trips the fail-closed
  coverage gate.
- `conftest.py` — sys.path setup, `GIT_*` env scrubbing, and the
  `mock_only` / `real_only` tier auto-skips.

Run via `just check-e2e-cli` (mock tier; part of `just check` and the
CI matrix).
