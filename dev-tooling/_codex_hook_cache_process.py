"""Liveness record and process lifecycle for the hook-cache observer.

The half of the observer that answers "is a healthy watcher running, and
if not, start one?" — kept separate from the watch loop so neither grows
past the repo's per-file complexity ceiling. Sibling-imported by
`codex_hook_cache_observe`, stdlib-only for the same bare-`python3`
provisioning reason.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

STALE_AFTER_SECONDS = 60.0
_START_TIMEOUT_SECONDS = 10.0


def runtime_dir(*, state_path: Path) -> Path:
    """Directory holding the observer's liveness record and log."""
    return state_path.parent


def status_file(*, state_path: Path) -> Path:
    """The observer's liveness record."""
    return runtime_dir(state_path=state_path) / "observer.json"


def log_file(*, state_path: Path) -> Path:
    """Where a detached observer's structured output lands."""
    return runtime_dir(state_path=state_path) / "observer.log"


def write_status(*, path: Path, pid: int, last_error: str | None) -> None:
    """Record liveness plus the outcome of the last reconcile attempt."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(
        {
            "pid": pid,
            "heartbeat_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "heartbeat_epoch": time.time(),
            "last_error": last_error,
        },
        indent=2,
        sort_keys=True,
    )
    staging = path.with_name(f".{path.name}.livespec-observe.{os.getpid()}")
    staging.write_text(body + "\n", encoding="utf-8")
    staging.replace(path)


def read_status(*, path: Path) -> dict[str, object] | None:
    """Parse the liveness record, or None when it is absent or malformed."""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def pid_alive(*, pid: int) -> bool:
    """Whether a process with this pid exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def health(*, path: Path, now: float | None = None) -> tuple[bool, str]:
    """Whether a healthy observer owns this runtime dir, and why not if it does not.

    A stale heartbeat and a failed last reconcile both count as unhealthy:
    an observer that is running but not repairing is exactly the silent
    failure this machinery exists to prevent.
    """
    status = read_status(path=path)
    if status is None:
        return False, "no observer status record"
    pid = status.get("pid")
    if not isinstance(pid, int) or not pid_alive(pid=pid):
        return False, f"observer pid {pid} is not running"
    beat = status.get("heartbeat_epoch")
    if not isinstance(beat, int | float):
        return False, "observer status record carries no heartbeat"
    age = (time.time() if now is None else now) - float(beat)
    if age > STALE_AFTER_SECONDS:
        return False, f"observer heartbeat is stale ({age:.0f}s old)"
    last_error = status.get("last_error")
    if isinstance(last_error, str) and last_error:
        return False, f"last reconcile failed: {last_error}"
    return True, "observer is running and healthy"


def spawn(*, entry_point: Path, interpreter: str, root: Path, state_path: Path) -> int:
    """Start a detached observer and return its pid."""
    runtime_dir(state_path=state_path).mkdir(parents=True, exist_ok=True)
    log = log_file(state_path=state_path).open("a", encoding="utf-8")
    argv = [
        interpreter,
        str(entry_point),
        "run",
        "--codex-home",
        str(root.parents[3]),
        "--marketplace",
        root.parent.name,
        "--plugin",
        root.name,
        "--state",
        str(state_path),
    ]
    # argv is built from resolved local paths, never from shell input.
    child = subprocess.Popen(
        argv,
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    return child.pid


def stop(*, state_path: Path) -> None:
    """Terminate a previously-recorded observer, if one is still alive."""
    status = read_status(path=status_file(state_path=state_path))
    pid = (status or {}).get("pid")
    if isinstance(pid, int) and pid != os.getpid() and pid_alive(pid=pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return


def ensure(
    *, entry_point: Path, interpreter: str, root: Path, state_path: Path
) -> tuple[bool, str]:
    """Start the observer unless a healthy one is already running."""
    healthy, why = health(path=status_file(state_path=state_path))
    if healthy:
        return True, why
    stop(state_path=state_path)
    pid = spawn(entry_point=entry_point, interpreter=interpreter, root=root, state_path=state_path)
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        healthy, why = health(path=status_file(state_path=state_path))
        if healthy:
            return True, f"observer started (pid {pid})"
        time.sleep(0.1)
    return False, f"observer failed to become healthy after start (pid {pid}): {why}"
