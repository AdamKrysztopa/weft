"""The store contract family — published here, never by the kernel.

Specified in `docs/06-phase-0-build.md` step 7 and, in full, `docs/02-extension-model.md`
section 1 → *The store contract family* (settled in **G4**). Two capabilities
published at Phase 0: `NodeStore`, the base every store implements all of, and
`VectorSearch`, one of the optional capabilities a store may additionally
satisfy. **`TextSearch` joins them at Phase 2 task 2.5**, on the terms `02`
predicted — one more Protocol here, no change to either of the other two — and
for the reason Phase 0 gave for leaving it out: this is the step where a store
implementing it exists (`pgvector_store.PgVectorStore.search_text`, over a
`tsvector` column). Text search being a *store* capability rather than a
retriever's own machinery is the whole of that task: a retriever that had to
build its own index would own a second copy of the corpus, stale from the
moment it was built.

**`MetadataFilter` joins them at task 2.6, with a member rather than as the
bare marker `02` §1 specified.** That correction was measured at task 2.5: a
`@runtime_checkable` Protocol with an empty body has an empty
`__protocol_attrs__`, so `isinstance(x, MetadataFilter)` is `True` for every
object in the language, `42` included, and published that way it would be a
capability every store advertises and none has to implement. What it needed
was a member that *is* the capability — "an entry point taking a `Filter` and
nothing else" — settled against a store that actually translates the whole
`FilterOp` set, which is what 2.6 brought: `weft-qdrant` translates it to
Qdrant's own filter language, `pgvector_store` to SQL, and `matching` is the
member both of them have. The operator set's own narrowings — what a path may
name, and which operator each kind of field admits — live in
`weft_store.fields`, published once so that two engines cannot come to
disagree about what a `Filter` means.

**Capability is derived, never declared — the whole reason these are two
Protocols rather than one with optional methods.** `docs/02-extension-model.md`:
"At registration the kernel computes which protocols a store class
satisfies, and that set is its capability. Nobody writes a flag, so nobody
writes a false one." Both Protocols below are `@runtime_checkable`, which is
what makes that computation `isinstance(store, VectorSearch)` — ordinary
Python, not a mechanism this module or the kernel has to build. One class
registered once under `NodeStore` may also satisfy `VectorSearch`; nothing
here registers `VectorSearch` under its own plugin name, because it is a
capability a store has, not a plugin a pipeline selects. `__protocol_attrs__`
— the set `isinstance` actually checks on a `@runtime_checkable` Protocol —
is therefore `{'search_vector'}` for `VectorSearch`, `{'search_text'}` for
`TextSearch`, `{'matching'}` for `MetadataFilter`, and exactly `NodeStore`'s
nine method names for `NodeStore`: a class implementing only those methods
satisfies the contract, nothing more required.

**`version` is readable off each class but carries no isinstance weight.**
`typing.Protocol` computes `__protocol_attrs__` once, when a class statement
closes, by walking every attribute (and bare annotation) present in the
class's own body at that moment. A `ClassVar` declared inside `NodeStore` or
`VectorSearch` would therefore become a *required* capability member — a
store implementing every method above but never restating `version` would
fail `isinstance`, exactly the defect this module exists to avoid. Each
Protocol below instead declares `version` only under `if TYPE_CHECKING:`
(so a type checker still sees it and `Cls.version` still type-checks) and
the real value is assigned once, after the class body, where `Protocol`'s
one-time computation can no longer see it.

**One version for the family, not one per Protocol.** `docs/09-release.md`'s
own accounting lists "the store protocol family" as a single contract-version
unit, distinct from "the filter AST", which is versioned separately because
it is serialised into stored pipelines and outlives any one store: `Filter`
carries `FILTER_AST_VERSION` as its own `ClassVar` — safe to declare directly
in `Filter`'s body since `Filter` is a `BaseModel`, not a `@runtime_checkable`
Protocol, so there is no `__protocol_attrs__` for it to join. Both constants
are mechanical facts for fitness function 6 — what a version *means* is G9's,
still open, and neither constant answers that question.

**`NodeStore` declares `Stage[Sequence[Node], Sequence[Node]]` as one of its
own bases, with a `run` method `02`'s pseudocode block does not show.**
That block enumerates the capability methods — `add`, `get`,
`delete_source`, and so on — and is correct as far as it goes, but the
pipeline example in `docs/02-extension-model.md` section 3 lists `store` as
an ordinary stage (`- id: store\\n    use: pgvector`), selected by the same
`StageSpec` mechanism as `extract` or `chunk`. `weft_kernel.runner` resolves
every pipeline stage's contract through `Stage[In, Out]`, read off the
contract via `__orig_bases__` — so a contract usable in that stage position
must declare it, exactly as `weft_extract.contract.Extractor` and
`weft_chunk.contract.Chunker` do. `run` is additive to the capability
methods `02` already lists, not a replacement for `add`: a `NodeStore`
plugin's `run` is expected to call its own `add` and pass its input through,
so the runner's batch counting and `flush()` ownership keep meaning what
`docs/02-extension-model.md` says they mean for every other stage. This is a
narrowing this module's implementation surfaced, in the same spirit as the
"Narrowed in Phase 0 step N" notes already in `02` — recorded there, not
only here, so the reference document stays the one place this fact is
stated.
"""

from collections.abc import Sequence
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, NewType, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import Node, NodeId, Outcome, SourceId, Vector
from weft_kernel.runner import Stage

#: Fitness function 6's subject for the store family — see the module docstring. Moved
#: `1.0.0` → `1.1.0` at task 2.5, when `TextSearch` joined, and `1.1.0` → `1.2.0` at task 2.6,
#: when `MetadataFilter` did: the family grew a capability each time, so the constant fitness
#: function 6 watches has to move with it, and one number covers all four Protocols. **What a
#: version number *means* is G9's question and G9 is Open** — this records only that the
#: published surface changed, and nothing here should be read as having settled a
#: compatibility policy.
STORE_CONTRACT_VERSION = "1.2.0"

#: Versioned separately from `STORE_CONTRACT_VERSION`: a `Filter` is data that
#: outlives any one store, serialised into a resolved, stored pipeline. Moved `1.0.0` →
#: `1.1.0` at task 2.6, when the four ordered operators narrowed to numbers — a filter this
#: AST used to accept is now refused, which is a change to what the data *is* and not to any
#: store that reads it.
FILTER_AST_VERSION = "1.1.0"

#: An opaque pagination token. Never constructed by a caller — only ever a
#: value a store previously handed back through `Page.next_cursor`.
Cursor = NewType("Cursor", str)


class Page[T](BaseModel):
    """One page of `scan`'s results, plus the cursor to fetch the next one.

    `next_cursor` is `None` exactly when this page is the last one — never a
    sentinel a caller must know to check by value, only by presence.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[T, ...]
    next_cursor: Cursor | None = None


class Scored[T](BaseModel):
    """A value paired with a retrieval score. `docs/02-extension-model.md`: "the score lives on
    `Scored[Node]`, not on `Node`" — it is a property of one search, not of the node.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    score: float


class SourceStatus(StrEnum):
    """Where a `SourceRecord` stands. `Enum` per the project's string-constant rule."""

    ACTIVE = "active"
    DELETING = "deleting"


class SourceRecord(BaseModel):
    """One indexed document's record — `docs/02-extension-model.md`'s "last reach-through" fix.

    `status` is the tombstone `delete_source` writes before it starts
    deleting by filter: `docs/02-extension-model.md` → *Deletion is
    idempotent and resumable*, "`delete_source` writes a tombstone — a
    status on the `SourceRecord` — deletes by filter on `lineage.sources`,
    then clears it." A crash leaves `status=DELETING`, so the next call or
    `weft doctor` can finish the job rather than leaving it half-deleted and
    invisible.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: SourceId
    uri: str
    content_hash: str
    indexed_at: datetime
    pipeline: str
    status: SourceStatus = SourceStatus.ACTIVE


class Removed(BaseModel):
    """What `delete_source` returns: counts and the source deleted, never a materialised cascade.

    `docs/02-extension-model.md`: "It returns counts and affected sources
    with a cursor for ids rather than materialising a cascade that can span
    a corpus." `cursor`, when present, is where a caller resumes paging
    through the deleted node ids via `scan`-shaped calls a future step may
    add — carried here as the documented placeholder for that, not yet a
    method this contract requires any store to expose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: SourceId
    node_count: int
    cursor: Cursor | None = None


class FilterOp(StrEnum):
    """The closed operator vocabulary `docs/02-extension-model.md` names: "eq ne in lt lte gt
    gte exists contains and or not". `Enum` per the project's string-constant rule — this is
    exactly the closed-vocabulary case the rule exists for, not an open, pack-declared set.
    """

    EQ = "eq"
    NE = "ne"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EXISTS = "exists"
    CONTAINS = "contains"
    AND = "and"
    OR = "or"
    NOT = "not"


#: A leaf value a comparison operator compares a field against, or (for `in`) a tuple of them.
type FilterValue = str | int | float | bool | tuple[str | int | float | bool, ...]

_COMPARISON_OPS = frozenset(
    {
        FilterOp.EQ,
        FilterOp.NE,
        FilterOp.IN,
        FilterOp.LT,
        FilterOp.LTE,
        FilterOp.GT,
        FilterOp.GTE,
        FilterOp.CONTAINS,
    }
)
_COMBINATOR_OPS = frozenset({FilterOp.AND, FilterOp.OR})

#: The four operators that put two values in an order rather than testing them for identity.
#: Their value must be a number — see `Filter._shape_matches_op` for why that is a fact about
#: portable data rather than a limitation of any one store.
_ORDERED_OPS = frozenset({FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE})

#: The comparison operators that ask *is this value that value* rather than putting two values
#: in an order. Spelled as its own set rather than derived as `_COMPARISON_OPS - _ORDERED_OPS`,
#: because a validator that refuses something is worth being able to read the subject of.
_IDENTITY_OPS = frozenset({FilterOp.EQ, FilterOp.NE, FilterOp.IN, FilterOp.CONTAINS})


class Filter(BaseModel):
    """A serialisable Pydantic AST — `docs/02-extension-model.md` → *Filters are data*.

    One representation serves YAML and Python and makes a resolved pipeline
    diffable; `field` is a dotted path, validated at pipeline load against
    the registered `ExtModel`s (a later step's job — nothing in Phase 0
    resolves a pipeline against a store's filter capability yet). Shape is
    checked here, once, regardless of who builds a `Filter`: a comparison
    op names `field` and `value` and carries no `clauses`; `exists` names
    only `field`; `and`/`or` carry two or more `clauses` and no `field` or
    `value`; `not` carries exactly one. `contains` is a comparison op, not a
    combinator — `docs/02-extension-model.md`: "`contains` is not optional:
    cascade delete is a filter over `lineage.sources`."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Fitness function 6's subject for the filter AST — see the module docstring, *"One
    #: version for the family, not one per Protocol."* Safe as an ordinary `ClassVar` here:
    #: `Filter` is a `BaseModel`, not a `@runtime_checkable` Protocol, so there is no
    #: `__protocol_attrs__` membership for it to join, and pydantic never treats a `ClassVar`
    #: as a model field regardless of `extra="forbid"`.
    version: ClassVar[str] = FILTER_AST_VERSION

    op: FilterOp
    field: str | None = None
    value: FilterValue | None = None
    clauses: tuple["Filter", ...] = ()

    @model_validator(mode="after")
    def _shape_matches_op(self) -> "Filter":
        if self.op in _COMPARISON_OPS:
            if self.field is None or self.value is None:
                raise ValueError(f"'{self.op}' filter requires both 'field' and 'value'")
            if self.clauses:
                raise ValueError(f"'{self.op}' filter must not carry 'clauses'")
            self._ordered_comparison_is_over_numbers()
            self._identity_comparison_is_not_over_floats()
        elif self.op is FilterOp.EXISTS:
            if self.field is None:
                raise ValueError("'exists' filter requires 'field'")
            if self.value is not None or self.clauses:
                raise ValueError("'exists' filter must not carry 'value' or 'clauses'")
        elif self.op in _COMBINATOR_OPS:
            if len(self.clauses) < 2:  # noqa: PLR2004 - "at least two clauses" is the definition
                raise ValueError(f"'{self.op}' filter requires at least two 'clauses'")
            if self.field is not None or self.value is not None:
                raise ValueError(f"'{self.op}' filter must not carry 'field' or 'value'")
        else:  # FilterOp.NOT
            if len(self.clauses) != 1:
                raise ValueError("'not' filter requires exactly one clause")
            if self.field is not None or self.value is not None:
                raise ValueError("'not' filter must not carry 'field' or 'value'")
        return self

    def _ordered_comparison_is_over_numbers(self) -> None:
        """Refuse `lt`/`lte`/`gt`/`gte` against anything but a number.

        Ordering text means whatever the engine's collation means — a property
        of a database, not of the filter — and Qdrant, the second backend this
        AST was proven against at task 2.6, ranges over numbers only. A filter
        is data that must mean one thing everywhere, so this is refused where
        the filter is *built*, once, rather than differently by each store.
        `bool` is excluded explicitly: it is an `int` in Python and nowhere
        else, and `flag > 0` is not a question anybody meant to ask.
        """
        if self.op not in _ORDERED_OPS:
            return
        if isinstance(self.value, bool) or not isinstance(self.value, int | float):
            raise ValueError(
                f"'{self.op}' compares an order, so its value must be a number; got "
                f"{self.value!r}. Ordering text would mean whatever the store's collation "
                f"means, which is a fact about a database rather than about this filter"
            )

    def _identity_comparison_is_not_over_floats(self) -> None:
        """Refuse `eq`/`ne`/`in`/`contains` against a float.

        Two reasons that point the same way, and the second is what made it a
        refusal rather than an opinion. Exact equality between floating-point
        numbers is a question whose answer depends on how each end rounded, so it
        is a bad filter wherever it is asked. And a document store indexes floats
        for range comparison and not for matching, so the same filter that selects
        in SQL selects nothing there — silently. A range with equal bounds is what
        this means, and it says so.

        **Guarded by `_IDENTITY_OPS`, and that guard is the whole of a repair.** It
        used to run for every comparison operator, including the four ordered ones —
        so `gte` against `0.8` was refused by a message telling the operator to ask
        for a range with `gte`, and no filter anywhere could compare against a
        confidence, a score or a threshold. Two validators disagreeing about the same
        value is the shape of that defect: `_ordered_comparison_is_over_numbers`
        admits `int | float` two methods up, and both backends were already written
        for a float bound (`weft_qdrant.store._as_number`, pgvector's `::numeric`).
        """
        if self.op not in _IDENTITY_OPS:
            return
        values = self.value if isinstance(self.value, tuple) else (self.value,)
        if any(isinstance(value, float) for value in values):
            raise ValueError(
                f"'{self.op}' tests identity, and a floating-point number cannot be tested for "
                f"identity portably; got {self.value!r}. Ask for a range instead — 'gte' and "
                f"'lte' with the bounds you actually mean"
            )


@runtime_checkable
class NodeStore(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """The base every store implements all of — see the module docstring for `run`.

    `docs/02-extension-model.md` → *The store contract family*, verbatim for
    the eight capability methods below `run`; see that section for what each
    one is for and why (durability as a guarantee rather than a `persist()`
    call, deletion as idempotent-and-resumable rather than atomic, and the
    rest).
    """

    if TYPE_CHECKING:
        #: Readable as `NodeStore.version`, invisible to `isinstance` — see the module
        #: docstring, *"`version` is readable off each class but carries no isinstance
        #: weight."* The `if TYPE_CHECKING:` guard never executes, so nothing here reaches
        #: `__protocol_attrs__`; the real value is assigned below, after the class body.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...
    async def add(self, nodes: Sequence[Node]) -> None: ...
    async def flush(self) -> None: ...
    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]: ...
    async def delete_source(self, source_id: SourceId) -> Removed: ...
    async def scan(self, cursor: Cursor | None = None) -> Page[Node]: ...
    async def count(self) -> int: ...
    async def put_source(self, record: SourceRecord) -> None: ...
    async def get_source(self, source_id: SourceId) -> SourceRecord | None: ...
    async def list_sources(self) -> Sequence[SourceRecord]: ...


NodeStore.version = STORE_CONTRACT_VERSION


@runtime_checkable
class VectorSearch(Protocol):
    """A store that can rank `Node`s by vector similarity. Never embeds — `02`: "stores never
    embed. `VectorSearch` takes a vector, `TextSearch` takes text; a store is therefore not
    coupled to a model." Not a `Stage`: nothing in an ingest pipeline calls `search_vector`, and
    a future `Retriever` (Phase 2) resolves this capability directly against the configured
    store rather than through the runner's stage machinery.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]: ...


VectorSearch.version = STORE_CONTRACT_VERSION


@runtime_checkable
class TextSearch(Protocol):
    """A store that can rank `Node`s by lexical match on their own text.

    The sibling of `VectorSearch`, and the reason `02` insists the two are
    separate Protocols: "stores never embed. `VectorSearch` takes a vector,
    `TextSearch` takes text; a store is therefore not coupled to a model."
    A store may satisfy both, either or neither, and which it is comes out of
    `isinstance` rather than out of anything a store author writes down.

    **This is the capability a retriever asks for instead of building.** A
    lexical arm implemented inside a retrieval plugin is a second index over
    the corpus — one the store's own writes never reach, so it is stale from
    the first `add()` and there is nothing in the pipeline to make it fresh
    again. A retriever that wants a text channel therefore declares it needs
    this capability and is refused, by name, against a store that does not
    advertise it (task 2.5; `docs/02-extension-model.md` §1 → *Retrievers
    declare what they need*). Nothing here adapts or degrades: a run that
    wanted a text channel does not quietly become vector-only.

    **An empty ranking is a result, not a failure.** A store whose index holds
    nothing matching returns an empty sequence; that is the honest answer to
    "what matches these words", and it is a different fact from a store that
    could not look, which raises.

    Not a `Stage`: nothing in an ingest pipeline calls `search_text`, so it
    carries no `run` and stays a pure capability Protocol, checked with
    `isinstance` against whatever instance `NodeStore` resolved — the same
    shape as `VectorSearch`, for the same reason.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]: ...


TextSearch.version = STORE_CONTRACT_VERSION


@runtime_checkable
class MetadataFilter(Protocol):
    """A store that can evaluate a whole `Filter` against what it holds.

    The fourth tier, published at task **2.6** — one task later than `02` §1
    scheduled it, and for the reason that task exists. Specified there as a bare
    marker (`class MetadataFilter(Protocol): ...`), it could not be published as
    written: a `@runtime_checkable` Protocol with an empty body has an empty
    `__protocol_attrs__`, so `isinstance(42, MetadataFilter)` is `True` and the
    capability would be one every store advertises and none implements. It needs
    a member that *is* the capability, and `02` names the shape that member must
    have — "an entry point taking a `Filter` and nothing else".

    `matching` is that entry point. No vector, no text, no `top_k`: the filter
    alone decides membership, which is what makes this capability separable from
    the two search tiers rather than a footnote on them. `cursor` is not a second
    query dimension — it is the same paging vocabulary `NodeStore.scan` already
    uses, because a predicate over a corpus can select more of it than one answer
    should carry.

    **What a store promises by having it.** Every operator in `FilterOp`, over
    every path `weft_store.fields` says a `Filter` may name, with the meanings
    that module states — and, since a store that can evaluate a filter has no
    excuse for ignoring one, `filter` honoured on whichever of `search_vector`
    and `search_text` the same store also has. A store that translates only some
    of the operator set does not implement this Protocol and must not carry
    `matching`: half a filter language silently applied is the failure `01`
    requirement 5 exists to forbid, and refusing the whole call is the honest
    alternative.

    **Order is not promised, pages are.** `matching` and `scan` both walk
    whatever key the backend orders by — a content digest in Postgres, a UUID in
    Qdrant — and a caller that needs a ranking is asking a search capability, not
    this one.

    Not a `Stage`: nothing in an ingest pipeline filters, so it carries no `run`
    and stays a pure capability Protocol, the same shape as its two siblings.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]: ...


MetadataFilter.version = STORE_CONTRACT_VERSION
