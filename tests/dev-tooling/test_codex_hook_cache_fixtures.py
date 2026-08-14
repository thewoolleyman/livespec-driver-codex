"""Shared builders for the hook-cache reconciler/observer suite, and their own test.

The modules under test live in `dev-tooling/`, a directory whose name is
not a valid Python identifier, so they are imported the same way the
runtime imports them: by putting their own directory on `sys.path` and
importing them as top-level modules. The sibling test modules import the
builders below from here.

The builders are only as useful as their fidelity to a real payload, so
this module carries the test that pins exactly that.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEV_TOOLING = Path(__file__).resolve().parents[2] / "dev-tooling"
if str(DEV_TOOLING) not in sys.path:
    sys.path.insert(0, str(DEV_TOOLING))

import codex_hook_cache_observe as observer  # noqa: E402  — needs the sys.path insert above
import codex_hook_cache_reconcile as reconciler  # noqa: E402  — same

HOOK_SCRIPT_BODY = "import sys\n\nsys.exit(0)\n"


def link_target(*, path: Path) -> str:
    """The literal target string of an alias symlink."""
    return Path.readlink(path).as_posix()


def write_payload(
    *,
    root: Path,
    version: str,
    hook_body: str = HOOK_SCRIPT_BODY,
    manifest_hooks: str | None = "./hooks/hooks.json",
    drop_hook_script: bool = False,
) -> Path:
    """Build a version payload shaped like a real Codex plugin cache entry."""
    payload = root / version
    (payload / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    (payload / "hooks").mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"name": "livespec", "version": version}
    if manifest_hooks is not None:
        manifest["hooks"] = manifest_hooks
    (payload / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    (payload / "hooks" / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/guard.py"',
                                }
                            ],
                        }
                    ],
                    "Stop": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/stop.py"',
                                }
                            ]
                        }
                    ],
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (payload / "hooks" / "guard.py").write_text(hook_body, encoding="utf-8")
    if not drop_hook_script:
        (payload / "hooks" / "stop.py").write_text(hook_body, encoding="utf-8")
    return payload


def test_the_builder_produces_a_payload_the_real_validator_accepts(tmp_path: Path) -> None:
    """Fidelity check: a mock payload must satisfy the same validation a real one does.

    Without this the whole mock suite could pass against a payload shape
    the reconciler would reject in the field — or, worse, one it accepts
    only because the builder omits what real payloads carry.
    """
    payload = write_payload(root=tmp_path, version="0.6.1")

    scripts, problems = reconciler.declared_hook_scripts(payload=payload)

    assert not problems
    assert sorted(script.name for script in scripts) == ["guard.py", "stop.py"]
    assert not reconciler.validate_payload(payload=payload)


def test_both_modules_under_test_import_under_a_bare_interpreter() -> None:
    """The sibling import the provisioner relies on must resolve from `dev-tooling/`."""
    assert Path(reconciler.__file__).parent == DEV_TOOLING
    assert Path(observer.__file__).parent == DEV_TOOLING
