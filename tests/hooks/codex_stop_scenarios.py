"""Scenarios that drive every declared Codex Stop hook to a NON-EMPTY payload.

`livespec/hooks/hooks.json` declares three hooks under `Stop`, and each one has
at least one path that writes a JSON object to stdout. Those payloads — not the
silent pass-throughs, which are how a Stop hook says "allow" — are what the
Codex Stop runtime parses against its closed schema, so they are exactly what
`codex_stop_output_contract.validate_stop_output` has to see.

The scenarios live here, apart from either suite that runs them, because BOTH
seams need the same payloads out of the same code paths: the direct suite
(`test_codex_stop_hook_output_contract.py`) runs the hooks in-process from this
checkout, and the install-shape suite (`test_shipped_hooks_install_shape.py`)
runs them as subprocesses out of a copied plugin cache, where nothing above
`livespec/` exists. A scenario is therefore pure DATA — a script name plus the
stdin, cwd, and environment that provoke the payload — and each suite supplies
its own way of running it.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "STOP_SCENARIO_LABELS",
    "StopScenario",
    "build_stop_scenarios",
    "declared_stop_hook_scripts",
]

# The two payload shapes the declared Stop hooks emit: the supervisor gate's
# blocking decision, and the two audits' warn-only system message.
_BLOCK_KEYS: Final = frozenset({"decision", "reason"})
_WARNING_KEYS: Final = frozenset({"systemMessage"})

_HANDOFF_WITH_CHECKBOXES = "# Handoff\n\n- [ ] step one\n- [ ] step two\n- [x] step three\n"


@dataclass(frozen=True, kw_only=True)
class StopScenario:
    """One hook run KNOWN to write a payload, plus the keys that payload carries.

    `env` names only the variables the scenario needs; each suite merges it over
    whatever base environment its own runner supplies. `expected_keys` pins WHICH
    payload the scenario provokes, so a hook that quietly starts taking a
    different path fails here instead of contract-validating something else.
    """

    script: str
    stdin: str
    cwd: Path
    env: Mapping[str, str]
    expected_keys: frozenset[str]


def declared_stop_hook_scripts(*, hooks_json: Path) -> tuple[str, ...]:
    """Every hook script name declared under `hooks.Stop`, in declaration order."""
    declared = json.loads(hooks_json.read_text(encoding="utf-8"))["hooks"]["Stop"]
    names: list[str] = []
    for entry in declared:
        for hook in entry["hooks"]:
            name = str(hook["command"]).rsplit("/", 1)[-1].rstrip('"')
            if name not in names:
                names.append(name)
    return tuple(names)


def _stop_stdin(*, transcript_path: str = "/nonexistent") -> str:
    return json.dumps({"stop_hook_active": False, "transcript_path": transcript_path})


def _governed_project(*, root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    root.joinpath(".livespec.jsonc").write_text(
        json.dumps({"implementation": {"plugin": "livespec-orchestrator-beads-fabro"}}),
        encoding="utf-8",
    )
    return root


def _no_shadow_ledger_warning(*, root: Path) -> StopScenario:
    """A handoff written this turn carrying three checkbox task items."""
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = [
        {"type": "user", "message": {"content": [{"type": "text", "text": "write the handoff"}]}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Write",
                        "input": {
                            "file_path": str(root / "HANDOFF-session.md"),
                            "content": _HANDOFF_WITH_CHECKBOXES,
                        },
                    }
                ]
            },
        },
    ]
    transcript = root / "transcript.jsonl"
    transcript.write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n",
        encoding="utf-8",
    )
    return StopScenario(
        script="no_shadow_ledger.py",
        stdin=_stop_stdin(transcript_path=str(transcript)),
        cwd=root,
        env={},
        expected_keys=_WARNING_KEYS,
    )


def _background_memory_audit_warning(*, root: Path) -> StopScenario:
    """A governed project whose Codex background-memory store carries rows."""
    project = _governed_project(root=root / "project")
    db_path = root / "home" / ".codex" / "memories_1.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute("create table jobs (id text primary key)")
        con.execute("create table stage1_outputs (id text primary key)")
        con.execute("insert into jobs (id) values ('job-0')")
        con.execute("insert into stage1_outputs (id) values ('out-0')")
        con.commit()
    finally:
        con.close()
    return StopScenario(
        script="codex_background_memory_audit.py",
        stdin=_stop_stdin(),
        cwd=project,
        env={
            "CLAUDE_PROJECT_DIR": str(project),
            "LIVESPEC_CODEX_BACKGROUND_MEMORY_DB": str(db_path),
        },
        expected_keys=_WARNING_KEYS,
    )


def _supervisor_state(*, topic: str = "topic") -> dict[str, object]:
    updated_at = (
        datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    return {
        "supervision_active": True,
        "topic": topic,
        "updated_at": updated_at,
        "objective": "Watch the supervised plan.",
        "open_obligations": [],
        "completion_disposition": {"kind": "plan-complete", "question": None},
        "wake_producer": {
            "kind": "ledger",
            "live_pid": None,
            "expected_command": None,
            "identity": f"ledger:{topic}",
            "registered_producer_identity": f"ledger:{topic}",
            "cold_reentry": (
                f"cold-open tmp/overseer/{topic}/.supervisor-state and re-query fresh ledger state"
            ),
        },
    }


def _write_marker(*, project: Path, text: str, topic: str = "topic") -> None:
    marker = project / "tmp" / "overseer" / topic / ".supervisor-state"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(text, encoding="utf-8")


def _supervisor_open_obligations_block(*, root: Path) -> StopScenario:
    """The gate working as designed: an active marker with an unmet obligation."""
    project = _governed_project(root=root)
    state = _supervisor_state()
    state["open_obligations"] = ["verify the dispatched worker"]
    _write_marker(project=project, text=json.dumps(state))
    return StopScenario(
        script="supervisor_completion_gate.py",
        stdin=_stop_stdin(),
        cwd=project,
        env={"CLAUDE_PROJECT_DIR": str(project)},
        expected_keys=_BLOCK_KEYS,
    )


def _supervisor_malformed_marker_block(*, root: Path) -> StopScenario:
    """The incident's own case: an unparseable marker must still block."""
    project = _governed_project(root=root)
    _write_marker(project=project, text="{not-json")
    return StopScenario(
        script="supervisor_completion_gate.py",
        stdin=_stop_stdin(),
        cwd=project,
        env={"CLAUDE_PROJECT_DIR": str(project)},
        expected_keys=_BLOCK_KEYS,
    )


def _supervisor_fail_closed_block(*, root: Path) -> StopScenario:
    """Malformed stdin raises past `_decision()` into the fail-closed boundary."""
    project = _governed_project(root=root)
    return StopScenario(
        script="supervisor_completion_gate.py",
        stdin="{",
        cwd=project,
        env={"CLAUDE_PROJECT_DIR": str(project)},
        expected_keys=_BLOCK_KEYS,
    )


_SCENARIO_BUILDERS: Final[Mapping[str, Callable[..., StopScenario]]] = {
    "no-shadow-ledger warns on a checkbox planning artifact": _no_shadow_ledger_warning,
    "background-memory audit warns on a populated store": _background_memory_audit_warning,
    "supervisor gate blocks open obligations": _supervisor_open_obligations_block,
    "supervisor gate blocks a malformed marker": _supervisor_malformed_marker_block,
    "supervisor gate fail-closed blocks on malformed stdin": _supervisor_fail_closed_block,
}

STOP_SCENARIO_LABELS: Final = tuple(_SCENARIO_BUILDERS)


def build_stop_scenarios(*, root: Path) -> dict[str, StopScenario]:
    """Materialize every scenario's fixtures under `root`, keyed by label.

    Each scenario gets its own subdirectory so the supervisor cases — which all
    write a `tmp/overseer/topic/.supervisor-state` marker — cannot overwrite one
    another.
    """
    return {
        label: builder(root=root / f"scenario-{index}")
        for index, (label, builder) in enumerate(_SCENARIO_BUILDERS.items())
    }
