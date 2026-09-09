"""The non-atomic entity filter, one rule at a time. Ledger **11.7**.

Mirrors `packages/weft-rag/src/weft_kg/atomicity.py`.

**This is the first place in the repository where `NOTICE` case 2 actually fires.** The five
rules, their constants and the LABEL-token guard are carried from the owner's own `graph-study`
project, marked in place with the convention `NOTICE` case 2 spells and enumerated on the
repository's `README.md`. `tests/architecture/test_release_licensing.py`'s task-11.0 block is what
checks the marker and the enumeration agree; nothing here repeats that. What this file checks is
the behaviour, because a filter is only worth carrying if each of its rules can be seen firing on
its own.

**Why a reason rather than a boolean, and why that is Weft's own half.** The donor answers
`bool` and its caller adds one number, `non_atomic_dropped`. `11.7`'s own line requires the
opposite — *every dropped candidate is counted **per reason**, never summed* — so the predicate
here returns **which rule fired**, and `weft_kg.payload.ExtractionTally` carries one count per
reason with no total anywhere. A corpus whose drops are 80% `document-reference` needs a different
repair from one whose drops are 80% `too-many-words`, and a single integer cannot tell an operator
which they have.

**The LABEL-token guard is the rule most worth a test of its own.** *"Table 1"* is a reference to
a document's furniture and makes a useless entity; *"table tennis"* is an ordinary noun phrase and
dropping it would quietly delete a whole subject area from a corpus. The guard is the difference,
and it is one alternation in one regex — exactly the kind of thing a later simplification removes
without noticing, since every other test in this file still passes when it goes.
"""

from __future__ import annotations

import pytest

from weft_kg.atomicity import MAX_ENTITY_WORDS, non_atomic_reason
from weft_kg.payload import DropReason


def test_an_ordinary_name_is_atomic() -> None:
    """The floor. Without it every assertion below is satisfied by a filter that drops
    everything, which would score perfectly on five out of six tests here.
    """
    # Act / Assert
    assert non_atomic_reason("adRAP") is None
    assert non_atomic_reason("New York City") is None
    assert non_atomic_reason("reciprocal rank fusion") is None


def test_a_name_longer_than_the_word_cap_is_a_clause_rather_than_an_entity() -> None:
    """Rule 1. A model asked for a triple will happily answer with half a sentence as the
    object, and a graph whose nodes are clauses matches nothing a later question can name.
    """
    # Arrange — one word past the shipped cap, so the assertion is about the boundary.
    name = " ".join(f"word{index}" for index in range(MAX_ENTITY_WORDS + 1))

    # Act / Assert
    assert non_atomic_reason(name) is DropReason.TOO_MANY_WORDS
    assert non_atomic_reason(" ".join(f"word{index}" for index in range(MAX_ENTITY_WORDS))) is None


def test_a_name_ending_in_a_function_word_is_a_truncated_clause() -> None:
    """Rule 2. *"the effect of"* is a fragment the model stopped writing mid-phrase; keeping it
    puts a node in the graph that no question will ever name and that matches many chunks.
    """
    # Act / Assert
    assert non_atomic_reason("the effect of") is DropReason.TRAILING_STOPWORD
    assert non_atomic_reason("the effect") is None


def test_a_name_carrying_mathematical_notation_is_dropped() -> None:
    """Rule 3. Subscripts, operators and LaTeX commands survive extraction from a paper and
    make entity names no two chunks spell the same way.
    """
    # Act / Assert
    assert non_atomic_reason("K_per") is DropReason.MATHEMATICAL_NOTATION
    assert non_atomic_reason("energy ≤ threshold") is DropReason.MATHEMATICAL_NOTATION


def test_a_name_that_is_really_a_citation_is_dropped() -> None:
    """Rule 4. A citation names a *work*, not a thing the work is about, and the two are
    indistinguishable once both are entity rows.
    """
    # Act / Assert
    assert non_atomic_reason("Smith et al.") is DropReason.CITATION
    assert non_atomic_reason("[12]") is DropReason.CITATION


def test_a_reference_to_the_document_s_own_furniture_is_dropped() -> None:
    """Rule 5. *"Section II"* is about where the text sits, never about what it says."""
    # Act / Assert
    assert non_atomic_reason("Section II") is DropReason.DOCUMENT_REFERENCE
    assert non_atomic_reason("Table 1") is DropReason.DOCUMENT_REFERENCE
    assert non_atomic_reason("Eq. 5") is DropReason.DOCUMENT_REFERENCE


def test_the_label_token_guard_keeps_an_ordinary_noun_phrase() -> None:
    """The guard, and the one rule here that exists to *stop* a drop.

    Rule 5's keyword list holds ordinary English nouns — `table`, `figure`, `chapter`. Firing on
    the keyword alone would delete *"table tennis"*, *"figure skating"* and every phrase built on
    one of them from any corpus that mentions them, and the symptom would be an absence: a graph
    with a subject area silently missing, which no count reports and no query complains about.
    Only a following label token — a number, a roman numeral or a single letter — means the
    keyword is pointing at the document rather than naming a thing.
    """
    # Act / Assert
    assert non_atomic_reason("table tennis") is None
    assert non_atomic_reason("figure skating") is None
    assert non_atomic_reason("chapter house") is None


def test_an_empty_name_answers_the_same_reason_the_extractor_s_own_check_gives() -> None:
    """Two layers can diagnose a blank field, and they must not disagree about what it is.

    `weft_kg.extraction` checks a candidate's fields before ever reaching this predicate, so this
    branch is a fast path's echo rather than a second opinion — and the tree's rule where two
    layers can both diagnose is that the first makes the check the second makes. Answering `None`
    here would let an empty name through whichever way it arrived.
    """
    # Act / Assert
    assert non_atomic_reason("") is DropReason.INCOMPLETE_ROW
    assert non_atomic_reason("   ") is DropReason.INCOMPLETE_ROW


def test_the_word_cap_is_a_parameter_and_the_control_disagrees() -> None:
    """Requirement 6: the one number this filter turns on is an operator's, not a constant.

    The control is asserted to disagree with the subject, so the parameter is proven to do
    something rather than being read and ignored (`docs/lessons.md` L9.58).
    """
    # Arrange
    name = "one two three"

    # Act / Assert
    assert non_atomic_reason(name, max_words=2) is DropReason.TOO_MANY_WORDS
    assert non_atomic_reason(name, max_words=3) is None


@pytest.mark.parametrize("bad", [0, -1])
def test_a_word_cap_below_one_is_refused(bad: int) -> None:
    """A loud refusal, not a silent clamp: `max_words=0` drops every entity there is, and an
    operator would have to diagnose that from an empty graph rather than from a message.
    """
    # Act / Assert
    with pytest.raises(ValueError, match="max_words"):
        non_atomic_reason("anything", max_words=bad)
