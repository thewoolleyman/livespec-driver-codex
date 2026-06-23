---
name: help
description: Explain what livespec does and route the user to the right sub-command (seed, propose-change, critique, revise, doctor, prune-history). Invoked by livespec:help, "what can livespec do", or when the user asks for an overview of livespec capabilities.
---

# help — Codex Driver binding

This file is the thin Codex binding for the `help` operation,
shipped by the **livespec-driver-codex** Driver plugin (plugin name
`livespec`, so the surface stays `livespec:*`). The complete
harness-neutral driving prose is livespec CORE's artifact at
`<core-root>/prose/help.md`. FIRST resolve `<core-root>` (next
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
2. If `<project-root>/.claude-plugin/prose/help.md` exists — the
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

## Runtime bindings

- **"the seed / propose-change / critique / revise / doctor /
  prune-history / next operation"** — the corresponding `<name>`
  skill in this Driver plugin (invoke it by name).
- **"running the seed CLI named in config with `--help`"** — e.g.
  `python3 "$LIVESPEC_CORE_ROOT/scripts/bin/seed.py" --help` via the
  shell tool (same pattern for every other operation's wrapper under
  `$LIVESPEC_CORE_ROOT/scripts/bin/`).
