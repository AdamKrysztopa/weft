"""Is this entity name a *thing*, or a fragment of a sentence? Ledger task **11.7**.

A model asked for subject–predicate–object triples answers with a great many rows that are
grammatically fine and useless as graph nodes: half-clauses (*"the effect of"*), equations
(*"K_per"*), citations (*"Smith et al."*) and references to the document's own furniture
(*"Section II"*). Every one of them becomes an entity nothing will ever ask about and that
matches many chunks, so a graph built without this filter is denser, slower and worse. Five
rules, applied to both endpoints of a candidate; a bad name makes the whole triple unusable, so
`weft_kg.extraction` drops the fact rather than half of it.

**This module is the first place in the repository where `NOTICE` case 2 fires, and the marker
below is what makes that visible.** The five rules, their constants and the LABEL-token guard
come from the project owner's own `graph-study`, written before Weft began — nobody else's to
license, and forbidding it would be a rule about tidiness dressed as a rule about ownership.
The carried lines are delimited in place with the convention `NOTICE` case 2 spells, and
`graph-study` is enumerated on the repository's `README.md`, where
`tests/architecture/test_release_licensing.py`'s task-11.0 block reads it. Nothing outside that
span is carried: the dispatch below, the reason it answers with, the parameterised word cap and
every word of prose in this file are Weft's own.

**What Weft changed, and why it is not cosmetic.** The donor's predicate answers `bool` and its
caller adds one integer, `non_atomic_dropped`, over five distinct rules. `11.7`'s own line
requires the opposite — *every dropped candidate is counted **per reason**, never summed* — so
this predicate answers **which rule fired**, and `weft_kg.payload.ExtractionTally` carries one
count per reason with no total anywhere. A corpus whose drops are mostly `document-reference`
needs a different repair from one whose drops are mostly `too-many-words`, and one integer
cannot tell an operator which they have. The word cap became a parameter for the same reason
requirement 6 makes every shipped constant one: six words is a good default for English prose
and a bad one for a corpus of chemical names.

**The LABEL-token guard is the subtlest line here and the easiest to lose.** Rule 5's keyword
list is ordinary English nouns — `table`, `figure`, `chapter`, `section`. Firing on the keyword
alone deletes *"table tennis"*, *"figure skating"* and every phrase built on one of them, and
the symptom is an absence: a corpus with a subject area silently missing, which no count reports
and no query complains about. The guard is that the keyword must be followed by a **label
token** — a number, a roman numeral, or a single letter — before it counts as pointing at the
document rather than naming a thing.
"""

from __future__ import annotations

import re
from typing import Final

from weft_kg.payload import DropReason

# weft-prior-work begin: graph-study
#
# The five rules' own constants, carried under `NOTICE` case 2 from the project owner's
# `graph-study` domain-extraction module. `_DOC_REF_RE` is split across two adjacent string
# literals because this repository's line limit is shorter than that project's; the pattern it
# compiles to is unchanged.

MAX_ENTITY_WORDS: Final[int] = 6

_TRAILING_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "of", "the", "a", "an", "and", "or", "to", "in", "on", "at", "for", "with",
        "by", "from", "as", "that", "which", "is", "are", "be", "than", "given", "where",
    }
)  # fmt: skip

# math operators / LaTeX commands / single-letter-subscript forms (K_per, I_t, σ², F(h;I_t))
_MATH_RE: Final[re.Pattern[str]] = re.compile(
    r"[=≤≥±∑∫√≈≠∞·×÷]|\\[a-zA-Z]+|[_^]\{?[A-Za-z0-9]|\b[A-Za-z]_[A-Za-z0-9]"
)

# citations: [n] markers, "et al", or a fully quoted title
_CITATION_RE: Final[re.Pattern[str]] = re.compile(
    r"""\[\d+\]|\bet\s+al\.?|^['"].*['"]$""", re.IGNORECASE
)

# document-structure references ("Section II", "Figure 3", "Table 1", "Appendix A", "Eq. 5")
# Only fires when the keyword is followed by a LABEL token (number / roman numeral / single
# letter), so common-noun phrases like "table tennis" or "figure skating" are NOT dropped.
_DOC_REF_RE: Final[re.Pattern[str]] = re.compile(
    r"^(section|figure|fig|table|appendix|chapter|eq|equation|algorithm|theorem|lemma"
    r"|proposition|corollary)\.?\s+(\d+|[ivxlcdm]{1,5}|[a-z])\b",
    re.IGNORECASE,
)

# weft-prior-work end


def non_atomic_reason(name: str, *, max_words: int = MAX_ENTITY_WORDS) -> DropReason | None:
    """Which rule refuses `name` as an entity, or `None` when it is a usable one.

    The rules are tried in the order above and the **first** one to fire is the answer. That
    ordering is a reporting decision rather than a correctness one — a name can break several
    rules at once — and it runs cheapest-first, so the count an operator reads is *"the first
    thing wrong with it"*, which is also the thing they would repair first.

    **An empty name answers `INCOMPLETE_ROW`, the same verdict `weft_kg.extraction` reaches
    first.** Two layers can diagnose a blank field, and the tree's rule where both can is that
    the first makes the check the second makes — so this predicate stays total rather than
    letting an empty name through whichever route it arrived by.
    """
    if max_words < 1:
        raise ValueError(
            f"max_words must be at least 1, not {max_words}: a cap below one refuses every "
            f"entity there is, and an operator would have to diagnose that from an empty graph "
            f"rather than from a message"
        )
    stripped = name.strip()
    if not stripped:
        return DropReason.INCOMPLETE_ROW
    words = stripped.split()
    if len(words) > max_words:
        return DropReason.TOO_MANY_WORDS
    if words[-1].strip(".,;:").lower() in _TRAILING_STOPWORDS:
        return DropReason.TRAILING_STOPWORD
    if _MATH_RE.search(stripped):
        return DropReason.MATHEMATICAL_NOTATION
    if _CITATION_RE.search(stripped):
        return DropReason.CITATION
    if _DOC_REF_RE.match(stripped):
        return DropReason.DOCUMENT_REFERENCE
    return None


__all__ = ["MAX_ENTITY_WORDS", "non_atomic_reason"]
