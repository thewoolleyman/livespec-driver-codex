"""Serialized, atomic, fresh-read writes to the host's Codex ``config.toml``.

Codex records hook trust in a file that Codex itself writes and that the
reconciler run by ``ensure-codex-plugins`` and the one run by the observer may
write at the same time.  Every Driver write goes through ``rewrite_config`` so
that (a) Driver writers are serialized through an advisory lock on a sibling
lock file, keyed to the target file rather than to a process or install, (b)
the file is replaced atomically, and (c) the new contents are computed from the
text read while the lock is held.  Codex does not take the lock, so (c) narrows
but cannot close the window in which a Codex edit could be overwritten.

The wait for the lock is bounded by ``CONFIG_LOCK_WAIT_SECONDS``.  A writer
that cannot take the lock in that time writes nothing and reports a problem.
The kernel drops a flock when its holder dies, so a writer killed mid-write
never wedges the others.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Iterator
from pathlib import Path

CONFIG_LOCK_WAIT_SECONDS = 10.0
_LOCK_POLL_SECONDS = 0.05
_LOCK_SUFFIX = ".livespec-lock"


class ConfigWriteError(Exception):
    """A config write was refused; the message names the reason."""


def rewrite_config(
    *,
    config_path: Path,
    rewrite: Callable[[str], str],
    wait_seconds: float | None = None,
) -> str | None:
    """Apply ``rewrite`` to the config text under the lock; return a problem or None."""
    wait = CONFIG_LOCK_WAIT_SECONDS if wait_seconds is None else wait_seconds
    target = Path(os.path.realpath(config_path))
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with _locked(lock_path=target.with_name(target.name + _LOCK_SUFFIX), wait_seconds=wait):
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            updated = rewrite(text)
            if updated != text:
                _replace_atomically(target=target, text=updated)
    except ConfigWriteError as err:
        return str(err)
    except OSError as err:
        return f"could not write {target}: {err}"
    return None


@contextlib.contextmanager
def _locked(*, lock_path: Path, wait_seconds: float) -> Iterator[None]:
    """Hold an exclusive flock on the sibling lock file, waiting a bounded time."""
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ConfigWriteError(
                        f"could not take the lock {lock_path} within {wait_seconds:g}s"
                    ) from None
                time.sleep(_LOCK_POLL_SECONDS)
        yield
    finally:
        os.close(descriptor)


def _replace_atomically(*, target: Path, text: str) -> None:
    """Write a same-directory temporary file and rename it over the target."""
    descriptor, temporary = tempfile.mkstemp(dir=target.parent, prefix=f"{target.name}.")
    replaced = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            _ = handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            shutil.copymode(target, temporary)
        _ = Path(temporary).replace(target)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                Path(temporary).unlink()
