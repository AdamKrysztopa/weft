"""No shipped technique claims an improvement with no run behind it — ledger task **6.9**.

`docs/09-release.md` §5.2, *Quality*: "Every shipped technique's claimed improvement is a delta
against V3 on the same corpus, pipeline and model versions. *Fails if any claim in the
documentation has no run behind it.*"

**Half of this was already built and the other half had nothing.** `eval/check_baseline.py`
(task 4.8) answers *"did this run reproduce the baseline"* — intervals derived from the baseline's
own repetitions, `IncomparableRunsError` when the corpus, pipeline or model versions differ. What
nothing checked is the sentence's actual subject: the **documentation**. A number in a manual is
what a reader acts on, and it is reachable by anyone with a text editor and no run at all.

**Two clauses, because a marker alone cannot catch what matters.**

- **(a) A marked claim names a baseline run that exists.** A claim is written as a fenced
  ` ```text id=claim:<technique> ` block naming a file under `eval/baselines/` — the same
  tagged-block mechanism `tests/architecture/test_ff11_pipeline_integrity.py` already uses for
  ` ```yaml id=pipeline:<name> `, for the same reason: a marker is a structural fact, where prose
  is a guess.
- **(b) No claim-shaped prose exists outside such a block.** Clause (a) on its own is worthless,
  and dangerously so: it polices the claims that opted in and is blind to *"raptor improves recall
  by 12%"* typed straight into a manual, which is the entire failure mode. So the shipped
  documentation is swept for claim-shaped language, with a **pinned waiver** for the passages that
  quote V3's own failure clause rather than making a claim.

**The subject is legitimately empty today**, which is exactly when a check proves nothing
(`docs/lessons.md` L5.19): no shipped document makes a numeric improvement claim about a technique,
measured rather than assumed. So clause (a) carries a planted self-test, and clause (b)'s waiver is
non-empty and real — it names the two passages in `manual/` that quote the rule, so the sweep is
demonstrably finding things rather than matching nothing.

**Why the sweep is over `manual/` and `README.md` and not over `docs/`.** `08` §1 defines the
shipped documentation set, and `09` §5's own clause sits under *"Security, licensing,
documentation"* — the published artefacts. `docs/` is the plan, where the rule is stated,
discussed and quoted at length; sweeping it would make every discussion of the rule a violation of
it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

MANUAL: Final[Path] = REPO_ROOT / "manual"
README: Final[Path] = REPO_ROOT / "README.md"
BASELINES: Final[Path] = REPO_ROOT / "eval" / "baselines"

#: A claim block: ` ```text id=claim:<technique> `, the same shape FF11's pipeline blocks take.
_CLAIM_BLOCK: Final[re.Pattern[str]] = re.compile(
    r"^```text\s+id=claim:(?P<technique>\S+)\n(?P<body>.*?)^```\s*$", re.MULTILINE | re.DOTALL
)

#: Claim-shaped language. Deliberately over-inclusive: a false positive costs one waiver entry
#: and a false negative costs a published number nobody can reproduce, so the asymmetry decides
#: the tuning. `docs/lessons.md` L5.28 is why this is not the *only* clause — a substring sweep is
#: unsound on its own — and why clause (a) exists beside it.
#:
#: **The gap between the two halves is `.{0,80}?` over whitespace-collapsed text, and getting
#: there took two corrections.** It was `[^.\n]{0,80}` first, which cannot cross a `.` — so it
#: never matched `"improvement... reported against a baseline"`, the exact phrasing both real
#: passages use, and the sweep matched nothing at all in the entire shipped set while every test
#: in this file passed. Excluding newlines was the second miss: the manuals wrap at 100 columns,
#: so a claim and its number routinely sit on different lines, and a detector that cannot cross a
#: line break has a false negative built into the house style. Both were found by emptying
#: `CLAIM_PROSE_WAIVED` and watching the check stay green (`docs/lessons.md` L6.29). The sweep
#: therefore runs over a whitespace-collapsed copy and reports the matched text rather than a line
#: number — the match is what identifies the claim, and a line number that came from a collapsed
#: copy would be a lie.
_CLAIM_PROSE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:improves?|improvement|outperforms?|better than|uplift|gain of)\b.{0,80}?"
    r"\b(?:\d+(?:\.\d+)?\s*(?:%|pp|points?)|baseline)\b",
    re.IGNORECASE,
)

#: Passages that **quote V3's own failure clause** rather than making a claim — the manuals
#: explaining to an operator why `weft eval compare` refuses two runs that are not comparable.
#: Pinned, and each is written as the span the sweep actually produces, so a reworded passage
#: stops being excused rather than silently continuing to excuse something else — and
#: `test_the_waiver_still_excuses_something` fails when one stops firing, which is what proves
#: clause (b) is running at all.
CLAIM_PROSE_WAIVED: Final[frozenset[str]] = frozenset(
    {
        "improvement... reported against a baseline",
        "improvement is reported against... a baseline",
    }
)


def _shipped_documents() -> list[Path]:
    return sorted([*MANUAL.glob("*.md"), README])


def _claim_blocks() -> list[tuple[Path, str, str]]:
    """Every `(document, technique, body)` claim block in the shipped documentation."""
    found: list[tuple[Path, str, str]] = []
    for path in _shipped_documents():
        text = path.read_text(encoding="utf-8")
        found.extend(
            (path, match.group("technique"), match.group("body"))
            for match in _CLAIM_BLOCK.finditer(text)
        )
    return found


def _prose_outside_claim_blocks(text: str) -> str:
    """`text` with every claim block removed and its whitespace collapsed to single spaces."""
    return re.sub(r"\s+", " ", _CLAIM_BLOCK.sub(" ", text))


def claim_shaped_prose(documents: list[Path]) -> list[str]:
    """Every claim-shaped span outside a claim block, whatever the waiver says.

    Separate from `unmarked_claims` on purpose: this is what the waiver-liveness test needs, and
    a function that applied the waiver could never show that the sweep fires at all.
    """
    return [
        f"{path.name}: {match.group(0)}"
        for path in documents
        for match in _CLAIM_PROSE.finditer(
            _prose_outside_claim_blocks(path.read_text(encoding="utf-8"))
        )
    ]


def unmarked_claims(documents: list[Path]) -> list[str]:
    """Every claim-shaped span in `documents` that is neither in a claim block nor waived."""
    return [
        hit
        for hit in claim_shaped_prose(documents)
        if not any(waived in hit for waived in CLAIM_PROSE_WAIVED)
    ]


def test_the_shipped_documentation_set_is_found() -> None:
    """The floor. A sweep over nothing reports no violations, which is not the same answer."""
    # Act
    documents = _shipped_documents()

    # Assert
    assert len(documents) > 3, f"only {documents} were swept — the glob is wrong, not the manuals"
    assert README in documents


def test_every_marked_claim_names_a_baseline_run_that_exists() -> None:
    """Clause (a). `09` §5.2: a claim with no run behind it fails."""
    # Arrange
    published = {path.name for path in BASELINES.glob("*.json")}

    # Act
    unbacked = [
        f"{path.name}: claim for '{technique}' names no published baseline run"
        for path, technique, body in _claim_blocks()
        if not any(name in body for name in published)
    ]

    # Assert
    assert published, (
        f"no baseline run is published under {BASELINES}. Every claim below would be unbacked by "
        f"construction, and V3 requires the baseline to exist as a persisted run."
    )
    assert not unbacked, (
        "\n".join(unbacked) + "\n\nA claimed improvement is a delta against the published "
        "baseline and nothing else (`09` §4, V3). Name the run file the number came from."
    )


def test_no_shipped_document_claims_an_improvement_outside_a_claim_block() -> None:
    """Clause (b), and the one that catches the failure that actually happens: a number typed
    into a manual by someone who never ran anything.
    """
    # Act
    unmarked = unmarked_claims(_shipped_documents())

    # Assert
    assert not unmarked, (
        "claim-shaped text outside a claim block:\n  " + "\n  ".join(unmarked) + "\n\n"
        "`09` §5.2: every shipped technique's claimed improvement is a delta against the "
        "published baseline, and it fails if any claim in the documentation has no run behind "
        "it. Put the number in a ```text id=claim:<technique> block naming the run it came "
        "from, or take it out."
    )


def test_the_waiver_still_excuses_something() -> None:
    """A ratchet whose entries have stopped matching is a ratchet that reads shorter than it is —
    `test_ff0_gate_in_the_gate.py` makes the identical check about its own waived suites.

    This one does double duty: the waived passages are the only claim-shaped text in the shipped
    set today, so a waiver that matched nothing would also mean the sweep matches nothing, and
    clause (b) above would be passing vacuously.
    """
    # Arrange — what has to be true is that the **sweep** fires on the waived passages, not
    # merely that their text is somewhere in the corpus. The first version of this test asserted
    # the latter and passed while the regex matched nothing anywhere (`docs/lessons.md` L6.29):
    # a waiver-liveness check that never runs the check it excuses proves nothing about it.
    matched = claim_shaped_prose(_shipped_documents())

    # Act
    stale = sorted(
        waived for waived in CLAIM_PROSE_WAIVED if not any(waived in hit for hit in matched)
    )

    # Assert
    assert matched, (
        "the claim-prose sweep matched nothing in the entire shipped documentation set. Clause "
        "(b) is then inert whatever the waiver says, and its green is meaningless."
    )
    assert not stale, (
        f"{stale} is waived and the sweep does not fire on it. Either the passage was reworded — "
        f"delete the entry — or the pattern stopped matching it, in which case the waiver is "
        f"hiding that clause (b) may now be matching nothing at all."
    )


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """Both clauses, planted through the real readers — the real set is empty, so this is the
    only place either comparison is seen disagreeing (`docs/lessons.md` L5.19).
    """
    # Arrange — one unbacked claim block, and one bare number in prose.
    document = tmp_path / "planted.md"
    document.write_text(
        "# Planted\n\n"
        "```text id=claim:raptor\n"
        "raptor improves nDCG@10 by 12% over a run nobody named.\n"
        "```\n\n"
        "And in prose: hybrid retrieval improves recall by 9% over the baseline.\n",
        encoding="utf-8",
    )
    text = document.read_text(encoding="utf-8")

    # Act
    blocks = [
        (match.group("technique"), match.group("body")) for match in _CLAIM_BLOCK.finditer(text)
    ]
    unbacked = [
        technique for technique, body in blocks if "8854c33f71ea-2026-08-20.json" not in body
    ]
    unmarked = unmarked_claims([document])

    # Assert
    assert blocks and blocks[0][0] == "raptor", "the claim-block reader found nothing to judge"
    assert unbacked == ["raptor"]
    assert len(unmarked) == 1, f"the prose sweep found {unmarked}"
    assert "recall by 9%" in unmarked[0]
