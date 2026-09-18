"""The gate of ledger task **39.1**: does `intent-and-anchors` separate questions it never saw?

`fix-plans/17`'s cheapest falsification, and the phase's stop: every anchor of the twenty questions
that carry one, and nothing for the twenty that carry none. Precision first, because a false anchor
costs every query the lexical noise Phase 38 measured at recall@5 0.244, while a missed one costs a
query only the dense arm it had anyway.

**The first forty failed it** at `578d0e8` — recall 1.000, precision 28/29, `DoH` read as camelCase
— and the clause was narrowed against them, so they are a regression set now and decide nothing.
The gate is the second forty, written after the narrowing was committed, by an agent that saw
neither the code nor the first set. A second miss reopens G24's Q-A rather than a second rewrite.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

from weft_retrieve.intent_and_anchors import find_anchors

FIXTURE: Final[Path] = Path(__file__).parent / "fixtures" / "anchor_questions_first.toml"


def _questions() -> list[tuple[str, str, tuple[str, ...]]]:
    raw = tomllib.loads(FIXTURE.read_text(encoding="utf-8"))
    return [(entry["id"], entry["text"], tuple(entry["anchors"])) for entry in raw["question"]]


def test_the_first_forty_are_the_set_the_gate_was_first_set_on() -> None:
    # Arrange
    questions = _questions()

    # Act
    carrying = [identifier for identifier, _, anchors in questions if anchors]

    # Assert
    assert len(questions) == 40
    assert len(carrying) == 20
    assert all(anchor in text for _, text, anchors in questions for anchor in anchors)


def test_the_first_forty_still_separate_after_the_narrowing() -> None:
    # Arrange
    questions = _questions()

    # Act
    missed: list[str] = []
    invented: list[str] = []
    for identifier, text, expected in questions:
        found = tuple(anchor.text for anchor in find_anchors(text))
        missed.extend(f"{identifier}: {anchor!r}" for anchor in expected if anchor not in found)
        invented.extend(f"{identifier}: {anchor!r}" for anchor in found if anchor not in expected)

    # Assert
    assert invented == [], f"false anchors — precision below 1.0: {invented}"
    assert missed == [], f"missed anchors — recall below 1.0: {missed}"
