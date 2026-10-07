"""Regenerates the README's release sentence from both distributions' versions — repair **R20.7**.

The README named `weft-rag 2.7.0` / `weft-kernel 0.2.1` while the tree was `3.1.0` / `0.3.0`: a
version written by hand is right on the day it is written. The sentence between `BEGIN` and `END`
is rendered from `packages/*/pyproject.toml`, and `tests/docs/test_readme_release_line.py` fails
when the checked-in copy differs or a README names either distribution's version anywhere else.
Run after a version bump and commit the result:

    uv run python scripts/generate_readme_release.py
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
README: Final[Path] = REPO_ROOT / "README.md"
READMES: Final[tuple[Path, ...]] = (
    README,
    REPO_ROOT / "packages" / "weft-kernel" / "README.md",
    REPO_ROOT / "packages" / "weft-rag" / "README.md",
)
DISTRIBUTIONS: Final[tuple[str, ...]] = ("weft-rag", "weft-kernel")
BEGIN: Final[str] = "<!-- weft-release:begin -->"
END: Final[str] = "<!-- weft-release:end -->"
_NAMED_VERSION: Final[re.Pattern[str]] = re.compile(
    r"\b(?:weft-rag|weft-kernel)`?\s+`?v?\d+\.\d+\.\d+"
)


def workspace_versions(root: Path = REPO_ROOT) -> dict[str, str]:
    """Each published distribution's `version`, read from its own `pyproject.toml`."""
    versions: dict[str, str] = {}
    for name in DISTRIBUTIONS:
        with (root / "packages" / name / "pyproject.toml").open("rb") as handle:
            versions[name] = tomllib.load(handle)["project"]["version"]
    return versions


def render(versions: dict[str, str]) -> str:
    """The sentence the markers wrap."""
    rag, kernel = versions["weft-rag"], versions["weft-kernel"]
    return f"this README describes `weft-rag {rag}` / `weft-kernel {kernel}`"


def spliced(markdown: str, sentence: str) -> str:
    """`markdown` with the text between `BEGIN` and `END` replaced by `sentence`."""
    start = markdown.index(BEGIN) + len(BEGIN)
    end = markdown.index(END, start)
    return markdown[:start] + sentence + markdown[end:]


def versions_named_outside(markdown: str) -> list[str]:
    """Every `weft-rag X.Y.Z` / `weft-kernel X.Y.Z` in `markdown` outside the generated span."""
    if BEGIN in markdown:
        start = markdown.index(BEGIN)
        markdown = markdown[:start] + markdown[markdown.index(END, start) + len(END) :]
    return _NAMED_VERSION.findall(markdown)


def main() -> None:
    """Rewrite the README's release sentence in place."""
    sentence = render(workspace_versions())
    README.write_text(spliced(README.read_text(encoding="utf-8"), sentence), encoding="utf-8")
    print(f"wrote {README}: {sentence}")


if __name__ == "__main__":
    main()
