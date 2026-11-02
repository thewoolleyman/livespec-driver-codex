#!/usr/bin/env python3
"""Install or verify the Codex hook-cache observer as a macOS LaunchAgent.

Run from a released, durable primary Driver checkout. The observer remains
outside Codex's disposable plugin cache, and launchd restarts it after failure
and at operator login. This command changes no Codex settings or hook guards.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys
import time
from pathlib import Path

LABEL = "com.livespec.codex-hook-cache"


def records(*, home: Path) -> list[dict]:
    """Read observer runtime records, never plugin trust or credentials."""
    root = home / ".local" / "state" / "livespec-driver-codex"
    found = []
    for path in root.glob("**/observer*.json"):
        try:
            value = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            found.append(value)
    return found


def managed_pid(*, output: str) -> int | None:
    """Read launchd's process identity rather than trusting a stale heartbeat."""
    match = re.search(r"^\s*pid = (\d+)\s*$", output, re.MULTILINE)
    return int(match[1]) if match else None


def healthy(*, output: str, desired: dict, home: Path) -> bool:
    """Require a running managed PID, its fresh heartbeat, and real repair health."""
    pid = managed_pid(output=output)
    if "state = running" not in output or pid is None:
        return False
    owned = [row for row in records(home=home) if row.get("pid") == pid]
    if not owned or any(
        not isinstance(row.get("heartbeat_epoch"), int | float)
        or not 0 <= time.time() - row["heartbeat_epoch"] < 60
        or row.get("last_error")
        for row in owned
    ):
        return False
    argv = desired["ProgramArguments"]
    result = subprocess.run(
        [*argv[:2], "status", *argv[3:]], capture_output=True, text=True, check=False
    )
    return result.returncode == 0


def refuse_detached(*, home: Path, managed: int | None) -> None:
    """Never turn a runtime record into authority to kill an arbitrary process."""
    for row in records(home=home):
        pid = row.get("pid")
        if not isinstance(pid, int) or pid <= 0 or pid == managed:
            continue
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise ValueError(
            f"observer record references live unmanaged pid {pid}; verify its command "
            "and retire that exact detached observer before installing the LaunchAgent"
        )


def definition(*, driver_root: Path, codex_home: Path, interpreter: Path, home: Path) -> dict:
    """Render argv as a plist array so spaces and shell characters stay data."""
    log = home / "Library" / "Logs" / "livespec-driver-codex" / "hook-cache-observer.log"
    return {
        "Label": LABEL,
        "ProgramArguments": [
            str(interpreter),
            str(driver_root / "dev-tooling" / "codex_hook_cache_observe.py"),
            "run",
            "--codex-home",
            str(codex_home),
        ],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "EnvironmentVariables": {"LIVESPEC_CODEX_HOOK_CACHE_SUPERVISOR": "launchd"},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
    }


def validate_source(*, driver_root: Path, codex_home: Path, interpreter: Path) -> None:
    """Refuse paths whose cleanup would recreate the original missing-file bug."""
    if driver_root.is_relative_to(codex_home / "plugins" / "cache"):
        raise ValueError("observer source must be outside Codex's managed plugin cache")
    git_dirs = subprocess.run(
        ["git", "-C", str(driver_root), "rev-parse", "--git-dir", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    paths = [(driver_root / value).resolve() for value in git_dirs]
    if len(paths) != 2 or paths[0] != paths[1]:
        raise ValueError("observer source must be a durable primary checkout, not a worktree")
    for name in (
        "codex_hook_cache_observe.py",
        "codex_hook_cache_reconcile.py",
        "_codex_hook_cache_payload.py",
        "_codex_hook_cache_process.py",
    ):
        if not (driver_root / "dev-tooling" / name).is_file():
            raise ValueError(f"observer source is incomplete: {name}")
    subprocess.run(
        [str(interpreter), "-c", "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"],
        capture_output=True,
        check=True,
    )


def converge(*, desired: dict, home: Path, uid: int, check_only: bool) -> int:
    """Manage only this named user agent, leaving unrelated services alone."""
    path = home / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    body = plistlib.dumps(desired, sort_keys=True)
    same = path.is_file() and path.read_bytes() == body
    target = f"gui/{uid}/{LABEL}"
    loaded = subprocess.run(
        ["launchctl", "print", target], capture_output=True, text=True, check=False
    )
    running = loaded.returncode == 0 and healthy(output=loaded.stdout, desired=desired, home=home)
    if check_only:
        return 0 if same and running else 1
    if same and running:
        return 0
    refuse_detached(home=home, managed=managed_pid(output=loaded.stdout))
    if loaded.returncode == 0:
        subprocess.run(["launchctl", "bootout", target], check=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(desired["StandardOutPath"]).parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(f".{path.name}.{os.getpid()}")
    staging.write_bytes(body)
    staging.chmod(0o600)
    staging.replace(path)
    subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(path)], check=True)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["launchctl", "print", target], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and healthy(output=result.stdout, desired=desired, home=home):
            return 0
        time.sleep(0.25)
    raise RuntimeError("LaunchAgent did not publish its own healthy observer heartbeat within 15s")


def main(argv: list[str] | None = None) -> int:
    """Install explicitly; default to a read-only configuration/lifecycle check."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--driver-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument(
        "--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", "~/.codex"))
    )
    parser.add_argument("--python", type=Path, default=Path("/opt/homebrew/bin/python3"))
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--print", dest="print_definition", action="store_true")
    args = parser.parse_args(argv)
    home = Path.home()
    root = args.driver_root.expanduser().resolve()
    codex_home = args.codex_home.expanduser().resolve()
    # Preserve the stable interpreter symlink: resolving it would pin the
    # versioned Homebrew cellar directory that a Python update later deletes.
    interpreter = args.python.expanduser().absolute()
    desired = definition(
        driver_root=root, codex_home=codex_home, interpreter=interpreter, home=home
    )
    if args.print_definition:
        sys.stdout.write(plistlib.dumps(desired).decode())
        return 0
    if sys.platform != "darwin":
        sys.stderr.write("This installer requires macOS and the operator's GUI login session.\n")
        return 1
    try:
        validate_source(driver_root=root, codex_home=codex_home, interpreter=interpreter)
        code = converge(desired=desired, home=home, uid=os.getuid(), check_only=not args.install)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        sys.stderr.write(f"hook-cache LaunchAgent failed: {error}\n")
        return 1
    if code:
        sys.stderr.write("hook-cache LaunchAgent is absent or has drift; run with --install.\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
