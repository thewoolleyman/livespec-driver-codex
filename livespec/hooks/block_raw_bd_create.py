#!/usr/bin/env python3
"""
block_raw_bd_create — PreToolUse hook routing a raw `bd create` to the
active impl-plugin's capture-work-item operation.

Declared in hooks.json on the `Bash` tool. The effective matcher is
`Bash(bd … create …)`: this hook inspects the command and acts only when a
`bd` command head reaches the `create` subcommand inside a livespec-governed
project (a `.livespec.jsonc` declaring `implementation.plugin`).

WHY THIS IS AN INTAKE FAILURE, not a style preference. A raw `bd create`
files the work-item at the beads-native status `open`, which is OUTSIDE the
runtime's livespec status vocabulary. The item therefore strands in backlog:
it never runs the intake Definition-of-Ready gate and never reaches the
factory. `capture-work-item` runs that gate and routes the status, which is
what makes an item dispatchable at all. Two surfaces already go LOUD about the
result — the armed `work_item_status_vocabulary` check and the orchestrator's
`untriaged_backlog_items` needs-attention lane — but both report a stranded
item AFTER it is filed; neither prevents the filing. This hook is the
prevention, so the deny reason CITES those two rather than adding a third
loudness layer.

Shape (deliberately the sibling redirect hooks', not a new one): the deny
decision of `block_auto_memory.py` — routing by INTENT to a named
`/<plugin>:capture-work-item` operation resolved from config, never hardcoded
— over the Bash-command inspection of `tmux_fleet_guard.py`.

DETECTION. Each LINE of the command is tokenized by `shlex`, and every token
position is scanned for a `bd` command head, so a wrapper prefix
(`mise exec -- bd create …`, `env -i bd create …`) is defeated by the scan
rather than by an allowlist of known wrappers. From each head, the argument
run is walked for the `create` subcommand, which lets beads' own global flags
sit in between (`bd -C <dir> create …` is the documented family spelling). The
walk STOPS at the first token carrying shell control punctuation, because that
is where this command's argument run ends and the next command begins — so
`bd list && grep create f` is not read as a create.

The LINE split comes first because `shlex` treats a newline as ordinary
whitespace: tokenizing a whole multi-line command fuses `bd list` on one line
with a bare `create` word on the next, and the argument walk cannot tell them
apart. Blocking a read-only invocation is the costlier error here — a missed
create is still reported by the two loud surfaces above, while a wrongly
blocked command stops legitimate work with a message that does not describe
it.

Quoting is what keeps this from over-blocking: `echo 'bd create x'`, a
`git commit -m` message, and a `grep` pattern each lex to ONE token whose
value is the whole sentence, so no token's basename is `bd`.

Fail-open contract: ANY failure (malformed stdin, an untokenizable command,
unset `CLAUDE_PROJECT_DIR`, an unreadable or unparseable `.livespec.jsonc`) is
a silent pass-through with exit 0. The hook only denies when it POSITIVELY
identifies a raw create in a governed project — a wrongly-denied command costs
one redirect message, and the two loud surfaces above still catch whatever
this misses. `main()` owns stdin/stdout at the hook boundary, catches every
failure, and returns 0 on every path; it is importable (no work at module
import) so the body is testable in-process for real per-file coverage.

Self-contained by contract: the plugin installer ships this file under bare
system `python3` with no virtualenv and no third-party packages, so every
import here is the standard library or a sibling module shipped beside it.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from typing import cast

from _livespec_project import resolve_impl_plugin
from _result import Failure, Result, Success

__all__: list[str] = []

_BD_COMMAND = "bd"
_CREATE_SUBCOMMAND = "create"
# `;`, `|`, and `&` all end the command whose arguments the subcommand walk is
# reading. A token that survived `shlex` carrying one of them is therefore the
# boundary, not an argument. A newline is NOT in this set: `shlex` consumes it
# as whitespace, so no token can carry one — line boundaries are handled by
# splitting BEFORE tokenization instead.
_SHELL_CONTROL = ";|&"


def _as_object_dict(*, value: object) -> dict[str, object] | None:
    """Narrow an arbitrary JSON value to a string-keyed dict, else None."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _basename(*, token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _reaches_create(*, arguments: list[str]) -> bool:
    """True when this `bd` head's OWN argument run carries `create`."""
    for argument in arguments:
        if any(char in _SHELL_CONTROL for char in argument):
            return False
        if argument == _CREATE_SUBCOMMAND:
            return True
    return False


def _line_runs_create(*, line: str) -> bool:
    """True when ONE line runs `bd create` at any of its token positions."""
    try:
        tokens = shlex.split(line, posix=True)
    except ValueError:
        # An untokenizable line cannot be shown to be a create; the sibling
        # loud surfaces cover what this misses, so it passes through.
        return False
    return any(
        _basename(token=token) == _BD_COMMAND and _reaches_create(arguments=tokens[index + 1 :])
        for index, token in enumerate(tokens)
    )


def _command_lines(*, command: str) -> list[str]:
    """The lines the shell runs in sequence, or the whole command.

    A quoted string may itself SPAN line breaks (a multi-line title), and then
    no line tokenizes on its own. Judging the whole command instead restores
    the balanced quote — the only case where the newline-fusing this split
    exists to prevent cannot occur anyway, since the newline is inside quotes.
    """
    lines = [line for line in command.splitlines() if line.strip()]
    if len(lines) < 2:
        return [command]
    try:
        for line in lines:
            _ = shlex.split(line, posix=True)
    except ValueError:
        return [command]
    return lines


def _is_raw_bd_create(*, command: str) -> bool:
    """True when any line of the command runs `bd create`."""
    return any(_line_runs_create(line=line) for line in _command_lines(command=command))


def _deny_reason(*, namespace: str) -> str:
    """The intake-routing deny reason naming the capture-work-item operation."""
    return (
        "This project is livespec-governed. A raw `bd create` is NOT the intake "
        "path here: it files the work-item at the beads-native status `open`, "
        "OUTSIDE the runtime's livespec status vocabulary, so the item strands in "
        "backlog — it never runs the intake Definition-of-Ready gate and never "
        "reaches the factory.\n"
        f"  - File the work-item with /{namespace}:capture-work-item instead. It "
        "runs the Definition-of-Ready gate and routes the status, which is what "
        "makes an item dispatchable.\n"
        "  - Do NOT re-run this create by another spelling, and do NOT drop what "
        "you were about to file.\n"
        "The two surfaces that already go loud about a stranded item — the armed "
        "`work_item_status_vocabulary` check and the orchestrator's "
        "`untriaged_backlog_items` needs-attention lane — report it only AFTER it "
        "is filed. This redirect is what prevents it."
    )


def _deny_decision(*, namespace: str) -> str:
    reason = _deny_reason(namespace=namespace)
    return json.dumps(
        {
            "decision": "block",
            "reason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            },
        }
    )


def _decision(*, raw: str) -> str | None:
    """Return the deny-decision JSON, or None for a pass-through."""
    payload = _as_object_dict(value=json.loads(raw))
    if payload is None or payload.get("tool_name") != "Bash":
        return None
    tool_input = _as_object_dict(value=payload.get("tool_input"))
    if tool_input is None:
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command:
        return None
    if not _is_raw_bd_create(command=command):
        return None
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "").strip()
    if not project_dir:
        return None
    namespace = resolve_impl_plugin(project_dir=project_dir).value_or(default=None)
    if namespace is None:
        return None
    return _deny_decision(namespace=namespace)


def _decision_result(*, raw: str) -> Result[str | None, Exception]:
    """Lift the expected malformed-payload failure from decision logic onto the rail.

    `ValueError` is raised by `json.loads`, including `JSONDecodeError`
    subclasses. The `.livespec.jsonc` read has its own rail inside
    `resolve_impl_plugin`, so it never surfaces here.
    """
    try:
        return Success(_decision(raw=raw))
    except ValueError as exc:
        return Failure(exc)


def main() -> int:
    """Hook entry point: emit the deny decision, if any; always exit 0.

    Owns the stdin read + stdout write at the hook boundary and catches every
    failure so the PreToolUse hook stays fail-open by contract — it only denies
    when it POSITIVELY identifies a raw create in a governed project, and never
    exits non-zero.
    """
    try:
        decision = _decision_result(raw=sys.stdin.read()).value_or(default=None)
        if decision is not None:
            _ = sys.stdout.write(decision + "\n")
    except Exception:  # noqa: BLE001 — sole fail-open hook boundary: silent pass-through, exit 0
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
