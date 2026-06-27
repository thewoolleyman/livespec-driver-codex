---
name: revise
description: Walk the user through accepting or rejecting each pending proposed change in <spec-root>/proposed_changes/, then snapshot the result as a new <spec-root>/history/vNNN/ revision. Invoked by livespec:revise, "revise the livespec", or "process pending proposed changes".
---

# revise — Codex Driver binding

This file is the thin Codex binding for the `revise` operation,
shipped by the **livespec-driver-codex** Driver plugin (plugin name
`livespec`, so the surface stays `livespec:*`). The complete
harness-neutral driving prose is livespec CORE's artifact at
`<core-root>/prose/revise.md`. FIRST resolve `<core-root>` (next
section), THEN read that prose file in full, then execute it
end-to-end, binding its harness-neutral vocabulary to this runtime as
follows.


## Resolving livespec core (`<core-root>`)

This Driver plugin ships ONLY bindings. The harness-neutral prose and
the reference spec-side CLIs ship with **livespec core** — the
`livespec` plugin from the `thewoolleyman/livespec` marketplace, which
must be installed alongside this Driver. The plugin-root placeholder
of THIS plugin resolves to the Driver's own root, which carries no
`prose/` and no `scripts/` — NEVER use it for core paths. Resolve
`<core-root>` once, in this order:

1. If the `LIVESPEC_CORE_PLUGIN_ROOT` environment variable is set and
   non-empty, use its value (explicit override; covers nonstandard
   dev setups, e.g. driving a sibling checkout's core).
2. If `<project-root>/.claude-plugin/prose/revise.md` exists — the
   governed project IS the livespec core repo itself (`--plugin-dir .`
   dev mode / dogfooding) — use `<project-root>/.claude-plugin`.
3. Otherwise resolve the installed `livespec@livespec` plugin's
   `source.path` from `codex plugin list --json -m livespec`.

Canonical Bash form (`<project-root>` defaults to the cwd):

```bash
LIVESPEC_CORE_ROOT="$LIVESPEC_CORE_PLUGIN_ROOT"
if [ -z "$LIVESPEC_CORE_ROOT" ] && [ -d "./.claude-plugin/prose" ]; then
  LIVESPEC_CORE_ROOT="$(pwd)/.claude-plugin"
fi
if [ -z "$LIVESPEC_CORE_ROOT" ]; then
  LIVESPEC_CORE_ROOT="$(codex plugin list --json -m livespec 2>/dev/null | python3 -c 'import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for plugin in data.get("installed", []):
    if plugin.get("pluginId") == "livespec@livespec":
        sys.stdout.write(plugin.get("source", {}).get("path", ""))
        break' 2>/dev/null || true)"
fi
if [ -z "$LIVESPEC_CORE_ROOT" ] || [ ! -d "$LIVESPEC_CORE_ROOT/prose" ]; then
  echo "livespec core not found. Install it first:" >&2
  echo "  codex plugin marketplace add thewoolleyman/livespec" >&2
  echo "  codex plugin add livespec@livespec" >&2
  exit 1
fi
echo "$LIVESPEC_CORE_ROOT"
```

If resolution fails, STOP and surface those install instructions to
the user instead of improvising paths.

## Config-named CLI dispatch

Per livespec core's contract (its `contracts.md`), every spec-side operation is named in the governed
project's `.livespec.jsonc` under `spec_clis.revise` as an argv-form
array, pre-populated with core's reference default and individually
overridable. To "run the revise CLI named in config":

1. Read `<project-root>/.livespec.jsonc` (JSONC — tolerate `//`
   comments). If the file, the `spec_clis` section, or the
   `spec_clis.revise` key is absent, use core's reference default
   argv: `python3 <core-root>/scripts/bin/revise.py`.
2. If the configured argv contains the literal plugin-root
   substitution token (the `CLAUDE_PLUGIN_ROOT` placeholder, written
   as a `$`-brace expansion in config), expand it to `<core-root>` —
   core's schema defines that token as "the installed livespec plugin
   root", which is CORE's root, never this Driver's.
3. Append the operation's flags and invoke via the shell tool.

With the default config this collapses to:

```bash
python3 "$LIVESPEC_CORE_ROOT/scripts/bin/revise.py" --revise-json <path> --post-step-doctor [--author <id>] [--spec-target <path>] [--project-root <path>]
```

## Runtime bindings

- **"run the revise CLI named in config" / "invoke the revise
  CLI"** — dispatch per the Config-named CLI dispatch section above; with the
  default config:

  ```bash
  python3 "$LIVESPEC_CORE_ROOT/scripts/bin/revise.py" --revise-json <path> --post-step-doctor [--author <id>] [--spec-target <path>] [--project-root <path>]
  ```

- **"run the template-resolution CLI"** — via the shell tool:

  ```bash
  python3 "$LIVESPEC_CORE_ROOT/scripts/bin/resolve_template.py"
  ```

- **"run `python -m livespec_dev_tooling.workflow_checks.no_stale_revise_branches`"**
  (prose Step 3.5) — via the shell tool against the project root.
- **"ask the user" / "confirm with the user" / "surface" /
  "narrate" / the per-proposal confirmation dialogue** —
  conversational narration in this session.
- **"read `<file>`" / "list `<dir>`"** — reading the file directly
  (or shell `ls`). **"write `<file>`"** — writing the file directly.
- **"the propose-change / critique operation"** — the
  `propose-change`, `critique` skills in this Driver plugin (invoke
  them by name).
- **"the doctor prose (`prose/doctor.md`)"** — read
  `$LIVESPEC_CORE_ROOT/prose/doctor.md` and follow it (the
  LLM-driven post-step phase runs under this Driver plugin's
  `doctor` binding).
- **"invoke the active impl plugin's `capture-impl-gaps`
  front-end"** (prose Step 13(e)) — invoke
  `/<plugin-namespace>:capture-impl-gaps --since-version <prior-vN>
  --spec-target <spec-target> --project-root <project-root>` via the
  skill-namespace dispatch, where `<plugin-namespace>` is the value
  of `implementation.plugin` in `.livespec.jsonc`.
- **"core's `livespec/schemas/` package"** — resolves at runtime to
  `$LIVESPEC_CORE_ROOT/scripts/livespec/schemas/`.
