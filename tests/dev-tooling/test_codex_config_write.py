"""Serialized, atomic, fresh-read writes to the host's Codex config.toml."""

from __future__ import annotations

import fcntl
import importlib
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_codex_hook_cache_fixtures import DEV_TOOLING, write_payload

_CHILD = """
import sys, time
sys.path.insert(0, {dev_tooling!r})
import codex_config_write as writer
from pathlib import Path

def rewrite(text):
    time.sleep(0.05)
    return text + {line!r} + "\\n"

problem = writer.rewrite_config(config_path=Path({config!r}), rewrite=rewrite)
sys.exit(1 if problem else 0)
"""

_KILL_CHILD = """
import os, signal, sys
sys.path.insert(0, {dev_tooling!r})
import codex_config_write as writer
from pathlib import Path

Path.replace = lambda *args, **kwargs: os.kill(os.getpid(), signal.SIGKILL)
writer.rewrite_config(config_path=Path({config!r}), rewrite=lambda text: text + "added = 1\\n")
"""


def _writer():
    module_path = DEV_TOOLING / "codex_config_write.py"
    assert module_path.is_file()
    return importlib.import_module("codex_config_write")


def _config(tmp_path: Path, body: str = 'model = "x"\n') -> Path:
    config = tmp_path / "codex" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(body, encoding="utf-8")
    return config


def _trust_inputs(tmp_path: Path) -> dict[str, object]:
    cache = tmp_path / "codex" / "plugins" / "cache" / "market" / "plugin"
    release = tmp_path / "release"
    release.mkdir()
    return {
        "marketplace": "market",
        "plugin": "plugin",
        "payload": write_payload(root=cache, version="1.2.3"),
        "release_payload": write_payload(root=release, version="1.2.3"),
    }


def test_concurrent_writer_processes_never_lose_each_others_edits(tmp_path: Path) -> None:
    """Six processes that each read, wait, and write all land their line."""
    _writer()
    config = _config(tmp_path)
    children = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CHILD.format(
                    dev_tooling=str(DEV_TOOLING), line=f"writer_{n} = {n}", config=str(config)
                ),
            ]
        )
        for n in range(6)
    ]

    assert [child.wait(timeout=60) for child in children] == [0] * 6
    text = config.read_text(encoding="utf-8")
    assert text.startswith('model = "x"\n')
    assert all(f"writer_{n} = {n}\n" in text for n in range(6))


def test_a_write_killed_before_the_replace_leaves_the_complete_prior_file(
    tmp_path: Path,
) -> None:
    """An interrupted write leaves the prior bytes, and the next writer proceeds."""
    writer = _writer()
    config = _config(tmp_path)
    prior = config.read_bytes()

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            _KILL_CHILD.format(dev_tooling=str(DEV_TOOLING), config=str(config)),
        ],
        check=False,
    )

    assert child.returncode == -signal.SIGKILL
    assert config.read_bytes() == prior
    assert (
        writer.rewrite_config(config_path=config, rewrite=lambda text: text + "after = 1\n") is None
    )
    assert config.read_text(encoding="utf-8") == prior.decode() + "after = 1\n"


def test_a_failed_replace_reports_a_problem_and_leaves_no_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prior file survives a failing replace, with no stray temporary beside it."""
    writer = _writer()
    config = _config(tmp_path)
    prior = config.read_bytes()

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "replace", refuse)

    problem = writer.rewrite_config(config_path=config, rewrite=lambda text: text + "added = 1\n")

    assert problem is not None
    assert "disk full" in problem
    assert config.read_bytes() == prior
    assert sorted(path.name for path in config.parent.iterdir() if path.name != "plugins") == [
        "config.toml",
        "config.toml.livespec-lock",
    ]


def test_a_writer_that_cannot_take_the_lock_in_time_writes_nothing(tmp_path: Path) -> None:
    """The wait is bounded: a held lock yields a reported problem, not a write."""
    writer = _writer()
    config = _config(tmp_path)
    prior = config.read_bytes()
    lock_fd = os.open(config.parent / "config.toml.livespec-lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        started = time.monotonic()
        problem = writer.rewrite_config(
            config_path=config, rewrite=lambda text: text + "added = 1\n", wait_seconds=0.2
        )
        elapsed = time.monotonic() - started
    finally:
        os.close(lock_fd)

    assert problem is not None
    assert "lock" in problem
    assert elapsed < 5
    assert config.read_bytes() == prior


def test_the_bounded_wait_is_stated_and_a_killed_lock_holder_releases_it(tmp_path: Path) -> None:
    """The stated wait covers a holder killed mid-write, whose lock the kernel drops."""
    writer = _writer()
    assert 0 < writer.CONFIG_LOCK_WAIT_SECONDS <= 60
    config = _config(tmp_path)
    lock_path = str(config.parent / "config.toml.livespec-lock")
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time\n"
            f"fd = os.open({lock_path!r}, os.O_RDWR | os.O_CREAT)\n"
            "fcntl.flock(fd, fcntl.LOCK_EX)\n"
            "print('held', flush=True)\n"
            "time.sleep(60)\n",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "held"
    holder.kill()
    holder.wait(timeout=10)

    assert (
        writer.rewrite_config(config_path=config, rewrite=lambda text: text + "after = 1\n") is None
    )
    assert config.read_text(encoding="utf-8").endswith("after = 1\n")


def test_the_replace_keeps_file_permissions_and_a_symlinks_target(tmp_path: Path) -> None:
    """Permissions carry over, and a symlinked config has its target replaced."""
    writer = _writer()
    real = tmp_path / "dotfiles" / "codex.toml"
    real.parent.mkdir()
    real.write_text("a = 1\n", encoding="utf-8")
    real.chmod(0o640)
    link = tmp_path / "codex" / "config.toml"
    link.parent.mkdir()
    link.symlink_to(real)

    assert writer.rewrite_config(config_path=link, rewrite=lambda text: text + "b = 2\n") is None

    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "a = 1\nb = 2\n"
    assert stat.S_IMODE(real.stat().st_mode) == 0o640


def test_a_new_config_is_created_private_and_an_unchanged_rewrite_writes_nothing(
    tmp_path: Path,
) -> None:
    """A missing file starts empty and private; a no-op rewrite leaves the file as is."""
    writer = _writer()
    config = tmp_path / "fresh" / "codex" / "config.toml"

    assert writer.rewrite_config(config_path=config, rewrite=lambda text: text + "a = 1\n") is None
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    before = config.stat().st_ino

    assert writer.rewrite_config(config_path=config, rewrite=lambda text: text) is None
    assert config.stat().st_ino == before


def test_a_rewrite_that_rejects_the_text_is_reported_and_writes_nothing(tmp_path: Path) -> None:
    """A rewrite may refuse the text it was handed; nothing is written."""
    writer = _writer()
    config = _config(tmp_path)
    prior = config.read_bytes()

    def refuse(_text: str) -> str:
        raise writer.ConfigWriteError("unrecognized Codex trust record format")

    problem = writer.rewrite_config(config_path=config, rewrite=refuse)

    assert problem == "unrecognized Codex trust record format"
    assert config.read_bytes() == prior


def test_an_unusable_config_location_is_reported(tmp_path: Path) -> None:
    """A parent that cannot be created is a reported problem, not a traceback."""
    writer = _writer()
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")

    problem = writer.rewrite_config(
        config_path=blocker / "codex" / "config.toml", rewrite=lambda text: text + "a = 1\n"
    )

    assert problem is not None


def test_trust_writes_wait_for_the_lock_and_report_the_plugin_when_it_times_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trust write that cannot get the lock writes nothing and names the plugin and hooks."""
    writer = _writer()
    trust = importlib.import_module("codex_hook_trust")
    config = _config(tmp_path, "[hooks.state]\n")
    prior = config.read_bytes()
    monkeypatch.setattr(writer, "CONFIG_LOCK_WAIT_SECONDS", 0.2)
    lock_fd = os.open(config.parent / "config.toml.livespec-lock", os.O_RDWR | os.O_CREAT)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        report = trust.reconcile_trust(config_path=config, **_trust_inputs(tmp_path))
    finally:
        os.close(lock_fd)

    assert not report.ok
    assert report.trusted_hooks == ()
    assert len(report.problems) == 1
    assert report.problems[0].startswith("plugin: ")
    assert "lock" in report.problems[0]
    assert "hooks/" in report.problems[0] or "plugin@market:" in report.problems[0]
    assert config.read_bytes() == prior


def test_trust_is_computed_from_the_file_as_read_under_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Codex edit landing after the caller started is carried forward, with comments."""
    trust = importlib.import_module("codex_hook_trust")
    _writer()
    config = _config(
        tmp_path, '# operator note\n[hooks.state]\n\n[projects."/work"]\ntrust = "yes"\n'
    )
    real_hash = trust._plugin_content_hash

    def hash_then_codex_edits(*, root: Path) -> tuple[str, str | None]:
        result = real_hash(root=root)
        with config.open("a", encoding="utf-8") as handle:
            handle.write('[tui]\ntheme = "dark"\n')
        return result

    monkeypatch.setattr(trust, "_plugin_content_hash", hash_then_codex_edits)

    report = trust.reconcile_trust(config_path=config, **_trust_inputs(tmp_path))

    text = config.read_text(encoding="utf-8")
    assert report.ok
    assert text.startswith("# operator note\n")
    assert '[projects."/work"]\ntrust = "yes"\n' in text
    assert '[tui]\ntheme = "dark"\n' in text
    assert text.count("trusted_content_hash") == 2


def test_trust_refuses_a_format_that_only_the_locked_read_reveals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A format change landing after the caller started is rechecked under the lock."""
    trust = importlib.import_module("codex_hook_trust")
    _writer()
    config = _config(tmp_path, "[hooks.state]\n")
    real_hash = trust._plugin_content_hash
    unknown = '[hooks.state]\nsurprise = "new codex format"\n'

    def hash_then_codex_changes_format(*, root: Path) -> tuple[str, str | None]:
        result = real_hash(root=root)
        config.write_text(unknown, encoding="utf-8")
        return result

    monkeypatch.setattr(trust, "_plugin_content_hash", hash_then_codex_changes_format)

    report = trust.reconcile_trust(config_path=config, **_trust_inputs(tmp_path))

    assert not report.ok
    assert report.problems == ("plugin: unrecognized Codex trust record format",)
    assert config.read_text(encoding="utf-8") == unknown


def test_no_driver_surface_invokes_codex_with_the_hook_trust_bypass() -> None:
    """Nothing the Driver ships or runs passes the bypass flag or sets its config key."""
    root = DEV_TOOLING.parent
    scanned = [
        *DEV_TOOLING.glob("*"),
        *(root / "livespec").rglob("*"),
        root / "justfile",
        root / "lefthook.yml",
        *(root / ".github").rglob("*.sh"),
    ]
    offenders = [
        path.relative_to(root).as_posix()
        for path in scanned
        if path.is_file()
        and any(
            marker in path.read_text(encoding="utf-8", errors="ignore")
            for marker in ("dangerously-bypass-hook-trust", "bypass_hook_trust")
        )
    ]

    assert offenders == []
