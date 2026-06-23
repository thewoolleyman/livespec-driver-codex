# constraints.md — livespec-driver-codex

Architecture-level constraints the Driver bindings, hook bundle, and
structural gate honor. Contracts (`contracts.md`) say what the seam must
look like; these constraints say what the implementation may and may not
do to realize it.

## Inherited from livespec

Every constraint in `livespec/SPECIFICATION/constraints.md` that applies
to a Driver binding applies here unmodified; this tree does not relax or
restate them. Where an inherited constraint and a Driver-local one appear
to conflict, the upstream constraint wins.

## Binding constraints

- A binding is **thin**: it carries no behavior of its own beyond
  resolving `<core-root>`, reading core's operation prose, and
  dispatching the config-named CLI. All dialogue capture, content
  generation, and structured-finding interpretation are dictated by
  core's prose, not invented in the binding.
- Each `SKILL.md` is self-contained and follows the family's three-part
  binding shape; a binding MUST NOT depend on another binding's files.
- A thin-transport binding (e.g. `next`) MUST NOT accrete ranking,
  filtering, formatting, a confirmation dialogue, or an opt-in flag — all
  such logic lives in the backing core wrapper.
- The Driver bundle ships NO `scripts/` tree and NO wrapper CLIs: those
  are core-owned and resolved at runtime. The bundle ships bindings, the
  footgun-guard hook, and the manifest only.

## Resolution-substrate constraints

- The core-root resolution order (`contracts.md` §"Core-root resolution")
  is fixed; a binding MUST walk it in order and MUST NOT short-circuit to
  a hardcoded path.
- A binding MUST NOT use the Driver's own plugin-root placeholder to reach
  core scripts (it resolves to the Driver root, which has no `scripts/`).
- A binding MUST NOT assume a single installation shape (dev-mode
  checkout vs. installed cache vs. operator override are all valid).
- The installed-cache fallback reads the core plugin's `source.path` from
  `codex plugin list --json -m livespec`; a binding MUST tolerate a
  missing/empty result by falling through to a clear install diagnostic.

## Structural-check constraints

- `dev-tooling/check_plugin_structure.py` MUST be stdlib-only: it runs
  under bare `python3` with no virtualenv, so it can gate commits and CI
  before any environment is provisioned.
- The check is **fail-closed**: it exits non-zero with one diagnostic per
  violation on stderr, and exits zero only when every assertion holds.
- The plugin-shipped `livespec_footgun_guard.py` is excluded from the
  product-code lint rule set (its `PreToolUse` protocol REQUIRES writing
  its decision JSON to stdout, which the print-ban rule forbids); its
  behavior is guarded by the `tests/hooks/` subprocess unit tests instead.

## Forbidden patterns

- `uv run`, a literal `.claude-plugin/scripts` path, or the Driver's own
  plugin-root placeholder in any fenced wrapper invocation inside a
  `SKILL.md`.
- A `/livespec:` slash-command form, an `installed_plugins.json`
  reference, the phrase `Claude Code Driver`, or the sibling repo name
  `livespec-driver-claude` in any binding body (Codex is name-based).
- An extra skill directory, a missing binding, or a `SKILL.md` whose
  frontmatter `name` disagrees with its directory or whose `description`
  is empty.
- A top-level `description` key in `hooks.json` (Codex's hooks parser
  rejects it).
- Renaming the plugin name (`livespec`) or the marketplace name
  (`livespec-driver-codex`) without a propose-change cycle.
- Committing or pushing at the primary checkout; passing `--no-verify`;
  editing tracked files outside a dedicated worktree (see
  `non-functional-requirements.md` §"Inherited from livespec").
