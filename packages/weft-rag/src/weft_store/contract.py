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

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Annotated, ClassVar, NewType, Protocol, runtime_checkable

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from weft_kernel.context import Context, ServiceRole
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Node, NodeId, Outcome, SourceId, Vector
from weft_kernel.runner import Stage

#: Fitness function 6's subject for the store family — see the module docstring. Moved `1.0.0` →
#: `1.1.0` at task 2.5, when `TextSearch` joined, and `1.1.0` → `1.2.0` at task 2.6, when
#: `MetadataFilter` did: the family grew a capability each time, so the constant fitness function 6
#: watches has to move with it, and one number covers every Protocol here. Moved `1.2.0` → `1.3.0`
#: at task **5.1a**, when `SourceDeletable` joined, and `1.3.0` → `1.4.0` at task **5.1b**, when
#: `Reconcilable` did — a fifth and a sixth capability, on the identical footing, each a minor: a
#: capability added without breaking an existing implementation. **`1.4.0` → `2.0.0` at task 5.1c —
#: a major, not a minor, and deliberately so.** This move adds `estimate` to `Reconcilable`, an
#: existing published Protocol, rather than publishing a new one. `docs/internal/README.md`'s G9 row
#: states the rule this constant now demonstrates: semver is classified for **two audiences**, and
#: the bump is the maximum of the two — adding a method is minor for a caller (every existing call
#: site still compiles) and **major for an implementer** (`PgVectorStore`,
#: `weft_qdrant.store.QdrantStore` and every out-of-tree `Reconcilable`, whoever wrote it, stop
#: satisfying the Protocol at all until they add the method). `COMMAND_CONTRACT_VERSION`'s own
#: mis-recorded 1.1.0, corrected to 2.0.0 in the same session, is the worked example this constant
#: now repeats honestly the first time, rather than under-recording it as G9's own note warns
#: against. **`2.1.0` → `2.2.0` at task 9.17 — a minor, for the same reason.** `SourceRecord` gains
#: `pipeline_identity`, an optional field defaulting to the empty string, so every writer of a
#: `SourceRecord` keeps satisfying the family untouched and every reader that ignores it is
#: unaffected. G9's table again: an added optional field on a returned model is minor for the caller
#: and minor for the implementer. **`2.0.0` → `2.1.0` at task 9.3 — a minor.** `Removed` gains
#: `removed`, an optional field defaulting to an empty mapping, so every participant already
#: returning a `Removed` keeps satisfying the family untouched. G9's two-audience table classifies
#: this minor for both sides: minor for a caller (an existing field, `node_count`, is untouched, so
#: nothing that reads a `Removed` breaks) and minor for an implementer (nothing that already builds
#: a `Removed` is asked for a new required value). **`2.2.0` → `2.3.0` at task 10.24 — a minor, and
#: it was nearly a major.** The family gains `NodeSupersedable`, a *new* one-member Protocol.
#: Nothing that already satisfies any member of this family is asked for anything, so it is minor
#: for an implementer and minor for a caller. `supersede` was first written onto `NodeStore` itself,
#: which by `09`'s table ("Add a method to a Protocol" — minor for a caller, **major** for an
#: implementer) would have forced `2.2.0` → `3.0.0` and, through fitness function 6's binding, a
#: major of `weft-rag` itself. The dispatched implementer declined to make that bump unilaterally
#: and recorded the cascade, which is what sent the design back to this family's own rule —
#: `SourceDeletable`'s *"a separate Protocol... exactly the optional-method design this family
#: exists to refuse"*. The correct shape and the cheap version turn out to be the same answer.
#: **`2.3.0` → `2.4.0` at task 11.9 — a minor, on the identical footing as 9.3 and 9.17.**
#: `ReconcileReport` gains `abstained`, an optional integer defaulting to `0`. G9's two-audience
#: table classifies this minor for the caller (every existing field is untouched, so nothing that
#: reads a report breaks) and minor for the implementer (nothing that already builds a report is
#: asked for a new value) — the maximum of two minors is a minor.
STORE_CONTRACT_VERSION = "2.4.0"

#: Versioned separately from `STORE_CONTRACT_VERSION`: a `Filter` is data that
#: outlives any one store, serialised into a resolved, stored pipeline. Moved `1.0.0` →
#: `1.1.0` at task 2.6, when the four ordered operators narrowed to numbers — a filter this
#: AST used to accept is now refused, which is a change to what the data *is* and not to any
#: store that reads it.
FILTER_AST_VERSION = "1.1.0"

#: The schema version `ReconcileReport` carries **in the data**, per G9 (2026-08-21) — see
#: `ReconcileReport`'s own docstring for why it is a serialised field and not a `ClassVar`.
#: Versioned separately from `STORE_CONTRACT_VERSION` for the same reason `FILTER_AST_VERSION`
#: is: a report a pack persisted outlives the contract version of whatever is installed when
#: it is read back, and the contract version is not available at the read site at all.
#:
#: Moved `1.0.0` → `1.1.0` at task 11.9, when `ReconcileReport` gained `abstained`: this
#: constant tracks the *persisted shape*, not the family's Protocol surface, so a field
#: added to what gets written to disk moves this number even though it left
#: `STORE_CONTRACT_VERSION`'s reasoning (a minor, either way) alone. Fitness function 6
#: deliberately does not bind `*_SCHEMA_VERSION` constants to any distribution version —
#: `tests/architecture/test_ff6_contract_version_binding.py` says why — so this move
#: publishes nothing there.
RECONCILE_REPORT_SCHEMA_VERSION = "1.1.0"

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
    #: A digest of what the pipeline actually **ran** — `weft_kernel.resolution.pipeline_identity`,
    #: ledger task 9.17. `pipeline` above is the document's *name*, and a name does not move when
    #: the plugin behind a stage does: swapping `pdf-text` for `pdf-layout` inside `index-text`, or
    #: changing an embedder's `with: model:`, leaves it reading `index-text` while the corpus was
    #: built two different ways.
    #:
    #: **Defaults empty, and empty means "not compared", never "unchanged".** Every record already
    #: on disk was written before this field existed, so an empty value is the absence of evidence
    #: rather than evidence of sameness — `weft_cli.ingest.changes_against_records` reports a
    #: reparse for one, because claiming `UNCHANGED` there would claim a comparison nobody made.
    pipeline_identity: str = ""
    status: SourceStatus = SourceStatus.ACTIVE


def _freeze_removed(value: Mapping[str, int]) -> Mapping[str, int]:
    """Wrap a validated `removed` mapping in an immutable view.

    The identical mechanism `weft_kernel.payload.ext._freeze` uses for
    `Node.ext` (`packages/weft-kernel/src/weft_kernel/payload/ext.py:120-129 'def _freeze'`), copied
    rather
    than imported because it is a private name of another distribution's module, not a
    published one — this module owns its own small equivalent instead.
    """
    return MappingProxyType(dict(value))


#: A frozen, JSON-round-tripping mapping of kind name to count — `Removed.removed`'s type,
#: not just its default. `MappingProxyType` has no serializer pydantic-core knows on its own
#: (the same gap `weft_kernel.payload.ext.ExtMap` closes for `Node.ext`), so the
#: `PlainSerializer` below dumps it back to a plain `dict` rather than leaving
#: `model_dump(mode="json")` to raise.
RemovedByKind = Annotated[
    Mapping[str, int],
    AfterValidator(_freeze_removed),
    PlainSerializer(dict, return_type=dict),
]


class Removed(BaseModel):
    """What `delete_source` returns: counts and the source deleted, never a materialised cascade.

    `docs/02-extension-model.md`: "It returns counts and affected sources
    with a cursor for ids rather than materialising a cascade that can span
    a corpus." `cursor`, when present, is where a caller resumes paging
    through the deleted node ids via `scan`-shaped calls a future step may
    add — carried here as the documented placeholder for that, not yet a
    method this contract requires any store to expose.

    **`removed` (task 9.3) is an open, participant-owned vocabulary, not a closed one the
    contract enumerates.** `node_count` already existed when `SourceDeletable` was still
    node-store-shaped; G7 then widened the fan-out to every plugin satisfying it, and a
    participant that removes something other than a node — a blob store, a graph pack — had
    no way to say what it actually did, reporting `node_count=0` and nothing else. `removed`
    is that vocabulary: each participant names its own kinds (`"blob"`, `"entity"`,
    `"relation"`, ...), so the contract does not have to know them in advance and a pack
    nobody has written yet can still report honestly. `Enum` is the project's rule for a
    *closed* vocabulary the kernel or a contract owns; this one is neither, which is why it
    is a `Mapping[str, int]` rather than a `StrEnum`-keyed one.

    **`"node"` is the one reserved key.** `node_count` already carries that number, so a
    second spelling of it inside `removed` is the exact two-lists-that-can-drift shape
    `docs/internal/README.md` opens with, reproduced inside a single model — refused at validation
    rather than left to drift silently.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: SourceId
    node_count: int
    cursor: Cursor | None = None
    removed: RemovedByKind = Field(default_factory=dict, validate_default=True)

    @model_validator(mode="after")
    def _reject_reserved_node_key(self) -> "Removed":
        if "node" in self.removed:
            raise ValueError(
                "'removed' must not carry the key 'node' — that count already lives in "
                "'node_count'; report every other kind under its own name"
            )
        return self


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


class UnhandledFilterOpError(WeftError, UnresolvedNameError):
    """A `FilterOp` member no dispatch at this site has been taught to translate.

    `docs/09-release.md` §2.3: *"A version bump does not fix silence, so silence is a
    separate defect."* Adding a member to `FilterOp` is textbook-additive everywhere it is
    *declared* — the field still validates, `weft_store.fields` may still admit it — but a
    dispatch that branches on the operator's identity has no branch for a member it predates,
    and requirement 5 forbids answering under whichever branch it happens to fall through to.
    Every dispatch over `FilterOp` in this tree (`Filter._shape_matches_op` here,
    `weft_store.pgvector_store`'s SQL translator, `weft_qdrant.store`'s Qdrant translator)
    raises this rather than defaulting, so a 13th member is a refusal everywhere until a
    person teaches every site about it, never a silent answer at some of them and a refusal
    at others. `valid_options` names the operators *this site* translates, never the whole
    enum — the raise is "you added a member and this translator does not know it yet", not
    "you spelled an operator wrong", so the options are what the reader would have to extend
    rather than what they could have typed instead. Fitness function 13
    (`docs/01-high-level-plan.md`) is what proves every site actually raises this rather than
    only being documented to.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], pack: str) -> None:
        super().__init__(message, pack=pack)
        self.valid_options = valid_options


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
        """Refuse a `Filter` whose `field`/`value`/`clauses` do not match what `op` needs.

        **`match`/`case _: raise`, not `if`/`elif`/`else` — task 5.2b.** This validator used
        to end `else:  # FilterOp.NOT`, which is the exact defect
        `docs/09-release.md` §2.3 names: a 13th `FilterOp` member would fall into that
        `else` and be *silently validated as if it were `not`*, accepted with the shape
        `not` happens to require (exactly one clause, no `field` or `value`) rather than
        refused for being a member this validator has never seen. A `match` whose final arm
        is `case _: raise UnhandledFilterOpError(...)` cannot do that: every branch above it
        names the operators it actually covers, and anything left over is refused by
        construction rather than by whichever arm happens to run last.
        """
        match self.op:
            case op if op in _COMPARISON_OPS:
                self._comparison_shape_is_valid()
            case FilterOp.EXISTS:
                self._exists_shape_is_valid()
            case op if op in _COMBINATOR_OPS:
                self._combinator_shape_is_valid()
            case FilterOp.NOT:
                self._not_shape_is_valid()
            case _:
                self._raise_unhandled_op()
        return self

    def _comparison_shape_is_valid(self) -> None:
        """A comparison op names `field` and `value` and carries no `clauses`."""
        if self.field is None or self.value is None:
            raise ValueError(f"'{self.op}' filter requires both 'field' and 'value'")
        if self.clauses:
            raise ValueError(f"'{self.op}' filter must not carry 'clauses'")
        self._ordered_comparison_is_over_numbers()
        self._identity_comparison_is_not_over_floats()

    def _exists_shape_is_valid(self) -> None:
        """`exists` names only `field` and carries no `value` or `clauses`."""
        if self.field is None:
            raise ValueError("'exists' filter requires 'field'")
        if self.value is not None or self.clauses:
            raise ValueError("'exists' filter must not carry 'value' or 'clauses'")

    def _combinator_shape_is_valid(self) -> None:
        """`and`/`or` carry two or more `clauses` and no `field` or `value`."""
        if len(self.clauses) < 2:  # noqa: PLR2004 - "at least two clauses" is the definition
            raise ValueError(f"'{self.op}' filter requires at least two 'clauses'")
        if self.field is not None or self.value is not None:
            raise ValueError(f"'{self.op}' filter must not carry 'field' or 'value'")

    def _not_shape_is_valid(self) -> None:
        """`not` carries exactly one clause and no `field` or `value`."""
        if len(self.clauses) != 1:
            raise ValueError("'not' filter requires exactly one clause")
        if self.field is not None or self.value is not None:
            raise ValueError("'not' filter must not carry 'field' or 'value'")

    def _raise_unhandled_op(self) -> None:
        """The `case _:` arm of `_shape_matches_op` — see that method's own docstring."""
        known = sorted(
            member.value
            for member in (*_COMPARISON_OPS, FilterOp.EXISTS, *_COMBINATOR_OPS, FilterOp.NOT)
        )
        raise UnhandledFilterOpError(
            f"'{self.op}' is a FilterOp this validator has no shape rule for. Every "
            f"operator must have one, named here rather than assumed — the operators it "
            f"knows are: {', '.join(known)}.",
            valid_options=tuple(known),
            pack="weft-store",
        )

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


class SupersedeNarrowsSourcesError(WeftError):
    """`new` covers fewer sources than the `old` node `NodeStore.supersede` was asked to replace.

    A constraint violation, not a name failing to resolve against an enumerable set —
    this does **not** join `UnresolvedNameError`'s family (fitness function 12), unlike
    `UnhandledFilterOpError` below: an operator *is* a name a dispatch either knows or
    does not, while a narrowed source set is a relationship between two nodes that no
    list of "valid options" describes.

    **What this refuses, and why refusing first is the whole of it.** `supersede`
    writes `new` before it deletes `old`, so a crash between the two leaves a
    *duplicate* — one `reconcile` can find — rather than a *hole*, which nothing can.
    That ordering protects against a crash; it does nothing about a caller that hands
    over a replacement covering fewer sources than the node it replaces, which would
    remove the last node carrying a source while that source's own documents remain —
    `docs/04-*`'s category A scar, approached from the caller's end rather than a
    crash's. `Node.combine` already refuses an empty member set by construction for
    the identical reason; this is that same refusal one level up, checked and raised
    *before* either write happens, so a refused `supersede` changes nothing at all.

    The message names the superseded node and every source that would be dropped —
    see `manual/troubleshooting.md`'s own entry for the wording a reader meets.
    """


@runtime_checkable
class NodeStore(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """The base every store implements all of — see the module docstring for `run`.

    `docs/02-extension-model.md` → *The store contract family*, verbatim for
    the eight capability methods below `run`; see that section for what each
    one is for and why (durability as a guarantee rather than a `persist()`
    call, deletion as idempotent-and-resumable rather than atomic, and the
    rest).

    **`supersede` is deliberately *not* here — see `NodeSupersedable`, ledger task
    10.24.** It was written onto this Protocol first, and that broke this family's own
    stated rule: `SourceDeletable`'s docstring calls a separate Protocol *"exactly the
    optional-method design this family exists to refuse"*, and `MetadataFilter` was
    corrected into the same shape at task 2.6. Growing this base would also have made
    every third-party store owe a method to keep satisfying it — a **major** by `09`'s
    table — to gain a capability most of them will never offer.
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

#: Ledger task **9.0** — `weft_store`'s own declaration that `[services].store` selects a
#: `NodeStore`. A plain module-level constant beside the Protocol, never a `ClassVar` on
#: `NodeStore` itself — see `weft_embed.contract.EMBED_ROLE`'s identical note, and
#: `weft_extract.contract` (`:44-56`) for the `__protocol_attrs__` reasoning in full.
STORE_ROLE = ServiceRole(key="store", contract=NodeStore)


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


@runtime_checkable
class NodeSupersedable(Protocol):
    """A store that can replace one node with another — ledger task **10.24**, G15's *Remove*.

    **One member, and that member *is* the capability**, which is this family's own rule:
    `SourceDeletable` states it (*"A separate Protocol rather than a reuse of `NodeStore`,
    deliberately... exactly the optional-method design this family exists to refuse"*) and
    `MetadataFilter` was corrected into it at task 2.6. This began as a method on `NodeStore`
    and was moved here before it shipped — growing the base would have obliged every
    third-party store to implement supersession to keep satisfying it, a **major** under
    `09`'s table, for a capability most stores will never offer. Both shipped backends satisfy
    this structurally and declare nothing, so `adrap` asks the store it was handed and refuses
    by name when the answer is no.

    **Why it exists.** `delete_source` is keyed on a *source*, and a summary's relationship to
    a source is many-to-many — `Lineage.sources` is the union of its members' — so *"this node
    is out of date"* had no expression at all and an incremental tree could not replace what it
    superseded.

    **Write `new` first, delete `old` second, and that ordering is the contract.** An
    interruption then leaves a **duplicate**, which `reconcile` can find, and never a **hole**,
    which nothing can and which `04` category A records as staying retrievable forever
    describing content that is gone. No atomicity is promised: Qdrant has no cross-operation
    transaction, and a guarantee only one backend could keep is worse than the honest one —
    `weft_qdrant.delete_source` already works exactly this way and calls itself *"`02`'s
    idempotent, resumable deletion"*.

    **Idempotent**, so the retry that ordering makes safe is also possible: `old` already
    absent is not an error. **Refuses first**, changing nothing, when `new.lineage.sources`
    does not cover every source `old` carries — see `SupersedeNarrowsSourcesError`.
    Superseding a node with itself is a no-op that must not delete it.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: so the attribute is readable off the class and never reaches
        #: `__protocol_attrs__`, where `isinstance` would demand it of every implementer.
        version: ClassVar[str]

    async def supersede(self, old: NodeId, new: Node) -> None: ...


#: The same assignment its six siblings carry — a published capability of this family,
#: versioned with it. `NodeStore.version`'s own note explains why this is set after the class
#: body rather than inside it: an attribute in the body reaches `__protocol_attrs__` and
#: `isinstance` would then demand it of every implementer.
NodeSupersedable.version = STORE_CONTRACT_VERSION


@runtime_checkable
class SourceDeletable(Protocol):
    """Anything holding data that a source's deletion must reach — G7 (2026-08-21).

    The fifth capability in this family, and the only one whose implementors
    are not expected to be stores. `docs/02-extension-model.md` §1 →
    *Extended by G7*: `delete_source` sat on `NodeStore` from G4 and nothing
    in the tree called it, while a pack holding entities derived from nodes
    would never hear that those nodes were gone. That is exactly the RAPTOR
    scar — summaries no deletion path can reach — reappearing first-party.

    **A separate Protocol rather than a reuse of `NodeStore`, deliberately.**
    A graph store is not a node store: asked to implement `NodeStore` it would
    owe `scan`, `count` and the three source methods to answer one question
    about deletion, which is exactly the optional-method design this family
    exists to refuse. One member, and that member *is* the capability — the
    same rule `MetadataFilter` was corrected into at task 2.6.

    **`NodeStore` satisfies this by construction and that is the point.**
    `delete_source` is already one of `NodeStore`'s own methods, so every store
    in this family is a participant with nothing added and nothing declared —
    capability derived, never declared, which is what makes a fan-out over
    "everything satisfying `SourceDeletable`" find the node store without
    naming it.

    **What an implementor promises.** Deletion is idempotent and resumable:
    deleting a source that is already gone is a legitimate no-op returning
    `node_count=0`, never an error, because a fan-out re-run after a partial
    failure must be able to finish the job. What it must *not* do is report
    success it did not achieve — `weft delete` names a participant that raises,
    and a participant that swallows its own failure makes that promise
    unkeepable.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def delete_source(self, source_id: SourceId) -> Removed: ...


SourceDeletable.version = STORE_CONTRACT_VERSION


class ReconcileMode(StrEnum):
    """What a reconciliation pass is allowed to do — G7's consent boundary, task **5.1b**.

    `docs/02-extension-model.md` §1: "`repair` removes derived state whose source is gone;
    `full` also **backfills** state that was never built." Two members and no third, because
    the distinction being drawn is not a degree of thoroughness but a question of consent:
    backfill runs model calls and writes, so an *ambient* backfill would silently change what
    an existing pipeline does by a second route — G3's installed-and-ambient threat wearing a
    different coat. Which mode a caller may reach, and when, is `03`'s and task 5.1c's;
    nothing here decides it.
    """

    REPAIR = "repair"
    FULL = "full"


class ReconcileReport(BaseModel):
    """What one participant's reconciliation pass did, and whether it finished.

    **`schema_version` is a serialised field, not a `ClassVar`, and that is the whole of
    G9's ruling applied here.** `docs/02-extension-model.md` §1 → *A schema version is
    carried in the data*: a report is persisted by any pack that records what it repaired,
    and at the read site the pack that wrote it may not be installed — so a version read off
    an importing module would be exactly whatever is installed and could never disagree with
    it. `Filter.version` is the worked example of getting this wrong: pydantic never
    serialises a `ClassVar`, so a filter stored inside a pipeline has always carried no
    version at all. This one is in the bytes.

    **`remaining` is what makes a pass resumable rather than atomic.** `reconcile` is
    `O(corpus)` and interruptible — `CancelledError` propagates per G6 — so a pass that was
    cut short returns what it managed, and the work it did not do is still *there*, in
    whatever durable form the participant reads its own backlog from. `remaining == 0` means
    converged; anything else means run it again, and running it again is safe because
    `reconcile` is idempotent.

    **`abstained`, task 11.9, is a fifth number because it is none of the other four.** It is
    not `backfilled` — nothing was written for the pair in question. It is not `removed` —
    nothing went. And it is emphatically not `remaining`: `remaining` means *resumable* — run
    the pass again over the same corpus and it converges — while an abstention means the pass
    reached the end of its adjudication chain and returned with no opinion, so running it
    again asks the same question of the same evidence and gets the same silence. Folding an
    abstention into `remaining` would make `converged` permanently `False` on any corpus
    holding a single genuinely ambiguous pair, forever asking to be re-run for work that will
    never resolve. It exists at all because the alternative is silent: a participant that
    spent a model call on a pair and reached no decision, reported as a clean `backfilled 0`,
    is indistinguishable from a corpus with nothing ambiguous in it at all — exactly the
    plausible-looking wrong answer requirement 5 exists to forbid.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = RECONCILE_REPORT_SCHEMA_VERSION
    mode: ReconcileMode
    examined: int = 0
    removed: int = 0
    backfilled: int = 0
    remaining: int = 0
    #: A pair asked about and left undecided — see the class docstring's paragraph above for
    #: why this is not folded into `backfilled`, `removed` or `remaining`. Defaults to `0`, the
    #: value every `Reconcilable` already shipping keeps returning, which is what makes this
    #: field's addition minor for an implementer rather than major.
    abstained: int = 0

    @property
    def converged(self) -> bool:
        """Whether this pass finished the job — see `remaining`'s note above."""
        return self.remaining == 0


class ReconcileEstimate(BaseModel):
    """What converging would cost, asked *before* anything is spent — task **5.1c**.

    `docs/03-cli.md` -> *Command surface*: "`full` states its cost before it spends it" —
    `weft-kg: 4,312 nodes have no graph data / backfill will make ~4,312 model calls" is
    the worked example. A caller cannot be told that without asking the participant itself —
    `list_sources`/`scan`/`count` answer *what should exist*, never *what converging one of
    them would cost* — so this is the shape `Reconcilable.estimate` returns.

    **Shape, settled against the worked example.** `mode` is the mode being asked about, since
    the honest answer to "what would converging cost" depends on it — `repair` never backfills,
    so its own honest `model_calls` is always `0`. `pending` is the count the participant's own
    prose in `description` is about — `docs/03-cli.md`'s own example counts nodes; a node
    store's own `reconcile` doctring narrows that to its outstanding tombstones, and `estimate`
    reports the identical count `reconcile` would examine, never a second, disagreeing figure.
    `description` is deliberately a bare `str`, not a structured breakdown: `03`'s own example
    output is one pack's own prose about its own outstanding work ("nodes have no graph data"),
    and a fixed shape here would either constrain every future `Reconcilable` to one kind of
    "pending" (nodes? sources? entities?) or force a lossy translation into one. `model_calls`
    defaults to `0` — honest for every `Reconcilable` this tree ships today, since a node store
    holds the primary data and has no derived state to backfill (see `PgVectorStore.reconcile`'s
    own docstring, which owns that argument for both first-party backends) — and is the one
    field `docs/03-cli.md`'s own example is actually about naming a real number for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ReconcileMode
    pending: int = 0
    description: str
    model_calls: int = 0


@runtime_checkable
class Reconcilable(Protocol):
    """Anything whose state can be made to agree with what the corpus actually holds — G7.

    The sixth capability in this family, and `docs/02-extension-model.md` §1 → *Extended by
    G7* calls it "the safety net, and it is why there is no bus": a bus reaches only
    subscribers live when the event fired, so it cannot repair a pack installed *after* the
    corpus was built, a drain killed mid-flight, or a second machine sharing one database.
    Convergence can, and it needs nothing new to ask its question — `list_sources`, `scan`
    and `count` already answer *what should exist*.

    **What an implementor promises.** Idempotent, so a second pass over a converged store is
    a legitimate no-op. `O(corpus)` and cursored, so it is bounded by what is stored rather
    than by what changed. Interruptible, with `CancelledError` propagating untouched — and,
    the clause that gives that meaning, **resumable**: whatever a cancelled pass did not
    finish must still be discoverable on the next pass, from durable state, never from a
    cursor that died with the process.

    **`estimate`, task 5.1c, added rather than left optional.** `docs/02-extension-model.md`
    §3 → *Slots*: "backfill is reached only by a person's per-run flag" — and `03`'s own text
    adds that the person is told the cost first, in real numbers, not asked to trust a flag
    blindly. A pack that can converge can say what converging would cost, and CLAUDE.md's own
    "cross-cutting concerns live at the registration seam, never in a rule authors must
    remember" is exactly why this is a second required member rather than an optional
    duck-typed method the way `describe_impact` is for `weft_command.contract.Command`:
    `describe_impact`'s own absence is silently fine because nothing there is mandatory for
    every command, while a `Reconcilable` that could not say its own cost would make `03`'s
    promise one whose truth depends on which packs happened to remember. **This is why
    `STORE_CONTRACT_VERSION` moves `1.4.0` → `2.0.0`** rather than to `1.5.0` — see that
    constant's own comment for G9's two-audience rule.
    """

    if TYPE_CHECKING:
        #: See `NodeStore.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport: ...

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate: ...


Reconcilable.version = STORE_CONTRACT_VERSION
