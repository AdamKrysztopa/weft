"""A bridge: a two-hop path whose endpoints share no chunk. Ledger **11.13**.

The pure half of `weft graph bridges`, mirroring `weft_kg/schema.py`'s own role beside
`store.py`: the models a bridge is built from, the two errors a run can end in, and the two
functions that turn what `GraphStore` measured into what a person or `weft eval run --questions`
reads. No container and no model call here — `weft_kg.commands` is the half that talks to the
store and prints; this module has no dependency capable of either.

**Why a bridge is defined by "no single node names both endpoints", never by "no single
document".** `01`'s falsification argument is about what a single-passage *retriever* can answer
from, and the unit a retriever returns is a node — `weft_kg.store.GraphStore`'s own `kg_nodes`
row, the same granularity `weft_store.pgvector_store.PgVectorStore` returns a hit at. A document
spans many chunks; two facts that happen to sit in the same document but in different chunks are
still a bridge by this test, exactly as they would be for a real vector search over that corpus.

**The ceiling is measured twice on purpose, and `bridges_from` is where the two numbers are made
to disagree or not — `docs/lessons.md` `L5.6`.** `GraphStore.two_hop_bridges`'s own `NOT EXISTS`
clause is what *selects* a candidate in the first place; reading the ceiling off that same clause
would be a comparison whose two sides come from one source and could never fail.
`GraphStore.chunks_by_entity` is an independent second query, and `bridges_from` is the one place
in this pack that compares its answer against the walk's own claim.  Agreement lets the ceiling
be printed; disagreement raises `CeilingDisagreesError` rather than printing either number.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import WeftError

#: `weft_cli.eval_scoring.Question.kind` for every question this module writes — task `11.12`'s
#: own `--kind` filter is what turns `weft eval compare … --kind requires-graph-hop` into a
#: measurement over exactly these questions and nothing else.
QUESTION_KIND: Final[str] = "requires-graph-hop"


class BridgeHop(BaseModel):
    """One edge of a bridge, **as the corpus stated it**, and its own citation.

    `node_id` is the `kg_nodes` row whose `ExtractedFact` (or co-occurrence edge) anchored *both*
    of this hop's endpoints — never the path as a whole, so a reader can check each hop against
    the exact evidence that produced it. `documents` is that node's own `sources`, sorted.

    **`source` and `predicate` and `target` read in the direction the fact was written, never in
    the direction the walk travelled.** A walk over `kg_relations` is undirected — `GraphWalk.
    neighbourhood` has always walked it that way, and rightly, because it returns entities and
    states no predicate. This carries a predicate, so the two stop being interchangeable: a hop
    the walk reached backwards, printed forwards, is the corpus's own claim inverted, standing
    beside a citation that is perfectly real. `Bridge.endpoints` and `Bridge.via` carry the walk's
    direction instead, as fields of their own, so neither fact has to be recovered from the
    other.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    predicate: str
    target: str
    node_id: str
    documents: tuple[str, ...]


class BridgeCandidate(BaseModel):
    """One two-hop path `GraphStore.two_hop_bridges` found, before the ceiling has been measured.

    `source_entity`/`target_entity` are `kg_entities.id` — what `chunks_by_entity` is keyed by,
    the second, independent query `bridges_from` compares its own walk against.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_entity: str
    source_name: str
    via_name: str
    target_entity: str
    target_name: str
    first: BridgeHop
    second: BridgeHop


class VectorCeiling(BaseModel):
    """The best any single-passage retriever could reach on this bridge's own question — a fact
    about the corpus, never about an embedder. `chunks_holding_both` is always `0` here: it is
    what a `Bridge` exists to guarantee, restated as a number rather than trusted as a name.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoints: tuple[str, str]
    chunks_holding_both: int
    chunks_holding_either: int
    best_single_chunk_endpoints: int


class Bridge(BaseModel):
    """A `BridgeCandidate` whose ceiling has been measured and agreed, plus the diagnostic
    question it stands for. `question_id` is deterministic — the same corpus produces the same
    id across two runs — so a promoted question keeps its identity even as the corpus is
    re-walked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    hops: tuple[BridgeHop, BridgeHop]
    #: The two entities the question is about, in the walk's own direction. A **field**, not a
    #: property over `hops`: a hop reads in the direction the corpus stated it, so deriving the
    #: path from `hops[0].source` would be right exactly when no hop was walked backwards.
    endpoints: tuple[str, str]
    #: The entity both hops share — what a single-passage retriever would have to already know.
    via: str
    ceiling: VectorCeiling
    question: str
    question_id: str
    relevant_documents: tuple[str, ...]


class NoRelationsToBridgeError(WeftError):
    """This corpus holds no `kg_relations` row at all — `weft_kg.schema.propose_schema`'s own
    split between "nothing was extracted" and "nothing survived a threshold", the first half of
    it: a bridge is built from relations, and a corpus that never produced one needs indexing,
    never a note that it is too small.
    """


class CeilingDisagreesError(WeftError):
    """`bridges_from`'s own two independent measurements of one bridge's ceiling disagreed: the
    walk says two endpoints share no chunk, and `chunks_by_entity` says they share at least one.
    Neither number is printed — see the module docstring's paragraph on why the ceiling is
    measured twice.
    """


#: The message `no_relations_to_bridge_error` carries — `weft_kg.schema.
#: _PROPOSE_NO_FACTS_TEMPLATE`'s own tone, restated for this command's own refusal rather than
#: imported, because the two messages name two different remedies (propose a schema vs. list
#: bridges) even though the underlying cause — no relation rows — is identical.
_NO_RELATIONS_TEMPLATE: Final[str] = (
    "weft_kg has no relations to bridge: this corpus holds no kg_relations row at all. Index a "
    "corpus through a rung that names the llm-facts stage — `weft index <path> --pipeline "
    "index-with-facts` is the shipped one — and run this again. A corpus built with "
    "`index-with-cooccurrence` also produces relations, on a machine with no model configured."
)


def _ceiling_disagreement_message(source_name: str, target_name: str) -> str:
    return (
        f"weft_kg's two independent measurements of the vector ceiling for {source_name!r} and "
        f"{target_name!r} disagreed: the two-hop walk found no chunk naming both, and a second, "
        "independent query (GraphStore.chunks_by_entity) found at least one that does. Neither "
        "number is printed — one of the two queries is wrong, and printing either would be "
        "printing a measurement nothing checked."
    )


def no_relations_to_bridge_error() -> NoRelationsToBridgeError:
    """`NoRelationsToBridgeError` with the shared message — a factory rather than a bare
    constant, so `GraphBridgesCommand.run` raises a fresh exception instance each call, the same
    discipline every other error in this pack's own idiom follows.
    """
    return NoRelationsToBridgeError(_NO_RELATIONS_TEMPLATE, pack="weft-rag")


def bridges_from(
    candidates: Sequence[BridgeCandidate],
    *,
    chunks_by_entity: Mapping[str, frozenset[str]],
) -> tuple[Bridge, ...]:
    """Measure and attach the vector ceiling to every candidate, in `candidates`' own order —
    `GraphStore.two_hop_bridges` already orders deterministically, so this function reorders
    nothing.

    Raises `CeilingDisagreesError` the moment one candidate's two endpoints turn out to share a
    chunk after all — see the module docstring. `chunks_by_entity[entity_id]` is looked up
    directly rather than through `.get`: a missing key here is a caller's programming error
    (every endpoint this function is asked about came from a candidate `two_hop_bridges` itself
    produced), and `KeyError` says so rather than silently treating "not looked up" as "holds no
    chunk" (`docs/lessons.md` L5.9's distinction, applied to a mapping instead of a count).
    """
    bridges: list[Bridge] = []
    for candidate in candidates:
        source_chunks = chunks_by_entity[candidate.source_entity]
        target_chunks = chunks_by_entity[candidate.target_entity]
        both = source_chunks & target_chunks
        if both:
            raise CeilingDisagreesError(
                _ceiling_disagreement_message(candidate.source_name, candidate.target_name),
                pack="weft-rag",
            )
        either = source_chunks | target_chunks
        best_single_chunk_endpoints = max(
            (
                sum(1 for chunks in (source_chunks, target_chunks) if chunk in chunks)
                for chunk in either
            ),
            default=0,
        )
        ceiling = VectorCeiling(
            endpoints=(candidate.source_name, candidate.target_name),
            chunks_holding_both=len(both),
            chunks_holding_either=len(either),
            best_single_chunk_endpoints=best_single_chunk_endpoints,
        )
        relevant_documents = tuple(
            sorted(set(candidate.first.documents) | set(candidate.second.documents))
        )
        digest_input = "|".join(
            (candidate.source_name, candidate.via_name, candidate.target_name)
        ).encode("utf-8")
        question_id = "bridge-" + hashlib.sha256(digest_input).hexdigest()[:12]
        bridges.append(
            Bridge(
                hops=(candidate.first, candidate.second),
                endpoints=(candidate.source_name, candidate.target_name),
                via=candidate.via_name,
                ceiling=ceiling,
                question=f"How is {candidate.source_name} related to {candidate.target_name}?",
                question_id=question_id,
                relevant_documents=relevant_documents,
            )
        )
    return tuple(bridges)


def questions_as_json(bridges: Sequence[Bridge]) -> str:
    """`bridges`, as the JSON `weft eval run --questions` reads: a **list**, one `Question`-shaped
    object per bridge and nothing else — `weft_cli.eval_scoring.Question` forbids extra keys, so
    an additional field here would make the file unreadable by the very command it exists for.
    """
    payload = [
        {
            "query": bridge.question,
            "relevant_documents": list(bridge.relevant_documents),
            "kind": QUESTION_KIND,
        }
        for bridge in bridges
    ]
    return json.dumps(payload, indent=2) + "\n"


__all__ = [
    "QUESTION_KIND",
    "Bridge",
    "BridgeCandidate",
    "BridgeHop",
    "CeilingDisagreesError",
    "NoRelationsToBridgeError",
    "VectorCeiling",
    "bridges_from",
    "no_relations_to_bridge_error",
    "questions_as_json",
]
