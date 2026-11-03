"""Obtain a covered plugin's release-tag payload without trusting its cache."""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_TABLE = re.compile(r'^\s*\[marketplaces\.("(?:[^"\\]|\\.)*"|[^]\s]+)]\s*(?:#.*)?$')
_FIELD = re.compile(r'^\s*(source_type|source)\s*=\s*("(?:[^"\\]|\\.)*")\s*(?:#.*)?$')


@dataclass(frozen=True, kw_only=True)
class ReleasePayload:
    """A verified-source checkout payload or an explanation of its absence."""

    payload: Path | None
    problem: str | None


@contextlib.contextmanager
def release_payload(
    *, config_path: Path, marketplace: str, plugin: str, version: str
) -> Iterator[ReleasePayload]:
    """Yield the matching release payload, never falling back to cache bytes."""
    source, problem = marketplace_source(config_path=config_path, marketplace=marketplace)
    if problem:
        yield ReleasePayload(payload=None, problem=problem)
        return
    with tempfile.TemporaryDirectory(prefix="livespec-codex-release-") as scratch:
        checkout = Path(scratch) / "source"
        checkout_problem = checkout_release(source=source, version=version, checkout=checkout)
        if checkout_problem:
            yield ReleasePayload(payload=None, problem=checkout_problem)
            return
        payload, payload_problem = catalog_plugin_payload(checkout=checkout, plugin=plugin)
        yield ReleasePayload(payload=payload, problem=payload_problem)


def marketplace_source(*, config_path: Path, marketplace: str) -> tuple[str | None, str | None]:
    """Read exactly the git source shape Codex records for one marketplace."""
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        return None, f"release tag cannot be identified ({err})"
    active: str | None = None
    fields: dict[str, str] = {}
    for line in lines:
        table = _TABLE.match(line)
        if table:
            try:
                raw = table.group(1)
                active = json.loads(raw) if raw.startswith('"') else raw
            except json.JSONDecodeError:
                return None, "release tag cannot be identified (unrecognized marketplace record)"
            continue
        match = _FIELD.match(line)
        if match and active == marketplace:
            try:
                fields[match.group(1)] = json.loads(match.group(2))
            except json.JSONDecodeError:
                return None, "release tag cannot be identified (unrecognized marketplace record)"
    if fields.get("source_type") != "git" or not fields.get("source"):
        return None, "release tag cannot be identified for this marketplace"
    return fields["source"], None


def checkout_release(*, source: str, version: str, checkout: Path) -> str | None:
    """Clone either conventional release-tag spelling into a disposable root."""
    attempted: list[str] = []
    for tag in (f"v{version}", version):
        result = subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", tag, source, str(checkout)],
            capture_output=True,
            check=False,
            text=True,
            timeout=90,
        )
        if result.returncode == 0:
            return None
        attempted.append(tag)
        if checkout.exists():
            _remove_checkout(checkout=checkout)
    tags = ", ".join(attempted)
    return f"release tag cannot be obtained for installed version {version} ({tags})"


def catalog_plugin_payload(*, checkout: Path, plugin: str) -> tuple[Path | None, str | None]:
    """Resolve a plugin from the source's tagged marketplace catalog."""
    for catalog in (
        checkout / ".agents" / "plugins" / "marketplace.json",
        checkout / "marketplace.json",
    ):
        try:
            document = json.loads(catalog.read_text(encoding="utf-8"))
        except OSError:
            continue
        except json.JSONDecodeError:
            return None, "release tag cannot be verified (invalid marketplace catalog)"
        plugins = document.get("plugins") if isinstance(document, dict) else None
        if not isinstance(plugins, list):
            return None, "release tag cannot be verified (invalid marketplace catalog)"
        for entry in plugins:
            if not isinstance(entry, dict) or entry.get("name") != plugin:
                continue
            source = entry.get("source")
            relative = source.get("path") if isinstance(source, dict) else None
            if not isinstance(relative, str) or not relative:
                return None, "release tag cannot be verified (invalid plugin source path)"
            payload = checkout / relative
            if payload.is_dir() and payload.is_relative_to(checkout):
                return payload, None
            return None, "release tag cannot be verified (plugin payload is missing)"
        return None, f"release tag cannot be verified (plugin {plugin!r} is absent)"
    return None, "release tag cannot be verified (marketplace catalog is missing)"


def _remove_checkout(*, checkout: Path) -> None:
    """Remove a failed temporary clone before attempting the alternate tag."""
    for path in sorted(checkout.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.unlink() if path.is_file() or path.is_symlink() else path.rmdir()
    checkout.rmdir()
