"""The one reader of "which distributions are published, and what module does each ship".

`docs/09-release.md` §5.2 requires fitness function 1 to hold for **every** published
distribution, not only the kernel. `scripts/check_isolated_installs.py` is the check that walks
this set; `tests/architecture/test_isolated_installs.py` is the pytest that can see the parts of
that check a subprocess-driven script cannot: that the enumeration itself is right.

The published set is exactly the workspace-side half of fitness function 10(a)
(`tests/architecture/test_ff10_ship_set_integrity.py`'s `workspace_distributions`) — every
workspace member whose own `pyproject.toml` does not carry the `[tool.weft] publish = false`
opt-out marker. That function is not imported from here: it returns a `frozenset[str]` of names
alone, and this reader also needs each member's directory and whether it ships code, so the walk
is done again rather than partially reused and then extended.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict

#: `scripts/` is one level below the repository root.
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

#: `[tool.weft] publish = false` in a distribution's own `pyproject.toml` — the opt-out marker
#: task 6.2 established. `testing/weft-canary` carries it.
_OPT_OUT_TABLE: Final[str] = "weft"
_OPT_OUT_KEY: Final[str] = "publish"


class Member(BaseModel):
    """One publishing workspace member: its name, its directory, and what it ships."""

    model_config = ConfigDict(frozen=True)

    name: str
    directory: Path
    module: str | None


class PublishSetUnreadableError(Exception):
    """A side of the read came back empty, which is not the same as there being nothing to read."""


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def publishing_members(repo_root: Path = REPO_ROOT) -> tuple[Member, ...]:
    """Every workspace member that publishes, sorted by name.

    Raises `PublishSetUnreadableError` if the member globs match no directory containing a
    `pyproject.toml`, or if `[tool.uv.workspace] members` itself is empty — an empty answer is
    "I did not find it", never "there is none" (`docs/lessons.md` L5.9).
    """
    workspace_manifest = repo_root / "pyproject.toml"
    workspace_config = _load_toml(workspace_manifest)

    members_field = (
        workspace_config.get("tool", {}).get("uv", {}).get("workspace", {}).get("members")
    )
    patterns = cast("list[str]", members_field) if isinstance(members_field, list) else []

    if not patterns:
        raise PublishSetUnreadableError(
            f"{workspace_manifest} declares no [tool.uv.workspace] members. That list is what "
            f"this reader expands; an empty one means the read is wrong, not that the workspace "
            f"is empty."
        )

    found: list[Member] = []
    seen_manifests = 0

    for pattern in patterns:
        for candidate in sorted(repo_root.glob(pattern)):
            manifest = candidate / "pyproject.toml"
            if not manifest.is_file():
                continue
            seen_manifests += 1

            config = _load_toml(manifest)
            opt_out = config.get("tool", {}).get(_OPT_OUT_TABLE, {}).get(_OPT_OUT_KEY, True)
            if opt_out is False:
                continue

            name = cast("str", config["project"]["name"])
            module = name.replace("-", "_") if (candidate / "src").is_dir() else None
            found.append(Member(name=name, directory=candidate, module=module))

    if seen_manifests == 0:
        raise PublishSetUnreadableError(
            f"none of {patterns} matched a directory with a pyproject.toml under {repo_root}. "
            f"The globs are wrong, not the workspace."
        )

    return tuple(sorted(found, key=lambda member: member.name))
