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
    """One publishing workspace member: its name, its directory, and what it ships.

    **`modules` is a tuple, and was a single `module: str | None` until 2026-09-05.** It was
    derived as `name.replace("-", "_")`, which held while every distribution shipped exactly one
    top-level package named after itself. `weft-rag` ships fourteen and is named after none of
    them, so that derivation named `weft_rag` — a module that does not exist — and the isolated
    install check it feeds would have imported nothing while reporting success. Read off the
    filesystem instead: every directory under the member's own `src/` with an `__init__.py`.
    Empty for a distribution that ships no code, which is a real state and stays distinguishable
    from "the read failed" by the raise in `publishing_members`.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    directory: Path
    modules: tuple[str, ...]


class PublishSetUnreadableError(Exception):
    """A side of the read came back empty, which is not the same as there being nothing to read."""


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _all_members(repo_root: Path, *, publishing_only: bool) -> tuple[Member, ...]:
    """Every workspace member that publishes, sorted by name.

    Raises `PublishSetUnreadableError` if the member globs match no directory containing a
    `pyproject.toml`, or if `[tool.uv.workspace] members` itself is empty — an empty answer is
    "I did not find it", never "there is none" (`docs/internal/lessons.md` L5.9).
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
            if publishing_only and opt_out is False:
                continue

            name = cast("str", config["project"]["name"])
            src = candidate / "src"
            modules = (
                tuple(
                    sorted(path.name for path in src.iterdir() if (path / "__init__.py").is_file())
                )
                if src.is_dir()
                else ()
            )
            found.append(Member(name=name, directory=candidate, modules=modules))

    if seen_manifests == 0:
        raise PublishSetUnreadableError(
            f"none of {patterns} matched a directory with a pyproject.toml under {repo_root}. "
            f"The globs are wrong, not the workspace."
        )

    return tuple(sorted(found, key=lambda member: member.name))


def publishing_members(repo_root: Path = REPO_ROOT) -> tuple[Member, ...]:
    """Every workspace member that publishes, sorted by name — the release set's own subject.

    A member opts out with `[tool.weft] publish = false`. Since G19 (2026-09-09) that is six
    add-ons as well as `testing/weft-canary`: Weft publishes under two names, and the add-ons'
    code ships inside the `weft-rag` wheel. For a property of the *code* rather than of the index,
    use `members_shipping_source` — see its own docstring for why the distinction started to
    matter.
    """
    return _all_members(repo_root, publishing_only=True)


def members_shipping_source(repo_root: Path = REPO_ROOT) -> tuple[Member, ...]:
    """Every workspace member that ships code, whether or not it publishes, sorted by name.

    **Why this exists beside `publishing_members`, since G19 on 2026-09-09.** That function
    answers "what reaches an index", which is the right subject for the release set and the wrong
    one for any property of the *code*. G19 settled that Weft publishes under two names and that a
    pack's code ships inside the `weft-rag` wheel, so six distributions that used to publish now
    carry `[tool.weft] publish = false` — and a check walking the publishing set stopped being able
    to see them. `weft-openai` reaching the network is a fact about its source, not about which
    wheel carries it, and it became *more* important to see once the code ships to everybody rather
    than only to whoever asked for it.

    So: same walk, same refusal on an empty read, and the publish flag ignored.
    """
    return _all_members(repo_root, publishing_only=False)


__all__ = ["Member", "PublishSetUnreadableError", "members_shipping_source", "publishing_members"]
