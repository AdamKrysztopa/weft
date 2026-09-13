"""A settled gate cited as open — `docs/internal/lessons.md` **`L19.2`**.

**A decision recorded with its reasons is a claim that expires the way a count does.** When a gate
closes, nothing walks the sentences that cited it: the gate's own row moves to *Settled*, the
document that owns the content is edited, and every *other* file that deferred a decision *because*
that gate was open keeps saying so. Those sentences do not look stale — they look like careful
practice, which is exactly what they were on the day they were written.

**Measured at Phase 21a's close, and it is why this file exists rather than a sentence in a
protocol.** Four tracked assertions of an open gate, none of them true, the oldest standing
**twenty-three days** and eight phases:

- `tests/integration/test_store_conformance.py` — *"what its own version means while **G9 is
  Open**"*. G9 settled 2026-08-21.
- `docs/02-extension-model.md` — *"**G9 is Open** and owns what a version number means"*. G9
  settled 2026-08-21.
- `docs/09-release.md` §0 — *"**G9 is open, and this document depends on it in five places**"*,
  and *"**G2, G7 and G8 are open**"*. G2 settled 2026-08-16, G8 2026-08-18, G7 and G9 2026-08-21.
- `docs/06-phase-0-build.md` — *"Phase 0 has to do things that G2 owns and **G2 is open**"*. G2
  settled 2026-08-16.

**What it cost, which is the part that makes this worth machinery.** The conformance-kit refusal in
`tests/integration/test_store_conformance.py:34 "A third reason stood here and expired"` gave three
reasons, and the third was G9's openness. `12-roadmap.md`
then inherited that refusal **by reference** — *"proposed at a Phase 2 task and refused"* — so an
expired premise became load-bearing in a second document, and Phase 26b was scheduled to inherit it
a third time without anyone re-reading the original. This is `L18.7` one level up: there a roadmap
row outlived its phase; here a **refusal** outlived its premise.

**What this checks, and what it deliberately does not.** Only the assertion *that a gate is open* —
a present-tense claim with a truth value the decision log can settle. It says nothing about whether
a *decision* made while the gate was open is still right; that is judgement and belongs to a
reading. Narrow on purpose: a check over every `G<n>` mention would walk 534 of them across 196
files, almost all correct citations of a settled gate, and would need a waiver list longer than the
population it protects.

**History is not a stale claim.** *"asserted the six add-ons until G19 (2026-09-09)"* and
*"blocker 2 cleared when G2 settled"* are past-tense records and must stay readable, so the
patterns below require a present-tense copula, or a subordinating conjunction with a
settlement verb after it.
`docs/_external-reading/` is excluded: it is a record of somebody else's project, which `CLAUDE.md`
keeps out of Weft's own reasoning entirely.

**`.claude/` is walked, and it was not in the first version of this list.** Twenty-three files
there are tracked — the hooks, the agent file and the six skills all travel with the repository —
and the roots above stopped before them, which is `L5.14`'s *a list is where to start looking, not
a census* biting the check written to enforce a neighbouring rule. Widened in the same drain that
adopted it, on finding `weft-qualities`' own *Not an architecture gate* clause naming G2, G7, G8
and G9 as open decisions a reader should stop at. All four had settled by 2026-08-21.

Skips on a clean checkout: the decision log lives in `docs/internal/README.md`, which is untracked
by design (`tests.conftest.UNTRACKED_BY_DESIGN`).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

import pytest

from tests.architecture.conftest import tracked_files
from tests.conftest import untracked_reason

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_LOG: Final[Path] = _REPO_ROOT / "docs" / "internal" / "README.md"

_MISSING: Final[str | None] = untracked_reason("docs/internal/README.md")
_requires_log = pytest.mark.skipif(_MISSING is not None, reason=_MISSING or "")

#: The roots walked. `docs/internal/` is absent deliberately — it is untracked, and its ledger
#: records what was true at each task, which is history and must stay verbatim.
_ROOTS: Final[tuple[str, ...]] = (
    ".claude",
    "docs",
    "manual",
    "packages",
    "tests",
    "testing",
    "eval",
    "scripts",
)

#: A directory of another project's material. `CLAUDE.md`: read to understand, then closed.
_EXCLUDED: Final[str] = "_external-reading"

#: `- [x] **G9** …` in the decision checklist. A ticked box is a settled gate.
_SETTLED: Final[re.Pattern[str]] = re.compile(r"^- \[x\] \*\*G(\d{1,2})\*\*", re.MULTILINE)

#: *"G9 is Open"*, *"G2, G7 and G8 are open"*, *"G12 remains unsettled"*. The window is bounded and
#: stops at a sentence end, so a paragraph mentioning a gate and, later, something else being open
#: is not a hit.
_CLAIMS_OPEN: Final[re.Pattern[str]] = re.compile(
    r"\bG\d{1,2}\b[^.\n]{0,60}?\b(?:is|are|remains|stays)\s+(?:still\s+)?(?:an?\s+)?"
    r"(?:open|unsettled)\b",
    re.IGNORECASE,
)

#: *"until G12 closes"*, *"when G21 settles"* — a decision waiting on a gate that stopped
#: waiting.
_AWAITS: Final[re.Pattern[str]] = re.compile(
    r"\b(?:until|when|once|while)\s+\**`?G\d{1,2}`?\**\s+(?:settles|closes|is\s+settled)\b",
    re.IGNORECASE,
)

_GATE: Final[re.Pattern[str]] = re.compile(r"\bG(\d{1,2})\b")

#: A double-quoted span, which may wrap across lines. **Quoted text is a record, not an
#: assertion** — this tree corrects a stale sentence by quoting what it used to say, so without
#: this the check fires on its own repairs and on its own docstring. Bounded, so an unbalanced
#: quote cannot swallow the rest of a file.
_QUOTED: Final[re.Pattern[str]] = re.compile(
    r'["\u201c][^"\u201c\u201d]{0,400}["\u201d]', re.DOTALL
)


def _settled_gates() -> frozenset[str]:
    return frozenset(_SETTLED.findall(_LOG.read_text(encoding="utf-8")))


def _files() -> list[Path]:
    """Every **tracked** file under the roots, from `git ls-files`.

    Tracked, not globbed, and the difference is not pedantry: the first version of this walk used
    `rglob` and swept `.claude/worktrees/` — leftover worktree checkouts of Phase 2 holding the
    very sentences this check was written from, at the version where they were still true. It
    reported nine violations in files no diff will ever touch. `git ls-files` is the population
    every architecture check in this tree reads for the same reason (`L11.34`), and it is what
    the word *tracked* in this file's own assertions has been claiming all along.

    **`tests.architecture.conftest.tracked_files` rather than a fourth `subprocess.run`.** That
    helper's own docstring records that it was written twice and that *"a third caller was about
    to restate it"*; this is that caller, arriving from a different directory. One copy is also
    one `S603` suppression and one `shutil.which`, which is the argument it already makes.
    """
    suffixes = {".md", ".py", ".yaml", ".toml"}
    return [
        _REPO_ROOT / name
        for name in tracked_files()
        if Path(name).parts[:1]
        and Path(name).parts[0] in _ROOTS
        and Path(name).suffix in suffixes
        and _EXCLUDED not in Path(name).parts
        and "internal" not in Path(name).parts
    ]


def claims_about_open_gates(text: str) -> list[tuple[str, str]]:
    """`(gate id, the sentence fragment claiming it)` for every gate this text says is open.

    Public because `test_the_check_can_actually_fail` below drives it on a planted string, and a
    check whose detector is reachable only through the filesystem cannot be shown to fail without
    writing into the tree.
    """
    # A docstring delimiter is three quote characters, not a quotation, and leaving them in
    # makes every later pairing in the file off by one. Blanked first, and offsets preserved so
    # the reported fragment still reads correctly.
    plain = text.replace('"""', "   ")
    unquoted = _QUOTED.sub(lambda match: " " * len(match.group(0)), plain)
    found: list[tuple[str, str]] = []
    for pattern in (_CLAIMS_OPEN, _AWAITS):
        for match in pattern.finditer(unquoted):
            fragment = match.group(0)
            found.extend((gate, fragment) for gate in _GATE.findall(fragment))
    return found


@_requires_log
def test_no_tracked_file_says_a_settled_gate_is_open() -> None:
    # Arrange
    settled = _settled_gates()
    assert len(settled) >= 12, (
        f"only {len(settled)} settled gates were parsed out of the decision checklist in "
        f"{_LOG} — the checklist's shape moved and this check is comparing against almost "
        f"nothing, which would pass forever."
    )

    # Act
    stale: list[str] = []
    for path in _files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "G" not in text:
            continue
        for gate, fragment in claims_about_open_gates(text):
            if gate in settled:
                relative = path.relative_to(_REPO_ROOT)
                stale.append(f"{relative}: G{gate} is settled — {fragment.strip()!r}")

    # Assert
    assert not stale, (
        "these tracked files assert that a gate is open, and the decision log says it is "
        "settled:\n  " + "\n  ".join(sorted(stale)) + "\nA decision deferred *because* a gate was "
        "open is a claim that expired when the gate closed, and nothing walks such sentences at "
        "settlement — so the reason outlives its premise and gets inherited by reference."
    )


def test_the_check_can_actually_fail() -> None:
    """A planted claim, in each of the two shapes, because the assertion above passes on a clean
    tree and would pass equally if either pattern had stopped matching anything."""
    # Arrange / Act
    copula = claims_about_open_gates("what its own version means while **G9 is Open**.")
    awaiting = claims_about_open_gates("the quickstart's second section when G21 settles.")
    several = claims_about_open_gates(
        "**G2, G7 and G8 are open** and this document assumes nothing"
    )

    # Assert
    assert [gate for gate, _ in copula] == ["9"]
    assert [gate for gate, _ in awaiting] == ["21"]
    assert sorted(gate for gate, _ in several) == ["2", "7", "8"]


def test_a_past_tense_record_of_a_gate_is_not_a_claim_that_it_is_open() -> None:
    """The half that decides whether this check is usable. This tree keeps *why* beside the code,
    so it is dense with sentences about gates that have since closed — and every one of them must
    stay readable. A check that cannot tell a record from an assertion would waive its way to
    uselessness within a phase."""
    # Arrange
    records = (
        "**This test asserted the six add-ons until G19 (2026-09-09)**, on the reading that",
        "blocker 2 cleared when G2 settled 2026-08-16",
        "for a second caller) until G17 added a third consumer, `weft_clean`",
        "G9 was open when this paragraph was written, and is not now.",
        "**Until G12, one rule holds without exception:**",
        'It read *"what its own version means while G9 is Open"* — and G9 settled 2026-08-21.',
        'This read *"G2, G7 and G8 are open"* until 2026-09-13.',
    )

    # Act / Assert
    for record in records:
        assert claims_about_open_gates(record) == [], record


@_requires_log
def test_the_walk_reaches_the_files_it_is_supposed_to() -> None:
    """Non-vacuity for the file walk: an empty population makes the real assertion pass over
    nothing, which is `L11.5`'s shape and the reason every sweep in this tree carries a floor."""
    # Arrange / Act
    files = _files()
    suffixes = {path.suffix for path in files}

    # Assert
    assert len(files) >= 200, f"only {len(files)} files were walked — the roots moved"
    assert {".md", ".py"} <= suffixes, f"the walk found only {sorted(suffixes)}"
    assert not any("internal" in path.parts for path in files), "the untracked tree was walked"
