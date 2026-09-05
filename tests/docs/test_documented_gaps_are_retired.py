"""A documented gap is retired when the task that closes it ticks — ledger task **8.21**.

`docs/lessons-archive.md` `L7.5`. `manual/pack-author-guide.md` §9.3 carried a paragraph headed
"Honest gap, not a pattern to copy" for two weeks after ledger task **6.26** closed the gap and
added a fitness function to keep it closed — so the guide went on telling pack authors that this
tree's own examples taught the wrong thing while a check enforced the right one. It was found
because a later task happened to be editing the paragraph next to it.

**The generalisation is that a prose gap outlives its own repair by default.** Nothing in a
document changes when a ledger box ticks, and nobody re-reads the manuals looking for sentences
that stopped being true. The two facts are already written down in two files, so the check is an
agreement between them: a sentence that asserts an open gap *and* names the task that owns it must
not name a task that is ticked.

**Scope is decided by measurement, not by preference**, and each exclusion below is a population
this check would be wrong about rather than merely noisy:

- `docs/build-ledger.md` is excluded. Its per-task entries end with the recurring idiom
  *"left to later tasks, named rather than silently covered: ... (3.9); ... (3.10)"* — a dated
  record of what that task's exit state **was**, which is the ledger's whole append-only point. A
  standing-claim check applied to a historical record reports the record as a defect.
- `docs/lessons-archive.md` is excluded for the same reason one level out: it is what was learned
  on a date, and an entry saying a thing was open then is correct forever.
- `docs/README.md` is excluded because its decision log is one table whose rows run to hundreds of
  lines and carry dozens of task ids apiece; its Status block has its own checker in
  `scripts/next_task.py --check-live`, which is where a stale project position is caught.

**What this enforces is a writing discipline, not only a fact**, and that is the honest way to
read a hit. A sentence that carries an open gap *and* a ticked task id is ambiguous at the point
where it matters: a reader cannot tell whether the id owns the gap or merely supplies provenance
for the half that is built, and `L7.5`'s failure is exactly that ambiguity resolving the wrong way
some weeks later. So the remedy for a hit on a gap that is genuinely still open is to **split the
sentence** — provenance in one, the gap and who owns it in the next — which is what the repairs in
this task's own commit do. Measured: this check fired twice on prose written to satisfy it.

**The correction convention is honoured rather than fought.** This tree supersedes text in place
with a `>` blockquote beginning `Corrected` — 29 of them across six documents — and a paragraph
that says a thing is not yet true, immediately followed by a note saying it now is, has not
outlived its repair: the correction is right there. So a hit whose following lines carry that
blockquote is not a failure. This is `docs/lessons.md` L6.4 applied: the marker means what its live
instances say.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

#: Documents whose prose makes standing claims about the tree. See the module docstring for why
#: each excluded file is a population this check would be *wrong* about, not merely noisy on.
_EXCLUDED: Final[frozenset[str]] = frozenset(
    {"build-ledger.md", "lessons-archive.md", "lessons.md", "README.md"}
)

#: Gap phrasings, chosen from what a sweep of this tree actually found rather than from a lexicon.
#: Every one of these produced a true positive and no false positive; the rejected candidates are
#: recorded here because the next person to widen this set needs the measurement, not the guess —
#: `left to` is ~100% ledger idiom and ordinary English, `deferred` is always a *decided* deferral
#: with a stated reason, `filed rather than` appears only in the ledger, and a bare `gap` fires
#: 45 times for 4 real hits because the tree writes "closed the gap" and "### 3.1 The gap" too.
_GAP_PHRASES: Final[tuple[str, ...]] = (
    r"until (?:ledger )?task",
    r"owns the repair",
    r"\bunbuilt\b",
    r"does not exist yet",
    r"still (?:open|unowned|owed|unbuilt|declares|needs|not published)",
    r"\bno(?:thing)?\b[^.]{0,60}\byet\b",
    r"do(?:es)? not yet (?:exist|run|ship|carry)",
)

_GAP: Final[re.Pattern[str]] = re.compile("|".join(_GAP_PHRASES), re.IGNORECASE)

#: A ledger id that the prose itself presents as one — preceded by `task`, by `ledger`, or opened
#: as an inline code span. Without that anchor the same `N.M` shape matches section numbers
#: (`### 3.1 The gap`), version strings and lesson ids, which is the largest false-positive class
#: a bare id regex has in this tree.
_ANCHORED_ID: Final[re.Pattern[str]] = re.compile(
    r"(?:task|ledger|build-ledger\.md`?)\s+\**`?(\d{1,2}\.\d{1,2}[a-z]?)`?\**"
    r"|`(\d{1,2}\.\d{1,2}[a-z]?)`"
)

#: One task line at column 0. The `[a-z]?` suffix is mandatory: 5.1a-5.1d, 5.2a-5.2g and 5.3a all
#: exist, and without it `5.2g` collapses onto `5.2` and the file reports false duplicate ids.
_TASK_LINE: Final[re.Pattern[str]] = re.compile(
    r"^- \[(?P<box>[ x])\] \*\*(?P<id>\d{1,2}\.\d{1,2}[a-z]?)(?: ⚠)?\*\*"
)

#: A numbered design document — `docs/02-extension-model.md`, `docs/11-multimodal.md` and their
#: siblings. **`11` keeps a task list of its own** whose ids collide with the ledger's: its
#: `- [ ] **1.13**` is an unbuilt multimodal proposal, while the ledger's ticked `1.13` is about
#: resolution-failure subclasses. So an id in a sentence that hands the numbering to one of these
#: documents is not a ledger id — unless the sentence says `ledger` or names the ledger file, which
#: is how this tree writes it when it means one. Measured: this was a live false positive, and
#: `docs/lessons.md` L6.4 is the rule it breaks — the marker means what its instances say.
_NUMBERED_DOCUMENT: Final[re.Pattern[str]] = re.compile(r"docs/\d\d-[\w-]+\.md")
_LEDGER_ANCHOR: Final[re.Pattern[str]] = re.compile(r"ledger|build-ledger", re.IGNORECASE)

#: This tree's supersede-in-place convention: a blockquote beginning `Corrected`.
_CORRECTION: Final[re.Pattern[str]] = re.compile(r"^\s*>\s*\**\*?\(?Corrected")

#: How far after a hit a correction may sit and still be reading as the same passage. Measured
#: against the two live instances, which sit 8 and 2 lines after their own superseded sentence.
_CORRECTION_WINDOW: Final[int] = 12

#: **A sentence in the past tense is a record, not a standing claim**, and this tree writes plenty
#: of them: *"a pack's `register()` did not contribute one automatically, until task 5.2g"* says
#: 5.2g closed it, and *"'there is no derive command yet' stopped being true at task 3.7"* is the
#: correction itself quoting what it supersedes. Both carry a gap phrase and a ticked id and
#: neither is a defect. This is the same argument that excludes `build-ledger.md` wholesale,
#: applied at the sentence rather than at the file — measured, both were live false positives on
#: this check's first run.
_PAST_TENSE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:did not|was not|were not|had not|used to|stopped being|no longer|until then)\b",
    re.IGNORECASE,
)

#: Sentences this check cannot return an honest verdict on. **Pinned empty.** An entry is a visible
#: act in a diff; a sentence that is genuinely stale belongs in a repaired document instead.
STALE_GAP_WAIVERS: Final[frozenset[str]] = frozenset()


def ledger_task_states() -> dict[str, bool]:
    """Every ledger task id mapped to whether its box is ticked.

    Fence-tracked: `build-ledger.md` → *How to read a task line* holds an example task line inside
    a fenced block, and a sweep that reads it counts a task that does not exist.
    """
    states: dict[str, bool] = {}
    in_fence = False
    for line in (REPO_ROOT / "docs" / "build-ledger.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _TASK_LINE.match(line)
        if match:
            states[match.group("id")] = match.group("box") == "x"
    return states


def _documents() -> list[Path]:
    """Every prose document whose sentences make standing claims about this tree."""
    return sorted(
        path
        for path in [*(REPO_ROOT / "manual").glob("*.md"), *(REPO_ROOT / "docs").glob("*.md")]
        if path.name not in _EXCLUDED
    )


def _sentences_with_lines(text: str) -> list[tuple[int, int, str]]:
    """`(first line, last line, sentence)` for every sentence outside fences and table rows.

    **Lines are joined into paragraphs before sentences are cut out of them**, and that is not a
    convenience. These documents wrap at the house width, so a sentence that names a gap on one
    line routinely names the task that owns it on the next — and a sweep that reads line by line
    has a false negative built into the house style, which is `docs/lessons.md` L6.29 exactly. Two
    of this check's own true positives straddle a line break.

    Both ends of the passage are carried: a reader is sent to where it **starts**, and the
    correction window is measured from where it **ends**, because this tree's supersede-in-place
    blockquote follows the passage it corrects rather than preceding it.

    A table row is skipped — a row is a cell of independent claims rather than a passage — and a
    fenced block is skipped, because a quoted transcript is a record of output, never an assertion
    the document is making.
    """
    found: list[tuple[int, int, str]] = []
    in_fence = False
    paragraph: list[str] = []
    first = last = 0

    def flush() -> None:
        if not paragraph:
            return
        joined = " ".join(paragraph)
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z*`_—])", joined):
            if sentence.strip():
                found.append((first, last, sentence.strip()))
        paragraph.clear()

    for number, line in enumerate(text.splitlines(), 1):
        # A fence inside a blockquote opens `> ```python`, so the marker is found after the quote
        # markers are stripped — not at column 0. Measured: `02` §1 nests four of them, and reading
        # them as prose joined Python source into a sentence.
        if line.lstrip().lstrip(">").strip().startswith("```"):
            in_fence = not in_fence
            flush()
            continue
        if in_fence or line.lstrip().startswith("|") or not line.strip():
            flush()
            continue
        if not paragraph:
            first = number
        paragraph.append(line.strip().lstrip(">").strip())
        last = number
    flush()
    return found


def _correction_follows(lines: list[str], number: int) -> bool:
    return any(
        _CORRECTION.match(candidate) for candidate in lines[number : number + _CORRECTION_WINDOW]
    )


def stale_gap_claims() -> dict[str, str]:
    """Sentences asserting an open gap whose named task has since ticked."""
    states = ledger_task_states()
    stale: dict[str, str] = {}
    for document in _documents():
        text = document.read_text(encoding="utf-8")
        lines = text.splitlines()
        for first, last, sentence in _sentences_with_lines(text):
            if (
                sentence in STALE_GAP_WAIVERS
                or not _GAP.search(sentence)
                or _PAST_TENSE.search(sentence)
            ):
                continue
            if _NUMBERED_DOCUMENT.search(sentence) and not _LEDGER_ANCHOR.search(sentence):
                continue
            ticked = [
                identifier
                for match in _ANCHORED_ID.finditer(sentence)
                for identifier in (match.group(1) or match.group(2),)
                if states.get(identifier) is True
            ]
            if ticked and not _correction_follows(lines, last):
                stale[f"{document.relative_to(REPO_ROOT)}:{first}"] = (
                    f"{sentence[:180]} → task(s) {sorted(set(ticked))} are ticked"
                )
    return stale


def test_the_ledger_parses_into_a_population_worth_comparing_against() -> None:
    # The floor, both halves. An empty map compares nothing; an all-ticked or all-unticked map
    # means the box was not read (`docs/lessons.md` L5.19).
    states = ledger_task_states()
    assert states, "no task lines parsed out of build-ledger.md"
    assert any(states.values()), "no ticked task parsed — the box is not being read"
    assert not all(states.values()), "no unticked task parsed — the box is not being read"
    assert "N.M" not in states, "the fenced example task line was counted as a real task"


def test_no_document_asserts_a_gap_its_own_task_has_closed() -> None:
    # Arrange / Act
    stale = stale_gap_claims()

    # Assert
    assert not stale, (
        f"these sentences assert a gap whose owning task is ticked: {stale}. A prose gap outlives "
        f"its own repair by default and nobody re-reads the manuals for it (lessons-archive L7.5)."
    )


def test_a_correction_in_place_is_not_a_stale_gap() -> None:
    # The convention this tree actually uses, asserted rather than left implicit.
    lines = [
        "There is no `weft pipeline derive` command yet — that is task 3.7's surface.",
        "",
        "> **Corrected, 2026-08-20 (task 3.9).** That stopped being true at task 3.7.",
    ]
    assert _correction_follows(lines, 1)
    assert not _correction_follows(lines[:1], 1)


def test_the_check_can_actually_fail() -> None:
    # Plant L7.5's own shape and run it through the same predicates the sweep uses.
    planted = "That pack does not exist yet — task 5.4 builds it — so this section adapts a case."
    states = ledger_task_states()

    assert _GAP.search(planted), "the gap matcher does not fire on L7.5's own phrasing"
    named = [m.group(1) or m.group(2) for m in _ANCHORED_ID.finditer(planted)]
    assert named == ["5.4"], f"the id anchor read {named} rather than the task the sentence names"
    assert states["5.4"] is True, "5.4 is unticked, so this plant proves nothing"

    # And the anchor refuses the largest false-positive class: a section number is not a task id.
    assert not [
        m.group(1) or m.group(2) for m in _ANCHORED_ID.finditer("### 3.1 The gap this closes")
    ]


def test_the_waiver_is_a_visible_act() -> None:
    # The two-way ratchet. A waiver that no longer matches a real sentence is a waiver nobody can
    # see has stopped applying, which is the same invisibility the pinned-empty set exists to end.
    live = {entry.split(" → ")[0] for entry in stale_gap_claims().values()}
    stale_waivers = sorted(
        waiver for waiver in STALE_GAP_WAIVERS if not any(waiver[:60] in entry for entry in live)
    )
    assert not stale_waivers, (
        f"STALE_GAP_WAIVERS waives sentences no document carries any more: {stale_waivers}"
    )
