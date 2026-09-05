"""`docs/08-manuals.md` §3 — the operations guide's tables are included, not retyped.

"The compose snippet is the actual shipped file; the exit-code and status tables are generated
from the same enums the CLI and doctor read... [what fails when it drifts:] the guide showing a
container topology or a status name that no longer exists." This is that check, run against
`manual/operations-guide.md` — task **0.13**: "an operator can run the one container, read a
`doctor` status and act on an exit code without opening `docs/`."

Three things are checked, each against the real source rather than against each other, in the
same identity-diff shape `tests/docs/test_pack_guide_samples.py` already uses for the pack author
guide: the guide can only ever show the artifact it claims to demonstrate, never a hand-retyped
copy that could quietly diverge.

1. **The `compose.yaml` block** is the repository's real file, byte for byte — the same
   `path=`-tag identity diff `test_pack_guide_samples.py` uses, repeated here rather than shared
   for the reason that module's own docstring gives: this should read as one self-contained
   scenario.
2. **The exit-code table** names exactly the members `weft_cli.exit_codes.ExitCode` declares, at
   the same integer values — not a superset, not a subset.
3. **The doctor status table** names exactly the members `weft_kernel.discovery.PackStatus`
   declares — the `ambient` flag is not a `PackStatus` member (it is a bool field on
   `PackReport`, not a status), so it is checked separately, as prose mentioning it, rather than
   folded into the status set-equality check where it would never belong.

Each check has a floor — "at least one thing to compare" — and a self-test proving the comparison
can actually fail, per `08` §3's own requirement of every check in this file: a check with no floor
degenerates to comparing a set against itself, passes vacuously on an empty guide, and never
catches the drift it exists to catch.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from weft_cli.exit_codes import ExitCode
from weft_kernel.discovery import PackStatus

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
GUIDE: Final[Path] = REPO_ROOT / "manual" / "operations-guide.md"

_FENCE = re.compile(
    r"^```(?P<lang>\S+)(?:\s+path=(?P<path>\S+))?\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL,
)
_TABLE_ROW = re.compile(r"^\|\s*`([^`|]+)`\s*\|\s*`([^`|]+)`\s*\|", re.MULTILINE)
_FIRST_CELL = re.compile(r"^\|\s*`([^`|]+)`\s*\|", re.MULTILINE)


def _guide_text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _fenced_blocks(markdown: str) -> list[tuple[str, str | None, str]]:
    """Every fenced block in `markdown`, as `(language, tagged_path_or_None, body)` triples."""
    return [
        (match.group("lang"), match.group("path"), match.group("body"))
        for match in _FENCE.finditer(markdown)
    ]


def _section(markdown: str, *, heading: str, next_heading: str) -> str:
    """The text strictly between two `##` headings — the scope one table's regex scans over,
    so a row shape reused for a different table under a different heading is never conflated
    with this one."""
    start = markdown.index(heading) + len(heading)
    end = markdown.index(next_heading, start)
    return markdown[start:end]


# --- 1. compose.yaml is the real file --------------------------------------------------------


def test_compose_block_is_tagged_against_the_real_file() -> None:
    # Floor — a guide with no tagged compose block passes zero comparisons.
    blocks = _fenced_blocks(_guide_text())
    tagged = [path for _, path, _ in blocks if path == "compose.yaml"]
    assert tagged, "manual/operations-guide.md has no `path=compose.yaml`-tagged block to check"


def test_compose_block_matches_the_shipped_file() -> None:
    # Arrange
    blocks = _fenced_blocks(_guide_text())
    matches = [body for _, path, body in blocks if path == "compose.yaml"]
    assert len(matches) == 1, f"expected exactly one path=compose.yaml block, found {len(matches)}"

    # Act
    actual = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")
    expected = matches[0].rstrip("\n") + "\n"

    # Assert — the two-lists bug, aimed at a container topology instead of a file format.
    assert actual == expected, (
        "manual/operations-guide.md's compose.yaml block has drifted from the shipped file. "
        "Paste the real compose.yaml back in — this block is included, not retyped."
    )


def test_a_retyped_compose_block_would_fail(tmp_path: Path) -> None:
    # Arrange — prove the comparison can actually fail.
    planted = tmp_path / "planted-guide.md"
    planted.write_text("```yaml path=compose.yaml\nservices: {}\n```\n", encoding="utf-8")

    # Act
    blocks = _fenced_blocks(planted.read_text(encoding="utf-8"))
    body = next(body for _, path, body in blocks if path == "compose.yaml")
    real = (REPO_ROOT / "compose.yaml").read_text(encoding="utf-8")

    # Assert
    assert body.rstrip("\n") + "\n" != real


# --- 2. the exit-code table matches ExitCode --------------------------------------------------

_EXIT_CODE_HEADING = "## Exit codes"
_EXIT_CODE_NEXT_HEADING = "## "


def _exit_code_rows(markdown: str) -> dict[int, str]:
    section = _section(markdown, heading=_EXIT_CODE_HEADING, next_heading=_EXIT_CODE_NEXT_HEADING)
    return {int(code): name for code, name in _TABLE_ROW.findall(section)}


def test_at_least_one_exit_code_row_is_present() -> None:
    # Floor
    rows = _exit_code_rows(_guide_text())
    assert rows, "manual/operations-guide.md's exit-code table has no `code` | `NAME` rows"


def test_exit_code_table_matches_the_enum_exactly() -> None:
    # Arrange
    rows = _exit_code_rows(_guide_text())
    expected = {int(member.value): member.name for member in ExitCode}

    # Assert — set equality, the same shape fitness functions 2 and 4(b) use, aimed at a
    # documentation table instead of a registry.
    assert rows == expected, (
        f"manual/operations-guide.md's exit-code table ({rows}) has drifted from "
        f"weft_cli.exit_codes.ExitCode ({expected})."
    )


def test_a_stale_exit_code_row_would_fail() -> None:
    # Arrange — a table that dropped a real code and invented one that does not exist.
    planted = {0: "SUCCESS", 5: "MADE_UP"}
    expected = {int(member.value): member.name for member in ExitCode}

    # Assert
    assert planted != expected


# --- 3. the doctor status table matches PackStatus ---------------------------------------------

_DOCTOR_HEADING = "## Doctor"
_DOCTOR_NEXT_HEADING = "## The one thing"


def _doctor_status_cells(markdown: str) -> set[str]:
    section = _section(markdown, heading=_DOCTOR_HEADING, next_heading=_DOCTOR_NEXT_HEADING)
    return {cell for cell in _FIRST_CELL.findall(section)}


def test_at_least_one_doctor_status_row_is_present() -> None:
    # Floor
    cells = _doctor_status_cells(_guide_text())
    assert cells, "manual/operations-guide.md's doctor status table has no `status` rows"


def test_doctor_status_table_matches_the_enum_exactly() -> None:
    # Arrange
    cells = _doctor_status_cells(_guide_text())
    expected = {member.value for member in PackStatus}

    # Assert
    assert cells == expected, (
        f"manual/operations-guide.md's doctor status table ({sorted(cells)}) has drifted from "
        f"weft_kernel.discovery.PackStatus ({sorted(expected)})."
    )


def test_ambient_is_documented_as_a_flag_not_a_status() -> None:
    # `ambient` is a `bool` field on `PackReport`, not a `PackStatus` member — `02` §2 shows it
    # as "`ambient` *(flag on `active`)*" in its own vocabulary table rather than a seventh
    # status, and the guide must say the same rather than inventing a sixth status value.
    assert "ambient" not in {member.value for member in PackStatus}
    section = _section(_guide_text(), heading=_DOCTOR_HEADING, next_heading=_DOCTOR_NEXT_HEADING)
    assert "ambient" in section, (
        "manual/operations-guide.md's doctor section never mentions the `ambient` flag"
    )


def test_a_stale_doctor_status_row_would_fail() -> None:
    # Arrange — a table naming a status that no longer exists.
    planted = {"active", "retired-status"}
    expected = {member.value for member in PackStatus}

    # Assert
    assert planted != expected
