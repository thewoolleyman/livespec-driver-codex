---
name: seed
description: Author the initial natural-language specification for a new project, populating the chosen template's spec_root layout. Invoked by livespec:seed, "seed a livespec spec", "set up a livespec", or when starting a brand-new spec in an empty SPECIFICATION/ tree.
---

# seed — Codex Driver binding

This file is the thin Codex binding for the `seed` operation,
shipped by the **livespec-driver-codex** Driver plugin (plugin name
`livespec`, so the surface stays `livespec:*`). The complete
harness-neutral driving prose is livespec CORE's artifact at
`<core-root>/prose/seed.md`. FIRST resolve `<core-root>` (next
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
2. If `<project-root>/.claude-plugin/prose/seed.md` exists — the
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
project's `.livespec.jsonc` under `spec_clis.seed` as an argv-form
array, pre-populated with core's reference default and individually
overridable. To "run the seed CLI named in config":

1. Read `<project-root>/.livespec.jsonc` (JSONC — tolerate `//`
   comments). If the file, the `spec_clis` section, or the
   `spec_clis.seed` key is absent, use core's reference default
   argv: `python3 <core-root>/scripts/bin/seed.py`.
2. If the configured argv contains the literal plugin-root
   substitution token (the `CLAUDE_PLUGIN_ROOT` placeholder, written
   as a `$`-brace expansion in config), expand it to `<core-root>` —
   core's schema defines that token as "the installed livespec plugin
   root", which is CORE's root, never this Driver's.
3. Append the operation's flags and invoke via the shell tool.

With the default config this collapses to:

```bash
python3 "$LIVESPEC_CORE_ROOT/scripts/bin/seed.py" --seed-json <path> [--project-root <path>]
```

## Runtime bindings

- **"run the seed CLI named in config" / "invoke the seed
  CLI"** — dispatch per the Config-named CLI dispatch section above; with the
  default config:

  ```bash
  python3 "$LIVESPEC_CORE_ROOT/scripts/bin/seed.py" --seed-json <path> [--project-root <path>]
  ```

- **"run the template-resolution CLI"** — via the shell tool:

  ```bash
  python3 "$LIVESPEC_CORE_ROOT/scripts/bin/resolve_template.py" --project-root . --template <chosen>
  ```

- **"ask the user" / "confirm with the user" / "surface" /
  "narrate"** — conversational narration in this session.
- **"read `<file>`"** — reading the file directly. **"write
  `<file>`"** — writing the file directly.
- **"the propose-change / critique / revise operation"** — the
  `propose-change`, `critique`, `revise` skills in this Driver
  plugin (invoke them by name).
- **"the doctor prose (`prose/doctor.md`)"** — read
  `$LIVESPEC_CORE_ROOT/prose/doctor.md` and follow it (the
  LLM-driven post-step phase runs under this Driver plugin's
  `doctor` binding).
- **"core's `livespec/schemas/` package"** — resolves at runtime to
  `$LIVESPEC_CORE_ROOT/scripts/livespec/schemas/`.
