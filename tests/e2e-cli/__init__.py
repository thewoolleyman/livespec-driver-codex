"""CLI end-to-end test package — the top-of-pyramid tier.

Per livespec/SPECIFICATION/contracts.md: this package wires the single canonical harness shipped
from `livespec-dev-tooling` (`livespec_dev_tooling.testing.cli_e2e`)
into this Codex Driver repo's pytest collection. The skills live in
THIS repo's Codex plugin (`livespec/skills/`), so the
structural-discovery + fail-closed coverage gate runs here. The `mock`
tier (LIVESPEC_E2E_HARNESS=mock) runs in `just check`/CI: real
structural skill discovery + real fixture loading + the real
fail-closed coverage gate + static binding-snippet assertions, with
NO live agent subprocess (the `codex` CLI is not guaranteed in CI).
The `real` tier drives the actual `codex` CLI binary and is NOT part
of `just check`.
"""

__all__: list[str] = []
