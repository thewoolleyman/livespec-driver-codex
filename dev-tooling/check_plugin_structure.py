"""check_plugin_structure — structural gate for the Codex Driver plugin bundle.

Stdlib-only (runs under bare python3; no venv required). The Codex
Driver's layout differs from the Claude Driver's: a Codex plugin cannot
live at `source.path: "."`, so the plugin sits in the `livespec/`
subdir and the marketplace catalog at the repo root
(`.agents/plugins/marketplace.json`) points at it. This check validates
THAT layout. It asserts:

1. `.agents/plugins/marketplace.json` parses as JSON; its top-level
   `name` is `livespec-driver-codex`; it lists exactly one plugin entry
   named `livespec` whose `source` is `{"source":"local","path":"./livespec"}`
   and whose `description` duplicates the plugin manifest's verbatim
   (`livespec/.codex-plugin/plugin.json` is the source of truth).
2. `livespec/.codex-plugin/plugin.json` parses as JSON; its `name` is
   `livespec`; its `version` is non-empty; `skills` is `./skills/`;
   `hooks` is `./hooks/hooks.json`.
3. All eight operations ship a SKILL.md under `livespec/skills/<op>/`
   whose `---`-fenced frontmatter `name` matches its directory and
   carries a non-empty `description`; no extra skill directories exist.
4. Codex-binding body rules inside every SKILL.md: the body MUST carry
   the Codex core-resolution invocation `codex plugin list --json -m
   livespec`, and MUST NOT carry any of the Claude-specific markers — a
   `/livespec:` slash-form invocation, the Claude `installed_plugins.json`
   resolution artifact, the literal phrase `Claude Code Driver`, the
   sibling repo name `livespec-driver-claude`, or an `allowed-tools`
   frontmatter key.
5. Fenced wrapper-invocation rules inside every SKILL.md: any fenced
   line invoking a `bin/<name>.py` wrapper MUST use the
   `$LIVESPEC_CORE_ROOT` resolution variable, MUST NOT use `uv run`,
   MUST NOT use a literal `.claude-plugin/scripts` path, and MUST NOT
   use the Driver's own plugin-root placeholder (`CLAUDE_PLUGIN_ROOT`
   would resolve to the Driver root, which carries no scripts).
6. `livespec/hooks/hooks.json` parses as JSON, has NO top-level
   `description` key (Codex's parser rejects it), and registers a
   `PreToolUse` entry with matcher `Bash` whose command references
   `livespec_footgun_guard.py`. The guard script
   `livespec/hooks/livespec_footgun_guard.py` exists.

Exit 0 when every assertion holds; exit 1 with one line per violation
on stderr otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MARKETPLACE = _REPO_ROOT / ".agents" / "plugins" / "marketplace.json"
_PLUGIN_DIR = _REPO_ROOT / "livespec"
_PLUGIN_MANIFEST = _PLUGIN_DIR / ".codex-plugin" / "plugin.json"
_SKILLS_DIR = _PLUGIN_DIR / "skills"
_HOOKS_JSON = _PLUGIN_DIR / "hooks" / "hooks.json"
_GUARD_SCRIPT = _PLUGIN_DIR / "hooks" / "livespec_footgun_guard.py"

_EXPECTED_SKILLS = frozenset(
    {
        "seed",
        "propose-change",
        "critique",
        "revise",
        "doctor",
        "prune-history",
        "next",
        "help",
    }
)

# The Codex core-resolution invocation every SKILL.md body MUST carry.
_CODEX_RESOLUTION_SNIPPET = "codex plugin list --json -m livespec"

_WRAPPER_INVOCATION_RE = re.compile(r"bin/[a-z_]+\.py\b")
_FRONTMATTER_NAME_RE = re.compile(r"^name:\s*(\S+)\s*$", re.MULTILINE)
_FRONTMATTER_DESCRIPTION_RE = re.compile(r"^description:\s*(\S.*?)\s*$", re.MULTILINE)
# Assembled from parts so this checker file itself never contains the
# literal placeholder token it bans (a plugin loader textually
# substitutes the token anywhere it appears in plugin-shipped files).
_DRIVER_ROOT_TOKEN = "CLAUDE_PLUGIN" + "_ROOT"


def _frontmatter_block(*, text: str) -> str | None:
    """Return the `---`-fenced frontmatter block, or None if absent/malformed.

    The block MUST be the first thing in the file: an opening `---` line,
    body lines, then a closing `---` line.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[1:idx])
    return None


def _marketplace_violations() -> tuple[list[str], str | None]:
    """Validate the repo-root marketplace catalog.

    Returns (violations, plugin_description) — the catalog's plugin
    description is returned so the manifest check can compare it as the
    source of truth.
    """
    out: list[str] = []
    try:
        marketplace = json.loads(_MARKETPLACE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f".agents/plugins/marketplace.json unreadable/invalid: {exc}"], None
    if marketplace.get("name") != "livespec-driver-codex":
        out.append(
            "marketplace.json name MUST be 'livespec-driver-codex'; "
            f"got {marketplace.get('name')!r}"
        )
    entries = marketplace.get("plugins", [])
    if len(entries) != 1:
        out.append(f"marketplace.json MUST list exactly one plugin; got {len(entries)}")
        return out, None
    entry = entries[0]
    if entry.get("name") != "livespec":
        out.append(f"marketplace plugin entry name MUST be 'livespec'; got {entry.get('name')!r}")
    expected_source = {"source": "local", "path": "./livespec"}
    if entry.get("source") != expected_source:
        out.append(
            "marketplace plugin entry source MUST be "
            f"{expected_source!r}; got {entry.get('source')!r}"
        )
    return out, entry.get("description")


def _manifest_violations(*, marketplace_description: str | None) -> list[str]:
    """Validate the Codex plugin manifest (source of truth for description)."""
    out: list[str] = []
    try:
        plugin = json.loads(_PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"livespec/.codex-plugin/plugin.json unreadable/invalid: {exc}"]
    if plugin.get("name") != "livespec":
        out.append(f"plugin.json name MUST be 'livespec'; got {plugin.get('name')!r}")
    if not plugin.get("version"):
        out.append(f"plugin.json version MUST be non-empty; got {plugin.get('version')!r}")
    if plugin.get("skills") != "./skills/":
        out.append(f"plugin.json skills MUST be './skills/'; got {plugin.get('skills')!r}")
    if plugin.get("hooks") != "./hooks/hooks.json":
        out.append(f"plugin.json hooks MUST be './hooks/hooks.json'; got {plugin.get('hooks')!r}")
    if marketplace_description is not None and plugin.get("description") != marketplace_description:
        out.append(
            "marketplace plugin description MUST duplicate plugin.json's verbatim "
            "(plugin.json is the source of truth)"
        )
    return out


def _skill_set_violations() -> list[str]:
    out: list[str] = []
    if not _SKILLS_DIR.is_dir():
        return [f"missing skills directory: {_SKILLS_DIR.relative_to(_REPO_ROOT)}/"]
    found = {p.name for p in _SKILLS_DIR.iterdir() if p.is_dir()}
    for missing in sorted(_EXPECTED_SKILLS - found):
        out.append(f"missing skill directory: skills/{missing}/")
    for extra in sorted(found - _EXPECTED_SKILLS):
        out.append(f"unexpected skill directory: skills/{extra}/")
    for name in sorted(_EXPECTED_SKILLS & found):
        skill_md = _SKILLS_DIR / name / "SKILL.md"
        if not skill_md.is_file():
            out.append(f"missing skills/{name}/SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        frontmatter = _frontmatter_block(text=text)
        if frontmatter is None:
            out.append(f"skills/{name}/SKILL.md MUST open with a `---`-fenced frontmatter block")
            continue
        name_match = _FRONTMATTER_NAME_RE.search(frontmatter)
        if name_match is None or name_match.group(1) != name:
            got = None if name_match is None else name_match.group(1)
            out.append(f"skills/{name}/SKILL.md frontmatter name MUST be {name!r}; got {got!r}")
        desc_match = _FRONTMATTER_DESCRIPTION_RE.search(frontmatter)
        if desc_match is None or not desc_match.group(1).strip():
            out.append(f"skills/{name}/SKILL.md frontmatter description MUST be non-empty")
        if "allowed-tools" in frontmatter:
            out.append(
                f"skills/{name}/SKILL.md frontmatter MUST NOT carry an 'allowed-tools' key "
                "(Codex skills have no allowed-tools surface)"
            )
    return out


def _binding_body_violations(*, skill_md: Path) -> list[str]:
    """Validate Codex-binding body markers (resolution snippet + bans)."""
    out: list[str] = []
    text = skill_md.read_text(encoding="utf-8")
    frontmatter = _frontmatter_block(text=text)
    body = text
    if frontmatter is not None:
        # Drop the frontmatter block (the body is what follows the closing `---`).
        closing = text.find("\n---", text.find("---") + 3)
        if closing != -1:
            body = text[closing + len("\n---") :]
    where = skill_md.relative_to(_REPO_ROOT)
    if _CODEX_RESOLUTION_SNIPPET not in body:
        out.append(
            f"{where}: body MUST carry the Codex core-resolution invocation "
            f"{_CODEX_RESOLUTION_SNIPPET!r}"
        )
    if "/livespec:" in body:
        out.append(
            f"{where}: body MUST NOT use the '/livespec:' slash-command form "
            "(Codex invocation is NAME-based: 'livespec:<op>')"
        )
    if "installed_plugins.json" in body:
        out.append(
            f"{where}: body MUST NOT reference 'installed_plugins.json' "
            "(that is the Claude resolution artifact)"
        )
    if "Claude Code Driver" in body:
        out.append(f"{where}: body MUST NOT contain the phrase 'Claude Code Driver'")
    if "livespec-driver-claude" in body:
        out.append(f"{where}: body MUST NOT reference the sibling repo 'livespec-driver-claude'")
    return out


def _fenced_invocation_violations(*, skill_md: Path) -> list[str]:
    out: list[str] = []
    in_fence = False
    for line_no, raw in enumerate(skill_md.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence or _WRAPPER_INVOCATION_RE.search(stripped) is None:
            continue
        where = f"{skill_md.relative_to(_REPO_ROOT)}:{line_no}"
        if "uv run" in stripped:
            out.append(f"{where}: fenced wrapper invocation uses 'uv run'")
        if ".claude-plugin/scripts" in stripped:
            out.append(f"{where}: fenced wrapper invocation uses a literal .claude-plugin path")
        if _DRIVER_ROOT_TOKEN in stripped:
            out.append(
                f"{where}: fenced wrapper invocation uses the Driver's own plugin-root "
                "placeholder (resolves to the Driver root, which has no scripts/)"
            )
        if "$LIVESPEC_CORE_ROOT" not in stripped:
            out.append(f"{where}: fenced wrapper invocation MUST use $LIVESPEC_CORE_ROOT")
    return out


def _hook_bundle_violations() -> list[str]:
    out: list[str] = []
    if not _GUARD_SCRIPT.is_file():
        out.append("missing livespec/hooks/livespec_footgun_guard.py")
    try:
        hooks = json.loads(_HOOKS_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        out.append(f"livespec/hooks/hooks.json unreadable/invalid: {exc}")
        return out
    if "description" in hooks:
        out.append(
            "hooks.json MUST NOT carry a top-level 'description' key "
            "(Codex's hooks parser rejects it)"
        )
    pre_tool_use = hooks.get("hooks", {}).get("PreToolUse", [])
    bash_entries = [e for e in pre_tool_use if e.get("matcher") == "Bash"]
    if not bash_entries:
        out.append("hooks.json MUST register a PreToolUse entry with matcher 'Bash'")
        return out
    guard_referenced = any(
        "livespec_footgun_guard.py" in inner.get("command", "")
        for entry in bash_entries
        for inner in entry.get("hooks", [])
    )
    if not guard_referenced:
        out.append("hooks.json PreToolUse/Bash entry MUST reference 'livespec_footgun_guard.py'")
    return out


def main() -> int:
    violations, marketplace_description = _marketplace_violations()
    violations.extend(_manifest_violations(marketplace_description=marketplace_description))
    violations.extend(_skill_set_violations())
    for skill_md in sorted(_SKILLS_DIR.glob("*/SKILL.md")):
        violations.extend(_binding_body_violations(skill_md=skill_md))
        violations.extend(_fenced_invocation_violations(skill_md=skill_md))
    violations.extend(_hook_bundle_violations())
    for violation in violations:
        sys.stderr.write(f"check_plugin_structure: {violation}\n")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
