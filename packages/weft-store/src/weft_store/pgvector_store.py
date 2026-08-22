"""`PgVectorStore` — the built-in `NodeStore`, `VectorSearch` and `TextSearch`, over Postgres.

Specified in `docs/06-phase-0-build.md` step 8: "a pgvector `NodeStore` with
`VectorSearch`... this is where the one container arrives — a `compose.yaml`
with Postgres and pgvector, because G4 retired the zero-container target and
made pgvector the floor." `compose.yaml`, at the repository root, brings up
that one container; `WEFT_DATABASE_URL` in `.env.example` is what a
`PgVectorSettings` block resolves against once discovery interpolates
`${env:...}`.

**Capability is derived, never declared.** This class implements every
method `weft_store.contract.NodeStore`, `VectorSearch`, `TextSearch` and
`MetadataFilter` name; nothing here sets a flag saying so —
`isinstance(store, VectorSearch)` at registration is what makes that true, per
`docs/02-extension-model.md` → *The store contract family*. All four tiers, as
of task 2.6; the store this repository ships beside it, `weft-qdrant`,
satisfies three, and that asymmetry is what a capability check has to be
demonstrable against.

**`TextSearch` arrives at task 2.5**, over a generated `tsvector` column —
see `_add_tsvector_column_sql` and `_search_text_sql` for why the index is
generated rather than written, and what each of the three text settings
decides. The task's property is what that column buys: a retriever asking
this store for a text channel is asking the thing that already owns the
corpus, so there is no second index for a pipeline to keep fresh.

**The text arm's three decisions are settings, not this pack's opinion**
(repair, 2026-08-17). Which text search configuration analyses the words,
whether a question matches on any of them or all of them, and which ranking
function scores the hit are all corpus-dependent, and `01` requirement 6 is
categorical: "every piece of it is parameterisable and composable by someone
who did not write it". They ship with the defaults this project's own corpus
wants and are reachable from `[packs.weft-store]` — see `PgVectorSettings`.
Because the index is a *generated* column, the configuration is schema, and
`_provision_text_index` refuses a database whose column was generated under a
different one rather than letting `ADD COLUMN IF NOT EXISTS` no-op.

**Connection settings are pack settings, not stage `with:` config** — the
same distinction `docs/02-extension-model.md` §2 draws for the graph pack's
`endpoint`/`api_key`: a database connection is one resource shared by
whatever this pack registers, not a per-pipeline-stage tuning knob. `register()`
wires `PgVectorSettings` in through `functools.partial`, exactly the shape
that section's own example shows, so `weft_kernel.runner.Runner.resolve`'s
`entry.factory(spec.config)` call becomes `PgVectorStore(settings, spec.config)`
— `spec.config` is accepted and ignored today; Phase 0 has no stage-level
tuning this store needs.

**The connection is opened lazily**, on first use, never inside `__init__`:
`psycopg.AsyncConnection.connect` is a coroutine, and `__init__` cannot be
one. `autocommit=True` is deliberate — Phase 0's contract already states
"durability is a guarantee, not a call" and "deletion is idempotent and
resumable rather than atomic", so per-statement autocommit is sufficient and
avoids a manual transaction lifecycle this contract does not ask for. The
`vector` extension and this store's two tables are created, idempotently, on
first connect — a store that requires a human to have already run a
migration before `weft index` works once is exactly the friction a walking
skeleton exists to remove.

**`add()` writes immediately; `flush()` is a true no-op.** The contract
permits buffering ("`add()` may buffer") but does not require it, and
writing immediately — one upsert per `add()` call — is the simpler
implementation that still satisfies "`flush` is documented as idempotent":
calling it on a store with nothing buffered is a legitimate no-op, not a
hazard.

**`ext` round-trips through `weft_store.rehydrate`**, not a hand-rolled map
— see that module's docstring for why `Node.model_validate` alone cannot
reconstruct a node's typed extension data from a JSONB column.

**Filters are translated to SQL at task 2.6**, and what a path may name and
which operator it admits are `weft_store.fields`', not this module's. That
split is the point: the same parse and the same refusals feed `weft-qdrant`'s
translator, so a `Filter` — which `docs/02-extension-model.md` → *Filters are
data* insists is data, serialised into a resolved pipeline — cannot come to
mean one thing in Postgres and another in a document store. Every literal
reaches the database as a bound parameter; the only thing this module
interpolates into SQL is a JSONB path built out of that parse, never out of
the raw `field` string an operator typed.
"""

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from functools import partial
from typing import Any, cast

import psycopg
from pgvector import Vector as PgVector
from pgvector.psycopg import register_vector_async
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, SecretStr

from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Node, NodeId, Outcome, Produced, SourceId, Vector
from weft_store.contract import (
    Cursor,
    Filter,
    FilterOp,
    FilterValue,
    NodeStore,
    Page,
    ReconcileEstimate,
    ReconcileMode,
    ReconcileReport,
    Removed,
    Scored,
    SourceRecord,
    SourceStatus,
    UnhandledFilterOpError,
)
from weft_store.fields import FieldKind, FieldPath, NodeField, field_for
from weft_store.rehydrate import rehydrate_ext

_PAGE_SIZE = 100

_CREATE_EXTENSION = "CREATE EXTENSION IF NOT EXISTS vector"

_CREATE_SOURCES_TABLE = """
CREATE TABLE IF NOT EXISTS weft_sources (
    id TEXT PRIMARY KEY,
    uri TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL,
    pipeline TEXT NOT NULL,
    status TEXT NOT NULL
)
"""

# `embedding` is declared as a bare `vector`, with no fixed dimension: pgvector has allowed an
# unconstrained column since 0.5.0, and this store has no reason to hard-code a dimension the
# configured embedder (`weft-embed`, or any future one) already owns.
_CREATE_NODES_TABLE = """
CREATE TABLE IF NOT EXISTS weft_nodes (
    id TEXT PRIMARY KEY,
    parents TEXT[] NOT NULL,
    sources TEXT[] NOT NULL,
    content TEXT NOT NULL,
    media_type TEXT NOT NULL,
    embedding VECTOR,
    ext JSONB NOT NULL
)
"""

_CREATE_TSVECTOR_INDEX = """
CREATE INDEX IF NOT EXISTS weft_nodes_content_tsv_idx ON weft_nodes USING GIN (content_tsv)
"""

# Does this database have the configured text search configuration? The cast is the question:
# `regconfig` resolves a name through `search_path` the way Postgres itself does, so a
# schema-qualified name and a bare one are answered on the database's own terms rather than by a
# `cfgname` string comparison that would get both wrong. An unknown name raises `UndefinedObject`,
# which is where the second statement comes in — `01` requirement 5 is not satisfied by a refusal
# that says only "no".
_RESOLVE_TEXT_SEARCH_CONFIG = "SELECT %(config)s::regconfig::oid AS oid"

_INSTALLED_TEXT_SEARCH_CONFIGS = "SELECT cfgname FROM pg_ts_config ORDER BY cfgname"

# What `content_tsv` is actually generated by, in this database, right now. Read back rather than
# assumed: see `_provision_text_index` for the silent divergence this closes. Keyed on
# `'weft_nodes'::regclass` rather than on a schema name, so it resolves the table through
# `search_path` exactly as every other statement here does — asking a differently-resolved table
# what its column is generated by would compare two different tables.
_GENERATED_EXPRESSION = """
SELECT pg_get_expr(d.adbin, d.adrelid) AS generation_expression
FROM pg_attrdef d
JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
WHERE d.adrelid = 'weft_nodes'::regclass AND a.attname = 'content_tsv'
"""

_SAME_TEXT_SEARCH_CONFIG = "SELECT %(found)s::regconfig = %(wanted)s::regconfig AS same"

#: Postgres renders a stored generation expression in its own normal form —
#: `to_tsvector('simple'::regconfig, content)` — which is what makes the configuration readable
#: back off the column at all. A shape this does not match is one this store did not write.
_GENERATED_TEXT_SEARCH_CONFIG = re.compile(r"to_tsvector\('([^']+)'::regconfig")


class TextQueryMode(StrEnum):
    """How the words of a question are combined into one `tsquery`.

    `plainto_tsquery` ANDs every word, which for a question ("why is mRMR preferred to plain
    relevance ranking?") matches nothing at all — a text arm that answers "no passages" to every
    natural-language ask is worse than no text arm, because it looks like a corpus problem. So
    `ANY` is the default. It is *not* the right answer everywhere: a keyword-style corpus, or a
    caller composing its own precise queries, wants the conjunction back, and which of the two a
    corpus wants is not knowable from inside this pack.
    """

    ANY = "any"
    ALL = "all"


class TextRank(StrEnum):
    """Which of Postgres's two ranking functions scores a text hit.

    Cover density (`ts_rank_cd`) ranks a passage by how close the matched words fall to each
    other, which is the signal a passage-level ranking usually wants; frequency (`ts_rank`)
    counts occurrences and weights, which is what a corpus of long, single-topic documents is
    better served by. Neither score is comparable to `search_vector`'s — that is what fusion is
    for, and why `Scored.score` is per-search.
    """

    COVER_DENSITY = "cover-density"
    FREQUENCY = "frequency"


def _add_tsvector_column_sql(config: str) -> sql.Composed:
    """The text index, as a *generated* column rather than a trigger or a second write in `add()`.

    Postgres recomputes it from `content` on every insert and update, so there is no path — no
    upsert, no future bulk load, no hand-run `UPDATE` — that can leave a node searchable by words
    it no longer contains. That is the property `TextSearch` is a store capability *for*; an index
    a retriever maintained beside the store would have exactly the staleness this column makes
    unreachable.

    Its own statement rather than a column in `_CREATE_NODES_TABLE`, because a database created
    before this column existed already has the table: `CREATE TABLE IF NOT EXISTS` would do
    nothing to it and text search would silently return nothing there. `ADD COLUMN IF NOT EXISTS`
    covers both the fresh database and the existing one, in one path — and it is also why
    `_provision_text_index` reads the column back: on an existing column this statement is a
    no-op, including when it asks for a *different* configuration.

    `config` is interpolated as a literal through `psycopg.sql`, never formatted in: DDL cannot
    carry a bound parameter, and a settings value reaching SQL by string concatenation is how a
    configuration file becomes an injection surface.
    """
    return sql.SQL("""
        ALTER TABLE weft_nodes
            ADD COLUMN IF NOT EXISTS content_tsv tsvector
            GENERATED ALWAYS AS (to_tsvector({config}, content)) STORED
    """).format(config=sql.Literal(config))


def _search_text_sql(
    config: str, mode: TextQueryMode, rank: TextRank, predicate: sql.Composable
) -> sql.Composed:
    """The lexical search, built from the three settings that decide what it means.

    **`ANY` rewrites the operator, not the character.** `plainto_tsquery` does the parsing, lexing
    and quoting, and its own `tsquery` output is rewritten in text form and cast back — which
    keeps every one of those Postgres's. The rewritten token is `' & '`, with its spaces: the AND
    operator is rendered space-delimited and no lexeme the default parser produces contains a
    space, so that string is unambiguous. A bare `&` is not, and the correction matters — measured
    on `pgvector/pgvector:pg16`, `plainto_tsquery('simple', 'find http://example.com/a?b&c now')`
    is `'find' & 'example.com/a?b&c' & 'example.com' & '/a?b&c' & 'now'`: the default parser's
    `url`, `url_path` and `host` token types routinely carry `&` *inside* a lexeme. Replacing
    every `&` rewrote those into lexemes no document contains, and the result was still valid
    `tsquery`, so nothing raised — the most specific term in the question simply never matched.

    The same `config` feeds this and `_add_tsvector_column_sql`, from one settings value, so the
    stored column and the query can never disagree about what a word is.

    `predicate` is the caller's `Filter`, or a constant true when there is none —
    built per call rather than once at construction, which task 2.6 forced: a
    filter is a per-call argument and the statement it appears in cannot be
    precomputed. The one thing that must not drift, the configuration name, is
    still read from the single settings field it always was.
    """
    parsed = sql.SQL("plainto_tsquery({config}, %(text)s)").format(config=sql.Literal(config))
    asked = (
        parsed
        if mode is TextQueryMode.ALL
        else sql.SQL("replace({parsed}::text, ' & ', ' | ')::tsquery").format(parsed=parsed)
    )
    ranker = sql.SQL("ts_rank_cd" if rank is TextRank.COVER_DENSITY else "ts_rank")
    return sql.SQL("""
        WITH asked AS (SELECT {asked} AS query)
        SELECT weft_nodes.*, {ranker}(content_tsv, asked.query) AS rank
        FROM weft_nodes, asked
        WHERE content_tsv @@ asked.query AND {predicate}
        ORDER BY rank DESC, id
        LIMIT %(top_k)s
    """).format(asked=asked, ranker=ranker, predicate=predicate)


class PgVectorSettings(BaseModel):
    """`weft-store`'s pack settings: one connection, and what its text arm means.

    **The text search settings are pack settings rather than stage `with:` configuration, and
    that is forced rather than chosen.** `content_tsv` is a generated column, so its
    configuration is a property of the *database*; and on the query path the store is reached as
    a service, not as a stage, so a stage-level `with:` block never gets near `search_text`. All
    three therefore live where an operator can actually set them — `[packs.weft-store]` in
    `weft.toml` — which is what makes running this store twice, under two configurations, a
    configuration edit (`01` requirement 6).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dsn: SecretStr

    #: The Postgres text search configuration both the stored column and the query use.
    #:
    #: **`simple` is the default, not the right answer.** The corpus this project is built
    #: against is deliberately bilingual (`09` §4, V1's non-English body), and an English stemmer
    #: applied to Polish text produces confident nonsense — matches on stems that are not stems
    #: of anything the reader wrote. `simple` folds case and splits on word boundaries and does
    #: nothing else, which is the one behaviour that is equally honest in both languages, and
    #: `Node` carries no language to choose per-node stemming by. An English-only corpus is a
    #: different situation and gets `english` here: with `simple`, a question about "retrieval"
    #: never reaches a passage that says "retrieved".
    text_search_config: str = "simple"

    #: Whether a question matches on any of its words or all of them. See `TextQueryMode`.
    text_query_mode: TextQueryMode = TextQueryMode.ANY

    #: Which ranking function scores a hit. See `TextRank`.
    text_rank: TextRank = TextRank.COVER_DENSITY


class UnknownTextSearchConfigError(WeftError, UnresolvedNameError):
    """`text_search_config` names a configuration this database has not got.

    `01` requirement 5 applied to a name an operator types into `weft.toml`: refused before the
    schema is touched, naming what was asked for and every configuration the database installs.
    Postgres's own error for the same mistake names neither the setting nor the alternatives.

    Fitness function 12's family: `valid_options` is every text search configuration this
    database actually has installed.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], pack: str) -> None:
        super().__init__(message, pack=pack)
        self.valid_options = valid_options


class TextSearchConfigMismatchError(WeftError):
    """`content_tsv` is generated by a different configuration than the one configured now.

    The failure this exists to prevent is silent: `ADD COLUMN IF NOT EXISTS` does nothing to an
    existing column, so a database provisioned under `simple` keeps storing `to_tsvector('simple',
    …)` however the setting is changed afterwards, while the query starts asking
    `plainto_tsquery('english', …)`. Stemmed query terms against unstemmed stored lexemes match
    almost nothing, and nothing anywhere raises — the operator sees a text arm that has quietly
    stopped working, which is the exact shape `01` requirement 5 forbids.
    """


#: The nine operators that reach a single leaf predicate rather than combining others —
#: named by hand for the identical reason `weft_qdrant.store._LEAF_OPS` is: the private
#: constant this list mirrors, `weft_store.contract._COMPARISON_OPS | {EXISTS}`, belongs to
#: the module that owns the whole vocabulary, and this one only needs to know which nine
#: are its own leaves.
_LEAF_OPS = frozenset(
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
)


def _predicate(filter: Filter, values: dict[str, object]) -> sql.Composed:
    """One `Filter` node as a SQL boolean expression, binding its values into `values`.

    Recursive, and every literal leaves through a bound parameter — a filter is
    data an operator wrote, and data that reaches SQL by string formatting is an
    injection surface. The only thing interpolated as SQL is a JSONB path built
    out of `weft_store.fields`' own parse, never out of the raw field string.

    The three refusals this never has to make — an unaddressable path, an
    operator a field cannot carry, an ordered comparison against text — are made
    for it by `fields.field_for` and by `Filter`'s own validator, so this
    function and `weft_qdrant`'s translator cannot drift into refusing different
    things.

    **`match`/`case _: raise`, not `if`/`if`/fallthrough — task 5.2b.** The combinators used
    to be peeled off by two `if`s and everything else fell to `field_for` unconditionally;
    a second combinator added to `FilterOp` tomorrow would have reached `field_for` as if it
    were a leaf, been refused there for a reason that has nothing to do with being a
    combinator, and reported the wrong defect. `case op if op in _LEAF_OPS` states which
    nine operators this branch is for; `case _: raise` is what stops "not `and`/`or`/`not`"
    standing in for "is a leaf".
    """
    match filter.op:
        case FilterOp.AND | FilterOp.OR:
            joiner = sql.SQL(" AND ") if filter.op is FilterOp.AND else sql.SQL(" OR ")
            return sql.SQL("({})").format(
                joiner.join(_predicate(clause, values) for clause in filter.clauses)
            )
        case FilterOp.NOT:
            return sql.SQL("(NOT {})").format(_predicate(filter.clauses[0], values))
        case op if op in _LEAF_OPS:
            path = field_for(filter.op, filter.field or "")
            if path.kind is FieldKind.EXTENSION:
                return _extension_predicate(filter.op, path, filter.value, values)
            column = sql.Identifier(_COLUMN_OF[path.core] if path.core is not None else "")
            placeholder = _bind(values, filter.value)
            if path.kind is FieldKind.TEXT_SET:
                return _text_set_predicate(filter.op, column, placeholder)
            return _text_predicate(filter.op, column, placeholder)
        case _:
            raise UnhandledFilterOpError(
                f"pgvector's filter translator has no top-level case for '{filter.op}'. It "
                f"translates the combinators 'and', 'or', 'not' and the leaf operators "
                f"{', '.join(sorted(member.value for member in _LEAF_OPS))}.",
                valid_options=("and", "or", "not", *sorted(member.value for member in _LEAF_OPS)),
                pack="weft-store",
            )


def _text_predicate(op: FilterOp, column: sql.Identifier, value: sql.Composable) -> sql.Composed:
    """`id`, `content`, `media_type` — all `NOT NULL` columns, so `exists` is a tautology.

    **`match`/`case _: raise` — task 5.2b.** The final line used to be an unconditional
    `operator = "=" if op is EQ else "IS DISTINCT FROM"`, correct only because `exists` and
    `in` are peeled off above it and `weft_store.fields._ADMITTED[FieldKind.TEXT]` admits
    exactly four operators today. A fifth ever admitted for text would have been silently
    compared with `IS DISTINCT FROM`, whatever it actually meant.
    """
    match op:
        case FilterOp.EXISTS:
            return sql.SQL("({} IS NOT NULL)").format(column)
        case FilterOp.IN:
            return sql.SQL("({} = ANY({}))").format(column, value)
        case FilterOp.EQ:
            return sql.SQL("({} = {})").format(column, value)
        case FilterOp.NE:
            return sql.SQL("({} IS DISTINCT FROM {})").format(column, value)
        case _:
            raise UnhandledFilterOpError(
                f"pgvector's text-field translator has no case for '{op}'. It knows: eq, "
                f"exists, in, ne.",
                valid_options=("eq", "exists", "in", "ne"),
                pack="weft-store",
            )


def _text_set_predicate(
    op: FilterOp, column: sql.Identifier, value: sql.Composable
) -> sql.Composed:
    """`lineage.parents`, `lineage.sources` — `TEXT[]` columns, compared element-wise.

    `in` is intersection rather than equality of the whole array, which is what
    the same filter means to a document store matching a payload array, and the
    only reading under which `in` on a set and `in` on a scalar are one operator.

    **`match`/`case _: raise` — task 5.2b.** The final line used to answer any operator
    that was not `exists` or `in` as `contains`, which is correct only because `contains`
    is the sole other member `weft_store.fields._ADMITTED[FieldKind.TEXT_SET]` admits today.
    """
    match op:
        case FilterOp.EXISTS:
            return sql.SQL("(array_length({}, 1) IS NOT NULL)").format(column)
        case FilterOp.IN:
            return sql.SQL("({} && {})").format(column, value)
        case FilterOp.CONTAINS:
            return sql.SQL("({} = ANY({}))").format(value, column)
        case _:
            raise UnhandledFilterOpError(
                f"pgvector's set-field translator has no case for '{op}'. It knows: "
                f"contains, exists, in.",
                valid_options=("contains", "exists", "in"),
                pack="weft-store",
            )


def _extension_predicate(
    op: FilterOp, path: FieldPath, value: FilterValue | None, values: dict[str, object]
) -> sql.Composed:
    """A path into the `ext` JSONB column, compared under this family's array rule.

    **An array is compared element-wise, a scalar directly** —
    `weft_store.fields`' stated rule, and a document store's native payload
    behaviour. SQL needs one expression covering both, so `elements` below is the
    stored value when it is already an array and a one-element array wrapping it
    otherwise; `jsonb_typeof` decides per row, which is the only place the
    decision can be made, since a JSONB column has no declared type.

    A consequence worth stating rather than discovering: under that rule `eq` and
    `contains` are the same question about extension data, and both mean "is this
    one of the values stored here". A pack that wants whole-array equality has
    asked for something no store in this family promises.

    `exists` is deliberately more than `IS NOT NULL`: a namespace present but
    holding JSON `null`, or an empty array, holds nothing, and answering "yes"
    for it would disagree with the document store, where an empty array is
    emptiness.

    **`match`/`case _: raise` — task 5.2b.** The final line used to be an unconditional
    `return _holds(...)`, reached by anything that was not `exists`, ordered, `in` or `ne` —
    correct only because `eq` and `contains` are the two operators left in
    `weft_store.fields._ADMITTED[FieldKind.EXTENSION]` once those four are removed. That set
    is now stated by hand rather than derived (see `fields._ADMITTED`'s own docstring), and
    this match is the other half of the same repair: an operator this function has not been
    taught refuses here even if a future `_ADMITTED` entry ever let it through.
    """
    stored = sql.SQL("(ext #> {})").format(sql.Literal([path.namespace, *path.keys]))
    elements = sql.SQL(
        "(CASE WHEN jsonb_typeof({stored}) = 'array' THEN {stored} "
        "ELSE jsonb_build_array({stored}) END)"
    ).format(stored=stored)
    match op:
        case FilterOp.EXISTS:
            return sql.SQL(
                "({stored} IS NOT NULL AND {stored} <> 'null'::jsonb AND "
                "jsonb_array_length({e}) > 0)"
            ).format(stored=stored, e=elements)
        case _ if op in _ORDERED_SQL:
            return sql.SQL(
                "(EXISTS (SELECT 1 FROM jsonb_array_elements({e}) AS element "
                "WHERE jsonb_typeof(element) = 'number' "
                "AND (element #>> '{{}}')::numeric {operator} {value}))"
            ).format(e=elements, operator=_ORDERED_SQL[op], value=_bind(values, value))
        case FilterOp.IN:
            wanted = value if isinstance(value, tuple) else (value,)
            return sql.SQL("({})").format(
                sql.SQL(" OR ").join(_holds(elements, values, each) for each in wanted)
            )
        case FilterOp.NE:
            return sql.SQL("(NOT {})").format(_holds(elements, values, value))
        case FilterOp.EQ | FilterOp.CONTAINS:
            return _holds(elements, values, value)
        case _:
            raise UnhandledFilterOpError(
                f"pgvector's extension-field translator has no case for '{op}'. It knows: "
                f"contains, eq, exists, gt, gte, in, lt, lte, ne.",
                valid_options=("contains", "eq", "exists", "gt", "gte", "in", "lt", "lte", "ne"),
                pack="weft-store",
            )


def _holds(
    elements: sql.Composed, values: dict[str, object], value: FilterValue | None
) -> sql.Composed:
    """Whether the stored value holds `value` — containment, which is membership for an array.

    `jsonb @> jsonb` answers exactly this: a scalar is contained by an array that
    has it as an element, which is why the element-wise rule needs no expansion
    into a subquery here.

    The literal is bound already wrapped in `psycopg.types.json.Jsonb` rather than
    handed to SQL's own `to_jsonb`, which cannot type a bare parameter: `to_jsonb
    (%(v)s)` raises *"could not determine polymorphic type because input has type
    unknown"* against every value. Wrapping it here also keeps one Python value
    converting to one JSON value in one place, instead of leaving `1` versus
    `"1"` to whatever type Postgres inferred.
    """
    name = f"f{len(values)}"
    values[name] = Jsonb(None if isinstance(value, tuple) else value)
    return sql.SQL("({e} @> {value})").format(e=elements, value=sql.Placeholder(name))


def _bind(values: dict[str, object], value: FilterValue | None) -> sql.Composable:
    """Bind one filter literal as a named parameter, returning its placeholder.

    Named rather than positional because the statements above interpolate the
    same sub-expression more than once; a positional parameter would have to be
    passed as many times as it appears, which is a counting exercise nobody
    should have to get right twice.
    """
    if value is None:
        return sql.SQL("NULL")
    name = f"f{len(values)}"
    values[name] = list(value) if isinstance(value, tuple) else value
    return sql.Placeholder(name)


#: Which column each addressable core field lives in. The only mapping in this store that
#: is not derivable, because `Node`'s shape and this schema's column names are two designs.
_COLUMN_OF: dict[NodeField, str] = {
    NodeField.ID: "id",
    NodeField.CONTENT: "content",
    NodeField.MEDIA_TYPE: "media_type",
    NodeField.PARENTS: "parents",
    NodeField.SOURCES: "sources",
}

_ORDERED_SQL: dict[FilterOp, sql.SQL] = {
    FilterOp.LT: sql.SQL("<"),
    FilterOp.LTE: sql.SQL("<="),
    FilterOp.GT: sql.SQL(">"),
    FilterOp.GTE: sql.SQL(">="),
}


def _predicate_or_true(filter: Filter | None, values: dict[str, object]) -> sql.Composable:
    """A filter's predicate, or a constant true where there is no filter.

    `TRUE` rather than two spellings of every statement: a search with no filter
    and a search with one must run the same SQL shape, or the filtered path is a
    second query that only a test with a filter in it ever exercises.
    """
    return sql.SQL("TRUE") if filter is None else _predicate(filter, values)


class PgVectorStore:
    """Every tier of the store family over Postgres, with pgvector for the vector column.

    Satisfies all four contracts structurally — this class never imports one of
    the Protocols, the same path any third-party store pack takes.
    """

    def __init__(self, settings: PgVectorSettings, config: object = None) -> None:
        del config  # nothing at the stage level this store needs — see the module docstring
        self._dsn = settings.dsn.get_secret_value()
        self._text_search_config = settings.text_search_config
        self._text_query_mode = settings.text_query_mode
        self._text_rank = settings.text_rank
        self._conn: psycopg.AsyncConnection[dict[str, Any]] | None = None

    def _search_text_sql(self, predicate: sql.Composable) -> sql.Composed:
        """This store's lexical statement, from the same configuration name the column has.

        One method rather than one precomputed statement, because task 2.6 gave
        `search_text` a per-call `Filter` to narrow by. The property the
        precomputed version was protecting is unchanged and is what matters:
        `self._text_search_config` is the single value that feeds both this and
        `_add_tsvector_column_sql`, so the stored column and the query cannot
        disagree about what a word is.
        """
        return _search_text_sql(
            self._text_search_config, self._text_query_mode, self._text_rank, predicate
        )

    async def _connection(self) -> psycopg.AsyncConnection[dict[str, Any]]:
        """The lazily-opened, schema-provisioned connection this store reuses for its lifetime."""
        if self._conn is not None:
            return self._conn
        # Parameterising the class explicitly, rather than relying on inference from
        # `row_factory=dict_row`, is what makes `Self` bind to `AsyncConnection[dict[str, Any]]`
        # under strict checking — inference alone resolves `Row` to the class's `TupleRow`
        # default before it ever looks at `dict_row`'s own return type.
        conn = await psycopg.AsyncConnection[dict[str, Any]].connect(
            self._dsn, autocommit=True, row_factory=dict_row
        )
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_EXTENSION)
        # `pgvector`'s type adapter looks the `vector` type up by name in the database's own
        # catalog, so it must register *after* `CREATE EXTENSION` has run at least once, never
        # before — a fresh database has no `vector` type until this statement creates it.
        await register_vector_async(conn)
        async with conn.cursor() as cur:
            await cur.execute(_CREATE_SOURCES_TABLE)
            await cur.execute(_CREATE_NODES_TABLE)
            await self._provision_text_index(cur)
        self._conn = conn
        return conn

    async def _provision_text_index(self, cur: psycopg.AsyncCursor[dict[str, Any]]) -> None:
        """Create `content_tsv` under the configured configuration, or refuse to use this database.

        Three statements, and the last two exist because the first one is a no-op when the column
        is already there. `ADD COLUMN IF NOT EXISTS` cannot *change* a generation expression, so a
        database provisioned under one configuration and opened under another would keep storing
        the old lexemes while the query asked for the new ones — matching almost nothing, raising
        nothing, and looking like an empty corpus. The column is therefore read back and compared,
        by `regconfig` identity rather than by spelling, so `simple` and `pg_catalog.simple` are
        one configuration and a genuinely different one is named in the refusal.

        The configuration name itself is resolved first, against this database's own catalogue, so
        a typo in `weft.toml` is refused before any schema is touched and with the installed names
        to choose from.
        """
        await self._require_text_search_config(cur)
        await cur.execute(_add_tsvector_column_sql(self._text_search_config))
        await cur.execute(_CREATE_TSVECTOR_INDEX)
        await cur.execute(_GENERATED_EXPRESSION)
        row = await cur.fetchone()
        expression = cast(str, row["generation_expression"]) if row is not None else ""
        found = _GENERATED_TEXT_SEARCH_CONFIG.search(expression)
        if found is None:
            raise TextSearchConfigMismatchError(
                f"weft_nodes.content_tsv is generated by an expression this store did not write: "
                f"{expression!r}. It cannot be checked against text_search_config="
                f"{self._text_search_config!r}, and searching against a column whose contents are "
                f"unknown would report matches nobody can account for.",
                pack="weft-store",
            )
        await cur.execute(
            _SAME_TEXT_SEARCH_CONFIG,
            {"found": found.group(1), "wanted": self._text_search_config},
        )
        row = await cur.fetchone()
        if row is not None and not cast(bool, row["same"]):
            raise TextSearchConfigMismatchError(
                f"weft_nodes.content_tsv in this database is generated by "
                f"'{found.group(1)}', and [packs.weft-store] text_search_config asks for "
                f"'{self._text_search_config}'. A generated column cannot be altered in place, so "
                f"the stored lexemes would stay '{found.group(1)}'s while every query asked "
                f"'{self._text_search_config}'s — near-zero matches, and no error to notice it by. "
                f"Either set text_search_config back to '{found.group(1)}', or drop the column "
                f"(ALTER TABLE weft_nodes DROP COLUMN content_tsv) and let this store recreate "
                f"it: it is generated from content, so nothing needs re-indexing.",
                pack="weft-store",
            )

    async def _require_text_search_config(self, cur: psycopg.AsyncCursor[dict[str, Any]]) -> None:
        """Refuse a configuration name this database has not got, naming the ones it has."""
        try:
            await cur.execute(_RESOLVE_TEXT_SEARCH_CONFIG, {"config": self._text_search_config})
        except psycopg.errors.UndefinedObject as exc:
            await cur.execute(_INSTALLED_TEXT_SEARCH_CONFIGS)
            rows = await cur.fetchall()
            options = tuple(cast(str, row["cfgname"]) for row in rows)
            installed = ", ".join(options) or "(none)"
            raise UnknownTextSearchConfigError(
                f"[packs.weft-store] text_search_config names "
                f"'{self._text_search_config}', which this database has no text search "
                f"configuration for. Installed here: {installed}.",
                valid_options=options,
                pack="weft-store",
            ) from exc

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Store `payload` and pass it through — the module docstring's narrowing note."""
        del ctx
        await self.add(payload)
        return Produced(value=payload)

    async def add(self, nodes: Sequence[Node]) -> None:
        if not nodes:
            return
        conn = await self._connection()
        rows = [_node_to_row(node) for node in nodes]
        async with conn.cursor() as cur:
            await cur.executemany(
                """
                INSERT INTO weft_nodes (id, parents, sources, content, media_type, embedding, ext)
                VALUES (%(id)s, %(parents)s, %(sources)s, %(content)s, %(media_type)s,
                        %(embedding)s, %(ext)s)
                ON CONFLICT (id) DO UPDATE SET
                    parents = EXCLUDED.parents,
                    sources = EXCLUDED.sources,
                    content = EXCLUDED.content,
                    media_type = EXCLUDED.media_type,
                    embedding = EXCLUDED.embedding,
                    ext = EXCLUDED.ext
                """,
                rows,
            )

    async def flush(self) -> None:
        """A true no-op: `add()` writes immediately — see the module docstring."""
        return

    async def get(self, ids: Sequence[NodeId]) -> Sequence[Node]:
        if not ids:
            return ()
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM weft_nodes WHERE id = ANY(%s)", (list(ids),))
            rows = await cur.fetchall()
        return tuple(_row_to_node(row) for row in rows)

    async def delete_source(self, source_id: SourceId) -> Removed:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE weft_sources SET status = %s WHERE id = %s",
                (SourceStatus.DELETING.value, source_id),
            )
            await cur.execute("DELETE FROM weft_nodes WHERE %s = ANY(sources)", (source_id,))
            node_count = cur.rowcount
            await cur.execute("DELETE FROM weft_sources WHERE id = %s", (source_id,))
        return Removed(source_id=source_id, node_count=node_count)

    async def reconcile(self, ctx: Context, mode: ReconcileMode) -> ReconcileReport:
        """Finish every deletion that was interrupted — `Reconcilable`, task **5.1b**.

        **What a *node* store has to converge, and what it deliberately does not.** `02` §1
        describes `repair` as removing "derived state whose source is gone", which is a
        graph pack's job and not this one's: a node store holds the primary data, so it *is*
        the authority on what exists, and a pass that deleted nodes because no `weft_sources`
        row named them would erase a corpus indexed before source records were written. What
        this store genuinely owns is the other half of `SourceRecord.status`'s reason for
        existing — "a crash leaves `status=DELETING`, so the next call or `weft doctor` can
        finish the job rather than leaving it half-deleted and invisible". Every tombstone is
        a deletion that started and did not end, and finishing them is convergence for this
        backend.

        **This is where "resumes rather than restarting" is a fact about durable state rather
        than a promise about a cursor.** The backlog *is* the tombstone rows. A pass cancelled
        after two of five leaves three tombstones standing, and the next pass finds exactly
        those three — no cursor is saved, so none can be lost with the process. `remaining` is
        what is still tombstoned when this returns, so `converged` answers honestly whether
        another pass is owed.

        `full` does the same work and backfills nothing, which is not a shortcut: backfill
        builds derived state that was never created, and a node store holds no derived state
        to build. `backfilled` is `0` and says so.
        """
        del ctx
        conn = await self._connection()
        examined = 0
        removed = 0
        for source_id in await self._tombstoned():
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM weft_nodes WHERE %s = ANY(sources)", (source_id,))
                removed += cur.rowcount
                await cur.execute("DELETE FROM weft_sources WHERE id = %s", (source_id,))
            examined += 1
        return ReconcileReport(
            mode=mode,
            examined=examined,
            removed=removed,
            remaining=len(await self._tombstoned()),
        )

    async def estimate(self, ctx: Context, mode: ReconcileMode) -> ReconcileEstimate:
        """What converging would cost — `Reconcilable`, task **5.1c**.

        The honest answer is `model_calls=0` for either mode, always: `reconcile`'s own
        docstring above owns the argument — a node store holds the primary data, so it has
        no derived state for `full` to backfill, and this method reports that rather than
        inventing a number for a mode it does not distinguish. `pending` is the identical
        tombstone count `reconcile` itself would examine, read the same way, so the two never
        disagree about what is outstanding.
        """
        del ctx
        pending = len(await self._tombstoned())
        description = (
            f"{pending} source(s) have an unfinished deletion to finish"
            if pending
            else "no unfinished deletions; nothing to converge"
        )
        return ReconcileEstimate(mode=mode, pending=pending, description=description)

    async def _tombstoned(self) -> tuple[str, ...]:
        """Every source id whose deletion started and did not finish, in id order."""
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT id FROM weft_sources WHERE status = %s ORDER BY id",
                (SourceStatus.DELETING.value,),
            )
            rows = await cur.fetchall()
        return tuple(cast(str, row["id"]) for row in rows)

    async def scan(self, cursor: Cursor | None = None) -> Page[Node]:
        conn = await self._connection()
        after = cursor if cursor is not None else ""
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM weft_nodes WHERE id > %s ORDER BY id LIMIT %s",
                (after, _PAGE_SIZE + 1),
            )
            rows = await cur.fetchall()
        return _page_of(rows)

    async def count(self) -> int:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) AS n FROM weft_nodes")
            row = await cur.fetchone()
        return cast(int, row["n"]) if row is not None else 0

    async def put_source(self, record: SourceRecord) -> None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO weft_sources (id, uri, content_hash, indexed_at, pipeline, status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    uri = EXCLUDED.uri,
                    content_hash = EXCLUDED.content_hash,
                    indexed_at = EXCLUDED.indexed_at,
                    pipeline = EXCLUDED.pipeline,
                    status = EXCLUDED.status
                """,
                (
                    record.id,
                    record.uri,
                    record.content_hash,
                    record.indexed_at,
                    record.pipeline,
                    record.status.value,
                ),
            )

    async def get_source(self, source_id: SourceId) -> SourceRecord | None:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM weft_sources WHERE id = %s", (source_id,))
            row = await cur.fetchone()
        return _row_to_source_record(row) if row is not None else None

    async def list_sources(self) -> Sequence[SourceRecord]:
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM weft_sources ORDER BY id")
            rows = await cur.fetchall()
        return tuple(_row_to_source_record(row) for row in rows)

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        """Every node `filter` selects, paged — `MetadataFilter`, task 2.6.

        The same walk as `scan`, with a predicate: ordered by the node id so a
        cursor means something, and one page at a time because a predicate over a
        corpus can select all of it.
        """
        values: dict[str, object] = {"after": cursor if cursor is not None else ""}
        statement = sql.SQL(
            "SELECT * FROM weft_nodes WHERE id > %(after)s AND {predicate} "
            "ORDER BY id LIMIT %(limit)s"
        ).format(predicate=_predicate(filter, values))
        values["limit"] = _PAGE_SIZE + 1
        conn = await self._connection()
        async with conn.cursor() as cur:
            await cur.execute(statement, values)
            rows = await cur.fetchall()
        return _page_of(rows)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        conn = await self._connection()
        values: dict[str, object] = {}
        statement = sql.SQL("""
                SELECT *, embedding <=> %(vector)s AS distance
                FROM weft_nodes
                WHERE embedding IS NOT NULL AND {predicate}
                ORDER BY embedding <=> %(vector)s
                LIMIT %(top_k)s
                """).format(predicate=_predicate_or_true(filter, values))
        async with conn.cursor() as cur:
            await cur.execute(
                statement,
                # Wrapped in `pgvector.Vector`, not passed as a bare list: a plain Python list
                # adapts to a Postgres array, and `<=>` has no overload comparing `vector` to
                # `double precision[]`. `register_vector_async` is what makes `PgVector` dump as
                # the `vector` type instead.
                {**values, "vector": PgVector(list(vector.values)), "top_k": top_k},
            )
            rows = await cur.fetchall()
        return [
            Scored(value=_row_to_node(row), score=1.0 - cast(float, row["distance"]))
            for row in rows
        ]

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        """Rank stored nodes by lexical match on their own text — `TextSearch`, task 2.5.

        Never embeds and never asks who embedded: this is the arm that works on a corpus
        indexed with no model at all, and the one whose recall does not move when the
        embedder is swapped. `filter` narrows what may be ranked, exactly as it does on
        `search_vector` — a store that can evaluate a filter has no excuse for ignoring one.

        No match is an empty sequence, not an error — see `TextSearch`'s own docstring.
        """
        conn = await self._connection()
        values: dict[str, object] = {}
        statement = self._search_text_sql(_predicate_or_true(filter, values))
        async with conn.cursor() as cur:
            await cur.execute(statement, {**values, "text": text, "top_k": top_k})
            rows = await cur.fetchall()
        return [
            Scored(value=_row_to_node(row), score=float(cast(float, row["rank"]))) for row in rows
        ]

    async def aclose(self) -> None:
        """Close the underlying connection, if one was ever opened. Not part of any contract."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


def register(registrar: PackRegistrar, settings: PgVectorSettings) -> None:
    """Register `PgVectorStore` as `"pgvector"` for `NodeStore`. The only plugin this pack ships."""
    registrar.add(NodeStore, "pgvector", partial(PgVectorStore, settings))


def _page_of(rows: Sequence[Mapping[str, object]]) -> Page[Node]:
    """One page of an id-ordered walk, from a query that asked for one row more than a page.

    Shared by `scan` and `matching` because the cursor discipline — fetch
    `_PAGE_SIZE + 1`, hand back `_PAGE_SIZE`, and carry the last id only when
    there was a row beyond it — is a property of this store's paging, not of
    either walk. Two copies would be two chances to say "there is more" wrongly.
    """
    page_rows = rows[:_PAGE_SIZE]
    has_more = len(rows) > _PAGE_SIZE
    next_cursor = Cursor(cast(str, page_rows[-1]["id"])) if has_more else None
    return Page(items=tuple(_row_to_node(row) for row in page_rows), next_cursor=next_cursor)


def _node_to_row(node: Node) -> dict[str, object]:
    dump = node.model_dump(mode="json")
    lineage = cast(dict[str, object], dump["lineage"])
    embedding = dump["embedding"]
    return {
        "id": dump["id"],
        "parents": lineage["parents"],
        "sources": lineage["sources"],
        "content": dump["content"],
        "media_type": dump["media_type"],
        "embedding": cast("dict[str, object]", embedding)["values"] if embedding else None,
        "ext": Jsonb(dump["ext"]),
    }


def _row_to_node(row: Mapping[str, object]) -> Node:
    embedding = row["embedding"]
    raw_ext = cast(dict[str, object], row["ext"])
    return Node.model_validate(
        {
            "id": row["id"],
            "lineage": {
                "parents": tuple(cast(list[str], row["parents"])),
                "sources": row["sources"],
            },
            "content": row["content"],
            "media_type": row["media_type"],
            # `pgvector`'s registered adapter (`register_vector_async`) decodes the `vector`
            # column into its own `pgvector.Vector` wrapper, not a plain sequence — `.to_list()`
            # is what turns it back into the floats `weft_kernel.payload.Vector` wants.
            "embedding": {"values": cast(PgVector, embedding).to_list()}
            if embedding is not None
            else None,
            "ext": rehydrate_ext(raw_ext),
        },
        context={"derived": True},
    )


def _row_to_source_record(row: Mapping[str, object]) -> SourceRecord:
    return SourceRecord(
        id=SourceId(cast(str, row["id"])),
        uri=cast(str, row["uri"]),
        content_hash=cast(str, row["content_hash"]),
        indexed_at=cast(datetime, row["indexed_at"]),
        pipeline=cast(str, row["pipeline"]),
        status=SourceStatus(cast(str, row["status"])),
    )
