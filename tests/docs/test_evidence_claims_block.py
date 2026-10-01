"""Task **44.32** — `manual/evidence.md` §3's rung table is generated from the claims, not typed.

The block between the `claims:begin` and `claims:end` markers must equal what
`weft_eval.claims_render.render_claims_table` produces from `eval/claims/` today, with every claim
recomputed from its committed records. A claim edited, added or made stale changes the render, so
the page cannot quietly keep a status the records no longer give. Regenerate with
`weft eval claims render` and paste its `markdown` between the markers.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path, PurePosixPath
from typing import Final

import pytest

from weft_eval.claims import load_claims
from weft_eval.claims_check import check_claim
from weft_eval.claims_render import render_claims_table

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_PAGE: Final[Path] = _ROOT / "manual" / "evidence.md"
_BLOCK: Final[re.Pattern[str]] = re.compile(
    r"<!-- claims:begin -->\n(.*?)\n<!-- claims:end -->", re.DOTALL
)


def _shipped_rungs() -> list[str]:
    git = shutil.which("git")
    assert git is not None, "git is not on PATH, so nothing here can enumerate tracked files"
    listed = subprocess.run(  # noqa: S603 — literal argv, no shell; nothing interpolated
        [git, "ls-files", "packages/*/src/*/pipelines/*.yaml"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted({PurePosixPath(path).stem for path in listed})


def block_of(text: str) -> str | None:
    """The generated block of the page, or `None` when the markers are missing."""
    found = _BLOCK.search(text)
    return found.group(1) if found else None


def rendered() -> str:
    claims = load_claims(_ROOT / "eval" / "claims")
    entries = [(claim, check_claim(claim, root=_ROOT)) for claim in claims]
    return render_claims_table(entries, shipped_rungs=_shipped_rungs())


# Each of the claims bootstraps its interval from its records; 60 s does not cover them all
# (L28.88).
@pytest.mark.timeout(300)
def test_the_rung_table_equals_the_render_of_the_claims() -> None:
    # Act
    block = block_of(_PAGE.read_text(encoding="utf-8"))

    # Assert
    assert block is not None, "manual/evidence.md section 3 has no claims:begin/claims:end block"
    assert block == rendered(), "regenerate with `weft eval claims render`"


def test_the_block_check_can_actually_fail() -> None:
    # Arrange
    page = "<!-- claims:begin -->\n| rung | status | evidence |\n<!-- claims:end -->"

    # Act / Assert
    assert block_of(page) == "| rung | status | evidence |"
    assert block_of("no markers here") is None
