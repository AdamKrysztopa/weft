"""The gate of ledger task **39.1**: does `intent-and-anchors` separate questions it never saw?

`fix-plans/17`'s cheapest falsification, and the phase's stop: every anchor of the twenty questions
that carry one, and nothing for the twenty that carry none. Precision first, because a false anchor
costs every query the lexical noise Phase 38 measured at recall@5 0.244, while a missed one costs a
query only the dense arm it had anyway.

**Neither form of the rule passed.** The first forty failed at `578d0e8` (precision 28/29, `DoH`);
the camelCase clause was narrowed against them, so they are a regression set here and decide
nothing. A fresh forty, written blind after the narrowing, failed it at `9aaa376` (precision
0.800, recall 0.923 — quantities read as identifiers, errno names missed), which reopened G24's
Q-A. The gate moved to the model decomposition, over both sets:
`tests/integration/test_intent_and_anchors_model_gate.py`.
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


def test_the_rule_invents_no_anchor_on_the_first_forty_and_misses_only_a_header() -> None:
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
    # A header named as one became an anchor when Codex's review sharpened the definition; the
    # rule refuses hyphenated words without a digit by design, which is why `method: model`
    # exists.
    assert missed == ["a05: 'cache-control'"]
