"""What a `Filter.field` may name, and which operator each kind of field admits.

`docs/02-extension-model.md` → *Filters are data*: "`field` is a dotted path".
Phase 0 wrote that down and no store translated it, so the path had no meaning
beyond the sentence. Task **2.6** is where it acquires one, and the reason it
acquires it *here* rather than inside a store is the task itself: a `Filter` is
data, serialised into a resolved pipeline, and data that means one thing to
Postgres and another to Qdrant is not data. One parse, one operator table, two
translators that start from the same answer.

**The vocabulary is `Node`'s own shape, not a table someone maintains.** A path
is what you would write to reach the value on a `Node`: `id`, `content`,
`media_type`, `lineage.parents`, `lineage.sources`, and `ext.<namespace>.<field>`
for anything a pack attached. There is nothing to look up and nothing to keep in
sync, which is the only way a field vocabulary stays true — the alternative, a
registry of blessed field names, drifts from the payload model the first time
someone adds a field.

**Where the operator set narrows, a second backend is why.** Three refusals
below exist because two engines had to agree, and each one is a place the
contract was over-fitted to SQL until something else had to satisfy it:

* **Ordered comparison is for numbers, and only on extension data.** Qdrant
  ranges over numbers and datetimes; Postgres will happily order text, by a
  collation that is a property of the database rather than of the filter. A
  `Filter` whose meaning depends on `LC_COLLATE` is not portable data, so
  `lt`/`lte`/`gt`/`gte` take a number (refused on `Filter` itself, see
  `contract.Filter`) and name an `ext.` path (refused here).
* **`eq` on a set is refused, naming `contains`.** Qdrant matches a payload
  array element-wise, so `eq` against `lineage.sources` would silently mean
  membership there and equality-of-the-whole-list in SQL. One spelling, two
  meanings, no error — exactly the class of defect `01` requirement 5 forbids.
* **`contains` on a text scalar is refused.** It reads as substring matching,
  which is `TextSearch`'s job and is not something every store can rank; a
  filter is a predicate over stored values, not a second search engine.

**An extension value that is an array is compared element-wise.** `ext.weft-pdf.
starts > 100` is true of a node with a page starting after character 100, not of
a node whose whole list somehow exceeds 100. That is Qdrant's native payload
semantics and it is the only rule under which a single scalar and a one-element
array answer the same question, so `weft_store.pgvector_store` implements it too
rather than the other way round.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_store.contract import Filter, FilterOp

#: The prefix that separates a pack's namespaced extension data from the six core fields.
#: `Node.ext` is literally the attribute, so the path is literally the attribute path.
EXT_PREFIX = "ext"


class NodeField(StrEnum):
    """Every core field of a `Node` a filter can address, spelled as the path that reaches it.

    Five, not six: `embedding` is deliberately absent. A vector is what
    `VectorSearch` ranks by, not a value a predicate compares — `embedding > 0.5`
    has no meaning, and no store this contract is proven against can answer it.
    """

    ID = "id"
    CONTENT = "content"
    MEDIA_TYPE = "media_type"
    PARENTS = "lineage.parents"
    SOURCES = "lineage.sources"


class FieldKind(StrEnum):
    """What sort of value a path reaches, which is what decides the operators it admits."""

    #: A string on the node itself — `id`, `content`, `media_type`.
    TEXT = "text"
    #: A set of strings on the node itself — `lineage.parents`, `lineage.sources`.
    TEXT_SET = "text-set"
    #: Whatever a pack put under its namespace: a string, a number, a bool, or an array
    #: of them. Its type is not knowable here, which is why the operator table below is
    #: permissive for this kind and the store's own translation carries the type check.
    EXTENSION = "extension"


class FieldPath(BaseModel):
    """A parsed `Filter.field`: which kind of value it reaches, and how to reach it.

    Frozen, like every domain object in this tree, and deliberately not a bare
    tuple of strings: a translator that received `("ext", "weft-pdf", "starts")`
    would have to re-derive what kind of field that is at every call site, and
    two translators re-deriving it is how they come to disagree.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: FieldKind
    #: The core field this path names, or `None` for an extension path.
    core: NodeField | None = None
    #: The distribution that owns the extension data, or `""` for a core path.
    namespace: str = ""
    #: The keys inside that namespace's model, outermost first. Empty addresses the
    #: namespace's whole value, which `exists` is the honest use of.
    keys: tuple[str, ...] = ()


class UnaddressableFieldError(WeftError, UnresolvedNameError):
    """A `Filter` names a path that reaches nothing on a `Node`.

    `01` requirement 5 applied to a filter an operator wrote: refused before any
    query runs, naming the path and every core field, rather than translated into
    a predicate that quietly matches nothing. A filter matching nothing looks
    exactly like a corpus that holds nothing, and the difference is the whole
    question the operator was asking.

    Fitness function 12's family: `valid_options` is every core field a path can
    name. Extension fields are open-ended (`ext.<namespace>.<field>`, per-pack), so
    they cannot be enumerated the same way — the message states the pattern instead,
    which `valid_options` cannot represent as a closed list without inventing one.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], pack: str) -> None:
        super().__init__(message, pack=pack)
        self.valid_options = valid_options


class FilterOpMismatchError(WeftError):
    """A `Filter` applies an operator to a field that cannot carry it.

    Every case is one where two backends would otherwise answer differently or
    where the operator has no meaning at all — see this module's docstring for
    the three, and why a second backend is what surfaced them.
    """


_SET_FIELDS = frozenset({NodeField.PARENTS, NodeField.SOURCES})

_DESCRIPTION: dict[FieldKind, str] = {
    FieldKind.TEXT: "one string",
    FieldKind.TEXT_SET: "a set of strings",
    FieldKind.EXTENSION: "a value a pack attached",
}

_ORDERED_REMEDY = (
    "ordered comparison is defined for numbers under a pack's namespace only: on text it "
    "would mean whatever the database's collation means, which is not a fact about the filter"
)

#: Which operators each kind of field admits. A comparison the table refuses is one whose
#: meaning would depend on the engine rather than on the filter.
#:
#: **`EXTENSION`'s set is stated by hand, not derived — task 5.2b.** It used to read
#: `frozenset(FilterOp) - {AND, OR, NOT}`, which is `docs/lessons.md` L5.6's shape one level
#: up from a version constant: a permitted set computed from the very enum it is supposed to
#: gate does not narrow as the vocabulary grows, it *widens*, admitting whatever `FilterOp`
#: gains next with nobody having decided that member belongs on a pack's own namespaced data.
#: Named here instead, the nine members below are exactly what `frozenset(FilterOp) -
#: {AND, OR, NOT}` evaluates to against today's twelve — no behaviour changes for any
#: operator that exists now — but a 13th lands in none of the three sets below until a
#: person adds it, refused by `field_for`'s existing `FilterOpMismatchError` rather than
#: admitted by construction. Proven by
#: `tests/architecture/test_ff13_filter_op_dispatch_is_exhaustive.py`, which manufactures a
#: `FilterOp`-shaped value this table has never seen and asserts every `FieldKind` refuses
#: it, `EXTENSION` included.
_ADMITTED: dict[FieldKind, frozenset[FilterOp]] = {
    FieldKind.TEXT: frozenset({FilterOp.EQ, FilterOp.NE, FilterOp.IN, FilterOp.EXISTS}),
    FieldKind.TEXT_SET: frozenset({FilterOp.IN, FilterOp.EXISTS, FilterOp.CONTAINS}),
    FieldKind.EXTENSION: frozenset(
        {
            FilterOp.EQ,
            FilterOp.NE,
            FilterOp.IN,
            FilterOp.LT,
            FilterOp.LTE,
            FilterOp.GT,
            FilterOp.GTE,
            FilterOp.EXISTS,
            FilterOp.CONTAINS,
        }
    ),
}

#: Why each refusal exists, in the words the operator needs rather than the ones this module
#: thinks in. Keyed by the operator, because in every case the operator is what has to change.
_REMEDY: dict[FilterOp, str] = {
    FilterOp.EQ: "use 'contains', which asks whether the value is one of the set's members",
    FilterOp.NE: "use 'not' wrapping 'contains', which asks whether the value is absent from it",
    FilterOp.CONTAINS: (
        "'contains' asks about membership of a set, not about a substring of a string — "
        "substring matching is what TextSearch ranks, and no filter can rank"
    ),
    FilterOp.LT: _ORDERED_REMEDY,
    FilterOp.LTE: _ORDERED_REMEDY,
    FilterOp.GT: _ORDERED_REMEDY,
    FilterOp.GTE: _ORDERED_REMEDY,
}


def parse_field_path(field: str) -> FieldPath:
    """The path `field` names, or `UnaddressableFieldError` naming what it could have named.

    Raises rather than returning `None`: every caller is translating a filter it
    is about to run, and a path that reaches nothing has no honest translation —
    a predicate that matches nothing is indistinguishable from an empty corpus.
    """
    for core in NodeField:
        if field == core.value:
            kind = FieldKind.TEXT_SET if core in _SET_FIELDS else FieldKind.TEXT
            return FieldPath(kind=kind, core=core)
    segments = tuple(part for part in field.split(".") if part)
    if len(segments) >= 2 and segments[0] == EXT_PREFIX:  # noqa: PLR2004 - "ext" plus a namespace
        return FieldPath(kind=FieldKind.EXTENSION, namespace=segments[1], keys=segments[2:])
    options = tuple(sorted(member.value for member in NodeField))
    core_names = ", ".join(options)
    raise UnaddressableFieldError(
        f"filter field '{field}' reaches nothing on a Node. The core fields are: {core_names}. "
        f"Anything a pack attached is under '{EXT_PREFIX}.<namespace>.<field>', where <namespace> "
        f"is the distribution that owns it — 'ext.weft-pdf.backend', say.",
        valid_options=options,
        pack="weft-store",
    )


def field_for(op: FilterOp, field: str) -> FieldPath:
    """The parsed path, checked against `op` — the one call a store's translator makes.

    Parsing and checking are one call on purpose. A store that parsed here and
    checked somewhere else would be a store whose refusals could drift from the
    other store's, and the whole reason this module exists is that they must not.
    """
    path = parse_field_path(field)
    if op in _ADMITTED[path.kind]:
        return path
    raise FilterOpMismatchError(
        f"filter operator '{op.value}' cannot apply to field '{field}', which holds "
        f"{_DESCRIPTION[path.kind]}. {_REMEDY.get(op, 'use an operator that field admits')}.",
        pack="weft-store",
    )


def leaves(filter: Filter) -> tuple[Filter, ...]:
    """Every comparison in `filter`'s tree, combinators flattened away.

    Used by callers that want a filter checked before anything runs rather than
    while it is being translated — `weft plugins doctor`, and any future
    pipeline-load validation `docs/02-extension-model.md` promises.
    """
    if filter.clauses:
        return tuple(leaf for clause in filter.clauses for leaf in leaves(clause))
    return (filter,)
