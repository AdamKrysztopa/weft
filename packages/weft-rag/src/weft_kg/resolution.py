"""Which surface forms are one entity — pure, deterministic, no I/O. Ledger task **11.8**.

The pass runs through `weft_store.contract.Reconcilable`, not as a pipeline stage: the Phase 11
preamble's narrowing of **G15** puts this pack's entity and alias rows on the footing
`weft_store`'s and `weft_qdrant`'s own tables already have — a `NodeStore` backend's internal
schema — rather than under G15's *"no rows that are not nodes"*, which governs what a *stage*
persists outside the node model. `weft_kg.store.GraphStore.reconcile` is the caller; everything
in this module is a function of its arguments.

**The split, and why the database keeps the half it keeps.** The donor this is carried from
computes similarity itself: it loads every name's embedding, builds an n×n cosine matrix and a
rapidfuzz ratio per pair. Weft does neither. `pg_trgm` scores the lexical term and pgvector the
cosine, in one query, over the pairs an index can reach — so the blend never materialises a
matrix, adds no dependency, and prunes candidates the way a database prunes. What is left is the
part SQL cannot do and is exactly what this module is: the **transitive closure** over the pairs
that survived, and the **choice of representative**.

**Why the representative is the lexicographically smallest member.** `11.8`'s own line: the
canonical id is a function of the **set**, not of arrival order. Every alternative that looks
better is a function of history — the most-mentioned form depends on what has been indexed so
far, the first-seen form on the order rows were written — so the same cluster would canonicalise
differently after a second document arrived, and every fact already written against the old id
would point at nothing. `min()` over the members depends on the members alone, which is what makes
a second run unable to change what the first decided.

**Three signals, and each is here because the other two cannot see what it sees.**

1. **Blended similarity**, scored in the database and arriving here as `similar_pairs`. The blend
   is not caution, it is two specific failure modes vetoing each other. *A degenerate embedder*
   — the donor's own recorded finding — pushes every cosine towards 1.0, so a vector-only rule
   merges a whole corpus into one entity, and the lexical term is what refuses that. *Lexical
   similarity alone* merges names that look alike and are not: `adRAP` and `adRAG` differ by one
   character and are two techniques, and trigram similarity cannot tell them apart, so the vector
   term is what refuses that. Neither failure is rare and neither is visible in the output —
   both produce a plausible graph over the wrong entities.
2. **A definition the text itself stated** — *Reciprocal Rank Fusion (RRF)* — which is the
   highest-precision signal available, because the corpus asserted the pair rather than a
   heuristic inferring it. It is exact, so it carries no threshold.
3. **A gated initialism**, for the far more common case where no definition was ever written. The
   letters alone are weak evidence — `RRF` is equally the initialism of *Rapid Response Force* —
   so this signal is gated twice: a **cosine floor**, and a **single-expansion rule** that
   abstains entirely when one short form matches two long forms. Abstaining leaves two entities
   that are one, which is wrong in a way a reader can see; picking one by iteration order would
   be wrong in a way that reads as a finding, and would violate this task's own line.

**A missing cosine is *not known*, never *close enough*.** An alias row with no embedding cannot
clear the floor. Treating an absent number as passing would make signal 3 fire hardest exactly where
there is least evidence, which is the inverse of what a gate is for — `docs/internal/lessons.md`
L5.9's rule for an empty collection, applied to a missing number.

**The signal this pass leans hardest on has exactly one rung that supplies it — carried repair
`R11.5`, measured at `11.9` and closed 2026-09-10.** `index-text` names `embed: hash`, and every
rung that derives from it inherits that, `index-with-graph`, `index-with-cooccurrence` and
`index-with-facts` included; a `--pipeline` run deliberately does not read `[services] embed`. A
content-hash vector has no semantic geometry, so signal 1's blend collapses to its lexical third
and signal 3's cosine floor is unreachable except by accident. Measured through the shipped binary
on a real two-document corpus: every alias pair scored between `0.105` and `0.165`, *Reciprocal
Rank Fusion* against *RRF* included. The same corpus with the embed stage replaced by
`openai-embeddings` put *Warsaw Institute* against *Warszawski Instytut* at `0.647`.

That replacement is now a **shipped document rather than an instruction** —
`index-with-facts-openai`, one `replace:` block over `index-with-facts`, the owner's decision on
2026-09-10 — so this pass has a rung on which its vector term means something and a reader no
longer has to derive one before pointing it at a corpus. The cost is on that document's own face:
it needs a credential. `index-with-facts` and `index-with-cooccurrence` are untouched and still
climb on a machine with no account, where this pass is the lexical third of itself and says so.

**Carried prior work — `NOTICE` case 2.** The initialism rule and its stopword set, the
short-form shape test, the Schwartz–Hearst patterns and their initialism validation, the
acronym-collision guard and the path-compressed union-find come from the project owner's own
`graph-study`, marked in place below and enumerated on the repository's `README.md` beside the
atomicity filter `11.7` carried. Two things inside the marked spans are Weft's repairs rather
than the donor's text, and each says so where it sits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Final

#: How much of the blended score is the vector term. The lexical term takes the rest. Scored in
#: `weft_kg.store`, not here; published here because it is the number the two failure modes above
#: trade off against each other, and a reader changing it should meet them first.
DEFAULT_VECTOR_WEIGHT: Final[float] = 0.7

#: The blended score at which two surface forms are one entity.
DEFAULT_SIMILARITY_THRESHOLD: Final[float] = 0.83

#: Signal 3's gate — see the module docstring. Deliberately far below
#: `DEFAULT_SIMILARITY_THRESHOLD`: this is not "these are the same", it is "the letters say they
#: might be, and the vectors do not rule it out."
DEFAULT_COSINE_FLOOR: Final[float] = 0.4

# weft-prior-work begin: graph-study
#
# The acronym signals and the union-find, carried under `NOTICE` case 2 from the project owner's
# `graph-study` domain layer. Two repairs inside this span are Weft's own and are commented as
# such at the line: the window search in `acronym_definitions`, and the tuple return.

_INITIALISM_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "the", "of", "and", "for", "to", "in", "on", "at", "by", "with", "from", "or",
    }
)  # fmt: skip

#: A short form is an initial capital followed by 1–9 more capitals or digits.
_SHORT_FORM: Final[str] = r"[A-Z][A-Z0-9]{1,9}"

#: `Long Form (SF)` — the classical forward order.
_FORWARD: Final[re.Pattern[str]] = re.compile(r"\(" + _SHORT_FORM + r"\)")

#: `SF (Long Form)` — the reverse order, equally ordinary in prose.
_REVERSE: Final[re.Pattern[str]] = re.compile(r"\b(" + _SHORT_FORM + r")\s+\(([^()]+)\)")


def initialism(name: str) -> str:
    """The initials of `name`'s significant words — `Reciprocal Rank Fusion` → `RRF`.

    Function words are skipped because a reader writing the short form skips them: *Department of
    Health and Human Services* is written `DHHS`, never `DOHAHS`, so a rule that kept them would
    match nothing anybody actually writes.
    """
    letters: list[str] = []
    for word in name.split():
        clean = word.strip(".,;:()'\"-")
        if not clean or clean.lower() in _INITIALISM_STOPWORDS:
            continue
        letters.append(clean[0].upper())
    return "".join(letters)


def is_short_form(name: str) -> bool:
    """Whether `name` has the *shape* of an acronym — all capitals, 2–10 characters, one word.

    Shape rather than a list: a list of known acronyms is a corpus-specific asset this pack
    cannot ship, and it would silently do nothing on the first corpus nobody wrote it for.
    """
    stripped = name.strip()
    return 2 <= len(stripped) <= 10 and stripped.isupper() and " " not in stripped


def acronym_definitions(text: str) -> tuple[tuple[str, str], ...]:
    """Every `(short, long)` pair `text` itself defines, in the order it defines them.

    Both orders are read. A pair is returned only when the long form's own initials produce the
    short form, which is what keeps this a *definition* signal rather than a proximity one: prose
    is full of capitalised words before parentheses, and a rule that fired on all of them would
    merge unrelated entities with the confidence this signal is trusted for.

    Reported once per distinct pair, however often the text repeats it: the fact is *that the
    corpus defined the pair*, and a count would describe the prose rather than the entity.
    """
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for match in _FORWARD.finditer(text):
        short = text[match.start() + 1 : match.end() - 1]
        words = text[: match.start()].rstrip().split()
        # **Weft's repair, inside the carried span.** The donor takes the whole window as the long
        # form and validates once, so it finds a definition only when the sentence begins where
        # the long form does — `We use Reciprocal Rank Fusion (RRF)` yields nothing. Searching the
        # window shortest-first and taking the first candidate that validates finds the *minimal*
        # expansion, which is both the correct one and the more precise choice.
        window = words[-(len(short) + 5) :]
        for size in range(1, len(window) + 1):
            candidate = " ".join(window[-size:])
            if _defines(short, candidate):
                _remember(found, seen, short, candidate)
                break

    for match in _REVERSE.finditer(text):
        short, candidate = match.group(1), match.group(2).strip()
        if re.fullmatch(_SHORT_FORM, candidate):
            continue
        if _defines(short, candidate):
            _remember(found, seen, short, candidate)

    return tuple(found)


def _defines(short: str, long_form: str) -> bool:
    return initialism(long_form).upper() == short.upper()


def _remember(
    found: list[tuple[str, str]], seen: set[tuple[str, str]], short: str, long_form: str
) -> None:
    key = (short.upper(), long_form.casefold())
    if key not in seen:
        seen.add(key)
        found.append((short, long_form))


class _UnionFind:
    """Path-halving union-find over an index range."""

    __slots__ = ("_parent",)

    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, index: int) -> int:
        while self._parent[index] != index:
            self._parent[index] = self._parent[self._parent[index]]
            index = self._parent[index]
        return index

    def union(self, left: int, right: int) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[left_root] = right_root


# weft-prior-work end


def resolve_clusters(
    names: Sequence[str],
    *,
    similar_pairs: Iterable[tuple[str, str]] = (),
    acronym_definitions: Iterable[tuple[str, str]] = (),
    cosines: Mapping[tuple[str, str], float] | None = None,
    cosine_floor: float = DEFAULT_COSINE_FLOOR,
) -> Mapping[str, str]:
    """`{surface form: representative}` — the three signals closed transitively.

    `similar_pairs` is signal 1, already scored and thresholded by `weft_kg.store`'s own query;
    nothing here re-derives it, and nothing here adds a pair of its own. `acronym_definitions` is
    signal 2, matched case-insensitively at both ends, because a paper that writes `adRAP` in one
    sentence and `ADRAP` in the next has defined one thing. `cosines` is signal 3's gate, read in
    either order for a pair; absent means *not known*, and refuses the merge.

    A pair naming a surface form `names` does not list is refused rather than absorbed: it comes
    from a query over this same alias set, so a name that is not here means the two disagree
    about what the corpus holds, and inventing the entity would put a node in the graph that no
    mention supports.
    """
    ordered = list(names)
    position = {name: index for index, name in enumerate(ordered)}
    union = _UnionFind(len(ordered))
    scores: Mapping[tuple[str, str], float] = cosines if cosines is not None else {}

    for left, right in similar_pairs:
        for name in (left, right):
            if name not in position:
                raise ValueError(
                    f"a similar-pair names {name!r}, which is not one of the {len(ordered)} "
                    f"surface forms this pass was given. The pairs come from a query over this "
                    f"same alias set, so a name that is not here means the two disagree about "
                    f"what the corpus holds — inventing the entity would put a node in the graph "
                    f"that no mention supports."
                )
        union.union(position[left], position[right])

    _apply_definitions(ordered, position, union, acronym_definitions)
    _apply_initialisms(ordered, position, union, scores, cosine_floor)

    members: dict[int, list[str]] = {}
    for index, name in enumerate(ordered):
        members.setdefault(union.find(index), []).append(name)
    return {name: min(cluster) for cluster in members.values() for name in cluster}


def _apply_definitions(
    names: Sequence[str],
    position: Mapping[str, int],
    union: _UnionFind,
    definitions: Iterable[tuple[str, str]],
) -> None:
    """Signal 2. Exact, case-insensitive, and unthresholded — the text said so."""
    folded: dict[str, list[str]] = {}
    for name in names:
        folded.setdefault(name.casefold(), []).append(name)
    for short, long_form in definitions:
        shorts = folded.get(short.casefold(), ())
        longs = folded.get(long_form.casefold(), ())
        for one in shorts:
            for other in longs:
                union.union(position[one], position[other])


def _apply_initialisms(
    names: Sequence[str],
    position: Mapping[str, int],
    union: _UnionFind,
    cosines: Mapping[tuple[str, str], float],
    floor: float,
) -> None:
    """Signal 3, with both gates. See the module docstring for why each one is worth its cost."""
    expansions: dict[str, set[str]] = {}
    pairs: dict[str, list[tuple[str, str]]] = {}
    for short, long_form in initialism_candidates(names):
        cosine = cosines.get((short, long_form), cosines.get((long_form, short)))
        if cosine is None or cosine < floor:
            continue
        expansions.setdefault(short.upper(), set()).add(long_form.casefold())
        pairs.setdefault(short.upper(), []).append((short, long_form))

    for key, seen in expansions.items():
        if len(seen) != 1:
            # The acronym-collision guard: two long forms, no way to choose but iteration order,
            # which is the one thing `11.8`'s line forbids. Abstain.
            continue
        for short, long_form in pairs[key]:
            union.union(position[short], position[long_form])


def _short_and_long(one: str, other: str) -> tuple[str, str] | None:
    """`(short, long)` when exactly one of the two has a short form's shape, else `None`."""
    if is_short_form(one) and not is_short_form(other):
        return one, other
    if is_short_form(other) and not is_short_form(one):
        return other, one
    return None


def initialism_candidates(names: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Every `(short, long)` pair from `names` that signal 3 could possibly merge on.

    **Why this is published rather than left inline.** `11.8` had `weft_kg.store` fetch every
    alias pair's cosine and hand the whole map to `resolve_clusters` — `O(corpus²)` in memory, and
    recorded on `GraphStore`'s own resolution pass as a cost belonging to this task rather than
    ahead of it. But the set of pairs signal 3 can possibly act on is a function of the *names*
    alone: it only ever looks up a pair where one name has a short form's shape and the other's
    initials spell it, and that shape test needs no database at all. Computing it first lets the
    store ask pgvector for exactly those pairs' cosines instead of every pair in the corpus, and
    publishing it is what lets `_apply_initialisms` and `weft_kg.store` ask the identical question
    rather than one of them silently drifting from the other.

    **The narrowing must be exact, never merely smaller.** A pair signal 3 would have consulted
    that this function omits is a merge that silently stops happening — so the two gates below are
    exactly `_apply_initialisms`'s own: `_short_and_long` for the shape, and `initialism` uppercased
    against the short form for the spelling. Order matches the nested loop that check replaces —
    outer index ascending, inner over `names[index + 1 :]` — so a caller consuming this in order
    sees exactly what the inline loop used to produce.
    """
    candidates: list[tuple[str, str]] = []
    for index, one in enumerate(names):
        for other in names[index + 1 :]:
            candidate = _short_and_long(one, other)
            if candidate is None:
                continue
            short, long_form = candidate
            if initialism(long_form).upper() != short.upper():
                continue
            candidates.append((short, long_form))
    return tuple(candidates)


__all__ = [
    "DEFAULT_COSINE_FLOOR",
    "DEFAULT_SIMILARITY_THRESHOLD",
    "DEFAULT_VECTOR_WEIGHT",
    "acronym_definitions",
    "initialism",
    "initialism_candidates",
    "is_short_form",
    "resolve_clusters",
]
