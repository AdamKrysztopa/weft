"""`CooccurrenceGraph` — this pack's own namespaced fact: which names a node mentions, and
which of them co-occur. Ledger **11.6**.

Attaches to `Node.ext` (`weft_kernel.payload.ext.ExtModel`), never to a query-path payload's
`ext` — `docs/02-extension-model.md` §1's own "Call it only for an `ExtModel` that attaches to
`Node.ext`" rule (`docs/lessons.md` L5.20) — so `weft_kg.register` calls
`registrar.add_ext_model(CooccurrenceGraph)`. `EntityMention`/`CooccurrenceEdge` are plain,
unnamespaced value objects carried *inside* it; only the outer model needs a namespace and a
schema version.

**No field named `technique`, on any of the three models.** `weft_generate.representation.
citable_nodes` cites a single-parent node carrying an ext model with a `technique: str`
attribute *as its parent* — a field of that name here would make anything derived from these
nodes cite the chunk instead of itself. `11.7`'s fact nodes are the ones that constraint binds;
kept out of this pack's vocabulary from its very first ext model.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.payload import ExtModel


class EntityMention(BaseModel):
    """One name this pack's own co-occurrence heuristic found in a single node's content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    #: How many times this exact name occurred in the node's own content — never a corpus-wide
    #: count, which lives in the store's `kg_entities` table instead.
    count: int = Field(ge=1, default=1)


class CooccurrenceEdge(BaseModel):
    """One undirected co-occurrence: `source` and `target` were both mentioned by the same node.

    `source < target` lexicographically is this pack's own convention for a canonical
    spelling, so a pair is never stored twice under swapped endpoints —
    `weft_kg.cooccurrence.CooccurrenceGraphBuilder` is the one place that invariant is
    established.

    `predicate` is a plain `str`, deliberately not an `Enum`: `11.7` extracts an open
    vocabulary of predicates from a model, so the value space this field admits is not this
    task's to close.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    predicate: str = "co-occurs-with"
    count: int = Field(ge=1, default=1)


class CooccurrenceGraph(ExtModel):
    """This node's own entity mentions and co-occurrence edges — crude, deterministic, no model
    call.

    `__namespace__` is this distribution's own pack name, collision-free by construction
    (`docs/02-extension-model.md` §1). `__schema_version__` is G9's own second axis — a schema
    in a user's database, not a fact about which contract version this pack implements.
    """

    __namespace__ = "weft-kg"
    __schema_version__ = "1.0.0"

    entities: tuple[EntityMention, ...] = ()
    relations: tuple[CooccurrenceEdge, ...] = ()


class DropReason(Enum):
    """Why one candidate triple's endpoint or row was refused. Ledger **11.7**, extended **11.11**.

    `weft_kg.extraction`'s own line is *every dropped candidate is counted per reason, never
    summed* — so a verdict is one of these named members, never a boolean and never folded into
    one integer. `INCOMPLETE_ROW` is the fast path over a blank field, the same verdict
    `weft_kg.atomicity.non_atomic_reason` reaches on an empty name; `TOO_MANY_WORDS` through
    `DOCUMENT_REFERENCE` are that predicate's five rules, carried here as the vocabulary its
    return type names; `DUPLICATE` and `OVER_LIMIT` belong to `weft_kg.extraction` alone, because
    neither is a fact about one candidate's own shape — both are facts about the batch it arrived
    in. `OFF_SCHEMA` is `11.11`'s own addition: a candidate whose `(source_type, predicate,
    target_type)` an active curated schema (`weft_kg.schema.GraphSchema`) does not `admit` — every
    field well-shaped, the arrangement itself refused. It needs no new field on
    `ExtractionTally`: that model already counts one entry per `DropReason` with nothing summed,
    so a sixth reason is a sixth entry, not a new mechanism.
    """

    INCOMPLETE_ROW = "incomplete-row"
    TOO_MANY_WORDS = "too-many-words"
    TRAILING_STOPWORD = "trailing-stopword"
    MATHEMATICAL_NOTATION = "mathematical-notation"
    CITATION = "citation"
    DOCUMENT_REFERENCE = "document-reference"
    DUPLICATE = "duplicate"
    OVER_LIMIT = "over-limit"
    OFF_SCHEMA = "off-schema"


class DroppedCandidates(BaseModel):
    """How many candidates one run's extraction refused under one `DropReason`.

    Plain, unnamespaced — carried *inside* `ExtractionTally`, never attached to a node on its
    own, the same relationship `EntityMention`/`CooccurrenceEdge` already have to
    `CooccurrenceGraph`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: DropReason
    count: int = Field(ge=1)


class ExtractedFact(ExtModel):
    """One kept subject–predicate–object triple a model read out of a chunk. Ledger **11.7**.

    `content` on the node this rides is the embeddable rendering of the same triple
    (`f"{source} {predicate} {target}"`); this model is the machine-readable half
    `weft_kg.store.GraphStore._derive_graph_rows` reads to write `kg_entities` and
    `kg_relations` rows, so a fact whose triple lived only in `content` would be one no
    traversal could ever walk. No `technique` field — `weft_generate.representation.
    citable_nodes` cites a single-parent node carrying such a field *as its parent*, and every
    fact node this pack derives has exactly one parent (the chunk it came from), so a field of
    that name here would make it cite the chunk instead of itself.
    """

    __namespace__ = "weft-kg-fact"
    #: `S5`: `11.11` gave this model a field, which is a persisted shape gaining a field — the
    #: rule this project follows for exactly that change, restated at `schema_id`'s own comment.
    __schema_version__ = "1.1.0"

    source: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    target: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    #: The curated schema's **identity** (`weft_kg.schema.GraphSchema.identity`), never its
    #: `name`, that this fact was extracted and verified under — ledger `11.11`. Two schemas an
    #: operator called `papers` a month apart are one name and two different sets of admitted
    #: arrangements, and only the identity says which constraint this fact actually satisfied.
    #: Empty means *extracted under no schema*, which is a state `weft graph show` reports as its
    #: own group, never a missing value silently read as "whichever schema is active now".
    schema_id: str = ""


class MentionedEntity(ExtModel):
    """One distinct name a chunk's kept facts named, anchoring a node of its own. Ledger **11.7**.

    `weft_kg.extraction` derives one of these per distinct **name** a chunk's kept facts mention,
    so a name two facts in one chunk both name still anchors one node — `11.8` cascades its
    entity and alias tables from mention node ids, and a second anchor for the same name would
    give it two. Keyed on the name alone rather than on `(name, entity_type)` because
    `weft_kg.store._entity_id_for` derives an entity's id from its name and nothing else, so two
    mention nodes differing only in type would attach one entity row twice and say nothing more.

    **A name two facts of one chunk give two different types therefore keeps the first, and that
    is a deferral rather than a decision.** The disagreement is not lost — both fact nodes carry
    their own `ExtractedFact` with the type it claimed — and reconciling what one name's several
    claims amount to is `11.8`'s pass, which is the only thing in this pack that sees a name's
    whole mention set. This model records what one chunk said; it does not adjudicate.

    No `technique` field, for the identical reason
    `ExtractedFact` carries none: this node's one parent is the chunk it was named in, and that
    is the only thing a `technique`-carrying ext model would let it be cited as.
    """

    __namespace__ = "weft-kg-mention"
    __schema_version__ = "1.0.0"

    name: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)


class ExtractionTally(ExtModel):
    """Every candidate one `llm-facts` call examined, and what became of each of them.

    **The run's tally, never the chunk's** — `weft_index.payload.RaptorFacts.
    clusters_found`/`clusters_summarised` is this pack's own precedent for exactly this shape:
    a chunk whose every candidate was dropped derives no node at all, so a per-chunk tally would
    have nowhere to ride and those drops would vanish from anything a reader could find. Computed
    once, after every node in the call has been attempted, and attached unchanged to **every**
    node the call derived — a reader who finds any one fact or mention node from the run finds
    the whole run's tally beside it.

    **Two invariants, enforced at construction rather than trusted of the loop that fills them.**
    No `DropReason` may repeat across `dropped`: two entries under one reason is exactly how a
    total sneaks back into a model whose entire point is that there is no total. And
    `kept` plus every entry's `count` must equal `candidates`: that is what makes *"every dropped
    candidate is counted"* a property of the type itself rather than a claim about a loop — a
    rule added later that forgets to count a new kind of drop fails here, at construction,
    instead of shipping a tally that is quietly short.
    """

    __namespace__ = "weft-kg-extraction"
    __schema_version__ = "1.0.0"

    candidates: int = Field(ge=0)
    kept: int = Field(ge=0)
    dropped: tuple[DroppedCandidates, ...] = ()

    @model_validator(mode="after")
    def _every_candidate_is_accounted_for(self) -> "ExtractionTally":
        reasons = [entry.reason for entry in self.dropped]
        if len(reasons) != len(set(reasons)):
            raise ValueError(
                "each DropReason may appear at most once in `dropped` — a repeated reason is "
                "how a total sneaks back into a tally whose whole point is that there is none"
            )
        accounted = self.kept + sum(entry.count for entry in self.dropped)
        if accounted != self.candidates:
            raise ValueError(
                f"kept ({self.kept}) plus every dropped count ({accounted - self.kept}) must "
                f"equal candidates ({self.candidates}), got {accounted}: every dropped "
                f"candidate must be counted, with nothing left unaccounted for"
            )
        return self


__all__ = [
    "CooccurrenceEdge",
    "CooccurrenceGraph",
    "DropReason",
    "DroppedCandidates",
    "EntityMention",
    "ExtractedFact",
    "ExtractionTally",
    "MentionedEntity",
]
