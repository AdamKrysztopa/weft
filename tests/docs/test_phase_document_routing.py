"""A retired phase-build document stops being routed to — repair for a reviewer finding.

`docs/README.md`'s own Documents table called `06-phase-0-build.md` "Reference — retire when
Phase 0 exits" *after* Phase 0 had already exited (`7dae68b`, 2026-08-16) — its own retirement
condition had fired and nothing acted on it. Three concrete places kept sending a reader or an
operator to Phase 0's build order as if it were still the live guide: `phase-step`'s own
`SKILL.md` — the skill `CLAUDE.md` names as "start here when writing code" — `CLAUDE.md` itself,
and `weft_kernel.registry.DuplicateRegistrationError`'s raised message, which pointed an operator
at Phase 0's build order for a duplicate-name trap G2 closed 2026-08-16, when
`docs/02-extension-model.md` §3 alone now states it.

**This file does not attempt the general sweep** — "does anything anywhere cite a retired phase
document" — because most such citations are exactly what `CLAUDE.md` asks a docstring to do: cite
the section that explains why code is shaped the way it is, which stays true and useful long after
the phase that wrote it closes. A heuristic that cannot tell that kind of citation apart from an
instruction that still tells a reader to go *start* there would flag the correct ones as often as
the wrong ones. This file instead pins the four concrete instances the finding named, so none of
them can quietly revert.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from weft_kernel.registry import DuplicateRegistrationError, Registry

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]


def _text(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _bullet(markdown: str, *, heading: str) -> str:
    """The paragraph of a `- **\\`heading\\`** — ...` bullet, up to the next top-level bullet.

    `CLAUDE.md`'s skills list wraps each entry across more than one line, so a single-line
    `grep`-shaped search would miss the wrapped continuation — this walks lines instead,
    starting at the line that opens the named bullet and stopping at the next `- **` or a
    blank line, whichever comes first.
    """
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"- **`{heading}`**"))
    end = start + 1
    while end < len(lines) and lines[end].strip() and not lines[end].startswith("- **"):
        end += 1
    return "\n".join(lines[start:end])


class _Stub:
    """A stand-in contract — this file only needs `Registry.add` to collide, not what it is for."""


def test_readme_documents_table_no_longer_calls_06_a_live_reference() -> None:
    # Arrange
    readme = _text("docs/README.md")

    # Act — the Documents table row is the one that starts the line with the file's own name.
    row = next(line for line in readme.splitlines() if line.startswith("| `06-phase-0-build.md`"))

    # Assert — Phase 0 exited 2026-08-16; the row's own stated retirement condition fired,
    # so it must no longer read as an open condition still to be met.
    assert "Reference — retire when Phase 0 exits" not in row
    assert re.search(r"\bretired\b", row, re.IGNORECASE)


def test_phase_step_skill_starts_a_reader_at_the_ledger_not_at_06() -> None:
    # Arrange — the frontmatter `description` is what a reader sees before opening the file,
    # and is exactly what routed an agent starting Phase 2 work to Phase 0's build order.
    skill = _text(".claude/skills/phase-step/SKILL.md")
    header = skill.split("---", 2)[1]

    # Assert
    assert "docs/06-phase-0-build.md" not in header
    assert "docs/build-ledger.md" in header


def test_phase_step_skill_no_longer_calls_g2_open() -> None:
    # Arrange — G2 settled 2026-08-16; the skill used to tell a reader to "check the traps"
    # for "G2, which is open" no matter which phase they were actually working.
    skill = _text(".claude/skills/phase-step/SKILL.md")

    # Assert
    assert "which is open" not in skill
    assert "G2, G7, G8 and G9 are open" not in skill


def test_claude_md_phase_step_bullet_names_the_ledger_and_marks_06_retired() -> None:
    # Arrange
    claude_md = _text("CLAUDE.md")

    # Act
    bullet = _bullet(claude_md, heading="phase-step")

    # Assert — the bullet is the "start here" pointer `CLAUDE.md` gives an agent; it must
    # name the phase-agnostic ledger, not send a reader to Phase 0's build order as though
    # it were still current. Mentioning `06` at all is fine as long as it is marked retired
    # in the same breath, which is what distinguishes this from the original defect.
    assert "docs/build-ledger.md" in bullet
    assert re.search(r"\bretired\b", bullet)


def test_duplicate_registration_error_points_an_operator_at_02_not_06() -> None:
    # Arrange
    registry = Registry()
    registry.add(_Stub, "shared", lambda: "first", distribution="weft-a")

    # Act
    with pytest.raises(DuplicateRegistrationError) as excinfo:
        registry.add(_Stub, "shared", lambda: "second", distribution="weft-b")

    # Assert — G2 closed 2026-08-16; the duplicate-name trap it fixed now lives only in
    # `02` §3, never in Phase 0's retired build order.
    message = str(excinfo.value)
    assert "06-phase-0-build.md" not in message
    assert "02-extension-model.md" in message
