"""Crude, deterministic entity and relation extraction — no model call, ever.

The task this pack exists to prove is the extension model, not entity resolution, so this
is intentionally the simplest thing that is still real: a Title-Case run of words is an
entity candidate, and any two entities the same node mentions co-occur. It will over- and
under-generate against a real corpus (a sentence-initial capitalised word with no proper
noun behind it is a false positive; a lower-cased acronym or a name split across a chunk
boundary is a false negative) — recorded here rather than hidden, since the point is that
the mechanism is honest and reproducible, not that the heuristic is good.
"""

import itertools
import re

from weft_example_graph.payload import Entity, Relation

#: Title-Case runs of up to four words — "Acme", "Acme Corp", "New York City Hall". Deliberately
#: simple: a real NER model is exactly what this pack must not use (crude and deterministic, per
#: this pack's own brief).
_ENTITY_PATTERN = re.compile(r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}\b")

#: Words that are capitalised only because they open a sentence, not because they name
#: anything — filtered so "The" and "This" do not become entities in every single node.
_STOPWORDS = frozenset(
    {
        "A",
        "An",
        "And",
        "As",
        "At",
        "But",
        "By",
        "For",
        "He",
        "I",
        "If",
        "In",
        "Is",
        "It",
        "Its",
        "On",
        "Or",
        "So",
        "Some",
        "That",
        "The",
        "There",
        "These",
        "They",
        "This",
        "Those",
        "Was",
        "We",
        "Were",
        "What",
        "When",
        "Where",
        "Which",
        "Who",
        "Why",
    }
)

#: A bound on how many distinct entities one node contributes, so a pathological node (a
#: table of proper nouns, say) cannot make the pairwise relation count quadratic without limit.
_MAX_ENTITIES_PER_NODE = 25


def _cleaned(raw: str) -> str | None:
    """`raw`, whitespace-normalised, with every *leading* stopword stripped — `None` if
    nothing is left. A multi-word match starting a sentence ("The Board met...") would
    otherwise carry its sentence-initial stopword into the entity name ("The Board"); this
    strips only from the front, since a stopword is a sentence-initial artefact and this
    pattern only ever matches a *run* starting where a capital begins.
    """
    words = raw.split()
    while words and words[0] in _STOPWORDS:
        words.pop(0)
    return " ".join(words) if words else None


def extract_entity_names(text: str) -> tuple[str, ...]:
    """Every distinct Title-Case run in `text`, in first-seen order, stopwords excluded.

    Whitespace inside a multi-word match is normalised (`"Acme  Corp"` and `"Acme\\nCorp"`
    both become `"Acme Corp"`) so the same name always has the same spelling — the property
    `weft_example_graph.store` relies on to match a query's own extracted names against stored ones.
    """
    seen: dict[str, None] = {}
    for match in _ENTITY_PATTERN.finditer(text):
        name = _cleaned(match.group())
        if name is None or name in seen:
            continue
        seen[name] = None
    return tuple(seen)[:_MAX_ENTITIES_PER_NODE]


def extract_graph_data(text: str) -> tuple[tuple[Entity, ...], tuple[Relation, ...]]:
    """This node's own entities (with in-node counts) and every pairwise co-occurrence.

    Relations are undirected and canonically ordered (`source < target`), so the same pair
    is never stored as both `(A, B)` and `(B, A)` — `weft_example_graph.store.GraphStore.add`
    upserts on that canonical pair.
    """
    counts: dict[str, int] = {}
    for match in _ENTITY_PATTERN.finditer(text):
        name = _cleaned(match.group())
        if name is None:
            continue
        counts[name] = counts.get(name, 0) + 1
    names = tuple(counts)[:_MAX_ENTITIES_PER_NODE]
    entities = tuple(Entity(name=name, count=counts[name]) for name in names)
    relations = tuple(
        Relation(source=source, target=target)
        for source, target in itertools.combinations(sorted(names), 2)
    )
    return entities, relations


__all__ = ["extract_entity_names", "extract_graph_data"]
