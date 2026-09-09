"""What this pack thinks a name looks like — one rule, two callers. Ledger **11.10**.

**Published because two things now ask the question.** `11.6`'s `cooccurrence-graph` matched
Title-Case runs in a *chunk* to find entity mentions; `11.10`'s `graph-walk` has to match them in
a *question* to find which entity it names. Those are the same rule, and a pack holding two
copies of it would let a question's notion of a name drift from the corpus's — a drift that fails
in the quietest possible way, as a graph query that matches nothing and looks like a corpus with
no answer rather than a query that was ever wrong. So `weft_kg.cooccurrence`'s own `_STOPWORDS`
frozenset, its leading-stopword strip and its Title-Case-run regex move here unchanged, and that
module imports them back — `tests/unit/weft_kg/test_cooccurrence.py` still asserts the same
counts, which is what says the move was a move and not a rewrite.

**`with_subspans` is the retriever's half, not the builder's.** A chunk's mention is written the
way the corpus writes it, so a maximal run is the right candidate there. A question is written by
somebody who may name the entity more briefly than the corpus did — *"what did Dostoevsky
write"* against an entity stored as *Fyodor Dostoevsky* — so `graph-walk` asks about each
candidate **and** its contiguous sub-spans. It stays one database round trip either way, because
`GraphTraversal.entities_by_name` takes the whole sequence, and it cannot invent an entity: every
name is matched exactly against rows the corpus actually produced.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

#: The longest name candidate `candidate_names` will return, in words, unless a caller overrides
#: it — `weft_kg.retrieval.GraphWalkConfig`'s own default, kept here beside the rule it configures
#: rather than duplicated at every caller.
DEFAULT_MAX_NAME_WORDS: Final[int] = 4

#: Words that are capitalised only because they open a sentence, not because they name
#: anything — filtered so a determiner does not become a candidate in every chunk or question
#: that happens to start with one. Written fresh for this pack, not carried from any other module
#: in this tree.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "A", "An", "And", "As", "At", "Because", "But", "By", "For", "From", "He", "How",
        "I", "If", "In", "Is", "It", "Its", "Of", "On", "Or", "She", "So", "Some", "That",
        "The", "There", "These", "They", "This", "Those", "To", "Was", "We", "Were",
        "What", "When", "Where", "Which", "Who", "Why", "With",
    }
)  # fmt: skip


def _cleaned(raw: str) -> str | None:
    """`raw`, whitespace-normalised, with every *leading* stopword stripped — `None` if nothing
    is left. A multi-word match starting a sentence ("The Board met...") would otherwise carry
    its sentence-initial stopword into the name ("The Board"); stripped only from the front,
    since a stopword is a sentence-initial artefact and the pattern below only ever matches a
    run starting where a capital letter begins.
    """
    words = raw.split()
    while words and words[0] in _STOPWORDS:
        words.pop(0)
    return " ".join(words) if words else None


def candidate_names(text: str, *, max_words: int = DEFAULT_MAX_NAME_WORDS) -> tuple[str, ...]:
    """Every Title-Case run in `text`, cleaned of its leading stopword, in order of first
    appearance — `weft_kg.cooccurrence`'s own rule, moved rather than rewritten.

    A run longer than `max_words` is cut into consecutive candidates of at most `max_words`
    words each, the same way a regex matched greedily up to a cap always has: `"New York City
    Council"` at `max_words=2` is `("New York", "City Council")`, two candidates from one run,
    not one candidate truncated.

    Duplicates are not collapsed here: a name mentioned twice in `text` is returned twice, in
    the order it was seen — `weft_kg.cooccurrence.CooccurrenceGraphBuilder` counts them itself,
    the same way it always has, and collapsing here would throw that count away before it ever
    reaches the caller that needs it. `weft_kg.names.with_subspans` is where a caller that wants
    a deduplicated set of seeds gets one.

    Raises `ValueError` naming `max_words` when it is below 1: `CooccurrenceSettings` already
    refuses that at construction, naming the same field, and this function must not silently
    disagree by returning an empty tuple for a value that was never valid.
    """
    if max_words < 1:
        raise ValueError(f"max_words must be at least 1 word; got {max_words}.")
    pattern = re.compile(rf"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){{0,{max_words - 1}}}\b")
    found: list[str] = []
    for match in pattern.finditer(text):
        name = _cleaned(match.group())
        if name is not None:
            found.append(name)
    return tuple(found)


def with_subspans(candidates: Sequence[str]) -> tuple[str, ...]:
    """Every candidate plus every **contiguous** sub-span of its words, deduplicated, longest
    first and then in the order each first appeared.

    Contiguous only: `"Saint Petersburg Institute"` yields `"Saint Petersburg"` and
    `"Petersburg Institute"` and never `"Saint Institute"` — a name is a phrase, and
    recombining its words the corpus never wrote would invent one. Longest first, so a caller
    that stops at the first match stops on the most specific one; a shorter sub-span of one
    candidate that is also a longer sub-span of another (or is simply repeated) is kept once.
    """
    by_length: dict[int, list[str]] = {}
    seen: set[str] = set()
    for candidate in candidates:
        words = candidate.split()
        for start in range(len(words)):
            for end in range(start + 1, len(words) + 1):
                span = " ".join(words[start:end])
                if span in seen:
                    continue
                seen.add(span)
                by_length.setdefault(end - start, []).append(span)
    ordered: list[str] = []
    for length in sorted(by_length, reverse=True):
        ordered.extend(by_length[length])
    return tuple(ordered)


__all__ = ["DEFAULT_MAX_NAME_WORDS", "candidate_names", "with_subspans"]
