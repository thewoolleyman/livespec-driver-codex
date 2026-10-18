"""Unit tests for `livespec/hooks/_memory_shell_writes.py`.

The classifier behind the auto-memory guard's Bash route. Every command string
here is inert DATA handed to a pure function; nothing is ever executed.

Contract under test: a command is a memory write only when the guard can READ
the written path from the command text and that path is in an agent memory
directory (the Codex store `~/.codex/memories/` or the Claude Code layout
`~/.claude/projects/<slug>/memory/*.md`). Reads, removals, writes elsewhere, a
runtime-computed destination, and an unlexable segment are all NOT a write.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

__all__: list[str] = []

_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "livespec" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from _memory_shell_writes import (  # noqa: E402 — path-dependent hook import.
    command_writes_memory,
    is_memory_path,
)

_CODEX = Path.home() / ".codex" / "memories"
_CLAUDE = Path.home() / ".claude" / "projects" / "-data-projects-demo" / "memory"

_WRITES = [
    f"echo x &> {_CODEX}/a.md",
    f"echo x > {_CODEX}/a.md 2>&1",
    f"cat <<EOF > {_CODEX}/a.md\nbody\nEOF",
    "echo x > ${HOME}/.codex/memories/a.md",
    f"sudo tee {_CODEX}/a.md",
    f"sed --in-place -e 's/a/b/' {_CLAUDE}/a.md",
    f"perl -pi -e 's/a/b/' {_CODEX}/a.md",
    f"perl -i.bak -pe 's/a/b/' {_CLAUDE}/a.md",
    f"install -m 644 /tmp/a.md {_CODEX}/a.md",
    f"ln -s /tmp/a.md {_CLAUDE}/a.md",
    f"cp -t {_CODEX} /tmp/a.md",
    f"cp --target-directory={_CLAUDE} /tmp/a.md",
    f"touch -r /tmp/ref {_CODEX}/a.md",
    f"truncate -s 0 {_CLAUDE}/a.md",
    f"dd if=/tmp/a of={_CODEX}/a.md",
    f"python3 -c \"from pathlib import Path; Path('{_CODEX}/a.md').write_text('x')\"",
    f"python3 -Ic \"open('{_CLAUDE}/a.md', mode='a').write('x')\"",
    f'perl -e \'open(my $f, ">", "{_CODEX}/a.md")\'',
    f"node -e \"require('fs').writeFileSync('{_CODEX}/a.md', 'x')\"",
    f'sh -lc "cp /tmp/a.md {_CODEX}/"',
    f"(echo x > {_CODEX}/a.md)",
    f"cp /tmp/a.md {_CLAUDE}",
]

_NOT_WRITES = [
    "",
    "git status",
    f"python3 -c \"print(open('{_CODEX}/a.md').read())\"",
    "python3 -c \"open('/tmp/a.md', 'w').write('x')\"",
    f"python3 {_CODEX}/script.py",
    "python3",
    "perl -i -pe 's/a/b/' /tmp/a.md",
    f"sed 's/a/b/' {_CODEX}/a.md",
    f"cp {_CODEX}/a.md /tmp/",
    f"cp {_CODEX}/a.md",
    f"touch -r {_CODEX}/ref.md /tmp/a.md",
    f"mv {_CLAUDE}/a.md /tmp/a.md",
    'echo x > "$DEST"',
    "bash -c",
    "bash script.sh",
    f"echo 'unterminated > {_CODEX}/a.md",
    "A=1",
    "echo x >",
    f"cat < {_CODEX}/a.md",
    "echo x > /tmp/memory/notes.txt",
    f"echo x > {Path.home()}/.claude/projects/s/notmemory",
]


@pytest.mark.parametrize("command", _WRITES)
def test_identifies_a_write_into_a_memory_directory(command: str) -> None:
    assert command_writes_memory(command=command)


@pytest.mark.parametrize("command", _NOT_WRITES)
def test_does_not_identify_reads_removals_or_unreadable_destinations(command: str) -> None:
    assert not command_writes_memory(command=command)


def test_nesting_beyond_the_depth_limit_is_a_stated_limit() -> None:
    inner = f"echo x > {_CODEX}/a.md"
    nested = inner
    for _ in range(5):
        nested = f"sh -c {_quote(text=nested)}"
    assert not command_writes_memory(command=nested)


def _quote(*, text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def test_is_memory_path_spellings() -> None:
    assert is_memory_path(path_str="~/.codex/memories")
    assert is_memory_path(path_str="~") is False
    assert is_memory_path(path_str="$HOME/.codex/memories/x/y.json")
    assert is_memory_path(path_str=f"{_CLAUDE}/")
    assert not is_memory_path(path_str="")
    assert not is_memory_path(path_str=f"{_CLAUDE}/a.txt")
