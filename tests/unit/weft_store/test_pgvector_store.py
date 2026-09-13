"""Tests for `weft_store.pgvector_store`, against a real Postgres + pgvector container.

Mirrors `packages/weft-rag/src/weft_store/pgvector_store.py`. Per
`docs/06-phase-0-build.md` step 8, "integration tests must run against the
real container, not a mock, and must be skipped with a clear reason — never
silently passed — when it is absent." `docker compose up -d` (`compose.yaml`,
repository root) brings the container up; `WEFT_DATABASE_URL` names it. If
the connection attempt below fails for any reason, every test in this module
is skipped with that reason attached, rather than quietly reporting green.

Covers the happy path (round-tripping a node through `add`/`get`, including
its lineage, its `SyntheticOrigin` ext data and its embedding — pgvector's
own single-precision storage means the embedding is compared with tolerance,
not exact equality), the edge case of `search_vector` ranking by cosine
distance, and the error case of a `Filter` this store does not yet translate.
`search_text` (task 2.5) is covered on the same three axes: a ranking that
prefers the passage matching more of the words, a search that matches nothing
and says so with an empty ranking rather than an error, and the same `Filter`
refusal.

Task 2.5's repair adds the axis the first pass had none of: the three
decisions that *are* this store's text technique are settings, so each is
exercised by running the same store twice under two configurations —
`text_query_mode` and `text_rank` against the shared database, and
`text_search_config` against a database of its own, because a generated
column's configuration is schema rather than a per-call argument. The
`fresh_database` fixture is what makes that possible, and it is also what the
three refusals need: an unknown configuration name, a database whose column
was generated under a different one, and a `content_tsv` this store did not
write.
"""

import os
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr, ValidationError

from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import MediaType, Node, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec
from weft_store.contract import (
    Filter,
    FilterOp,
    NodeStore,
    SourceRecord,
    TextSearch,
    VectorSearch,
)
from weft_store.pgvector_store import (
    Bm25NotAvailableError,
    PgVectorSettings,
    PgVectorStore,
    TextMode,
    TextQueryMode,
    TextRank,
    TextSearchConfigMismatchError,
    UnknownTextSearchConfigError,
)

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def _database_reachable() -> str | None:
    """`None` if a real connection to `_DSN` succeeds; otherwise the reason it did not."""
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}"
    await conn.close()
    return None


@pytest.fixture
async def store() -> AsyncIterator[PgVectorStore]:
    """A `PgVectorStore` against a truncated schema — skips the whole module if unreachable."""
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    await instance.count()  # forces schema creation (extension + tables) through public API
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
    await conn.close()
    yield instance
    await instance.aclose()


@pytest.fixture
async def fresh_database() -> AsyncIterator[str]:
    """A database that has never been provisioned, dropped again afterwards.

    `content_tsv` is a *generated* column, so its text search configuration is a property of the
    database and not of a call: the fixture database above is already generated under `simple`,
    and a store asking for another configuration there is the mismatch one of these tests is
    about. Everything that reads the setting at provisioning time therefore needs its own
    database — which is also the situation an operator setting it is in.
    """
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    name = f"weft_probe_{uuid4().hex[:12]}"
    admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        # The DSN's path component is the database name; nothing here parses more of it than
        # that, and the fallback above is the only form this repository's own tooling writes.
        yield f"{_DSN.rsplit('/', 1)[0]}/{name}"
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


def _node(content: str, *, sources: frozenset[SourceId] = frozenset()) -> Node:
    return Node.synthetic(
        content=content, media_type=MediaType.TEXT, reason="test fixture", sources=sources
    )


async def test_add_and_get_round_trip_a_node_including_lineage_and_ext(
    store: PgVectorStore,
) -> None:
    # Arrange
    node = _node("hello world", sources=frozenset({SourceId("doc-1")})).with_embedding(
        Vector(values=(0.5, -0.25, 0.75))
    )

    # Act
    await store.add([node])
    [fetched] = await store.get([node.id])

    # Assert
    assert fetched.id == node.id
    assert fetched.content == node.content
    assert fetched.lineage.sources == node.lineage.sources
    assert fetched.ext == node.ext
    assert fetched.embedding is not None and node.embedding is not None
    assert fetched.embedding.values == pytest.approx(node.embedding.values, abs=1e-6)


async def test_run_composes_through_the_kernel_runner_as_a_node_store_stage(
    store: PgVectorStore,
) -> None:
    # Arrange
    def factory(_config: object) -> PgVectorStore:
        return store

    registry = Registry()
    registry.add(NodeStore, "pgvector", factory, distribution="weft-store")
    engine = Runner(registry)
    specs = (StageSpec(id="store", contract=NodeStore, name="pgvector"),)
    node = _node("via the runner")

    async def batches() -> AsyncIterator[list[Node]]:
        yield [node]

    # Act
    pipeline = engine.resolve(specs, tenant_id="tenant-a")
    summary = await engine.run(pipeline, batches(), _ctx())

    # Assert
    assert summary.produced == 1
    assert await store.count() == 1


async def test_search_vector_ranks_by_cosine_distance_and_advertises_vector_search(
    store: PgVectorStore,
) -> None:
    # Arrange
    near = _node("near").with_embedding(Vector(values=(1.0, 0.0)))
    far = _node("far").with_embedding(Vector(values=(-1.0, 0.0)))
    await store.add([near, far])

    # Act
    results = await store.search_vector(Vector(values=(1.0, 0.0)), top_k=2)

    # Assert
    assert isinstance(store, VectorSearch)
    assert [scored.value.id for scored in results] == [near.id, far.id]
    assert results[0].score > results[1].score


async def test_search_vector_narrows_by_a_filter_rather_than_refusing_it(
    store: PgVectorStore,
) -> None:
    # Arrange — task 2.6 replaced this store's `UnsupportedFilterError` with a translation.
    # The cross-backend agreement is `tests/integration/test_store_conformance.py`'s subject;
    # what belongs here is that the filter reaches *this* store's own vector statement.
    wanted = _node("wanted").with_embedding(Vector(values=(1.0, 0.0)))
    unwanted = _node("unwanted").with_embedding(Vector(values=(1.0, 0.0)))
    await store.add([wanted, unwanted])

    # Act
    results = await store.search_vector(
        Vector(values=(1.0, 0.0)),
        top_k=5,
        filter=Filter(op=FilterOp.EQ, field="content", value="wanted"),
    )

    # Assert
    assert [scored.value.content for scored in results] == ["wanted"]


async def test_search_text_ranks_by_lexical_match_and_advertises_text_search(
    store: PgVectorStore,
) -> None:
    # Arrange — no embeddings anywhere: a text channel is the one that still works when
    # nothing has been embedded, which is half of why it is a capability of its own.
    both = _node("mutual information redundancy criterion")
    one = _node("redundancy in distributed storage")
    neither = _node("the cat sat on the mat")
    await store.add([both, one, neither])

    # Act
    results = await store.search_text("mutual redundancy", top_k=5)

    # Assert — the store advertises the capability by implementing it, and the node
    # matching both words outranks the one matching a single word.
    assert isinstance(store, TextSearch)
    assert [scored.value.id for scored in results] == [both.id, one.id]
    assert results[0].score > results[1].score


async def test_search_text_matches_a_lexeme_that_itself_contains_an_ampersand(
    store: PgVectorStore,
) -> None:
    """Repair for a reviewer finding: the AND→OR rewrite used to corrupt URL lexemes.

    Measured against this container: `plainto_tsquery('simple', 'http://alpha.example/q?w=1&z=2')`
    is `'alpha.example/q?w=1&z=2' & 'alpha.example' & '/q?w=1&z=2'` — the default parser's `url`
    and `url_path` tokens carry `&` inside a single lexeme. Replacing every `&` rewrote those
    lexemes into ones no document contains, and the result was still valid `tsquery`, so nothing
    raised: the most specific term in the question simply never matched. Replacing the *operator*
    — the space-delimited ` & ` Postgres renders, which no lexeme can contain — leaves them alone.
    """
    # Arrange — the URL is the only thing telling these two apart; both share the host.
    exact = _node("The changelog lives at http://alpha.example/q?w=1&z=2 and nowhere else")
    host_only = _node("The homepage alpha.example has moved")
    await store.add([exact, host_only])

    # Act
    results = await store.search_text("http://alpha.example/q?w=1&z=2", top_k=5)

    # Assert — the node carrying the whole URL outranks the one sharing only the host, which it
    # cannot do while its two `&`-bearing lexemes are being rewritten out of the query.
    assert [scored.value.id for scored in results] == [exact.id, host_only.id]
    assert results[0].score > results[1].score


async def test_search_text_returns_an_empty_ranking_when_nothing_matches(
    store: PgVectorStore,
) -> None:
    # Arrange
    await store.add([_node("the cat sat on the mat")])

    # Act
    results = await store.search_text("photosynthesis", top_k=5)

    # Assert — a store that looked and found nothing answers with an empty ranking. It is
    # not an error and it is not `None`: "no passage matches these words" is a fact a
    # retriever is entitled to pass on.
    assert list(results) == []


async def test_query_mode_all_requires_every_word_of_the_question(store: PgVectorStore) -> None:
    """Repair for a reviewer finding: the AND→OR rewrite is a *choice*, so it is a setting.

    ORing is the right default for a natural-language question and the wrong one for a
    keyword-style ask, and the pack that ships the technique does not get to decide that for
    every corpus — `01` requirement 6. This runs the same store twice, from configuration alone.
    """
    # Arrange — the fixture store keeps the pack default (`any`); this one asks for `all`.
    both = _node("mutual information redundancy criterion")
    one = _node("redundancy in distributed storage")
    await store.add([both, one])
    conjunctive = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(_DSN), text_query_mode=TextQueryMode.ALL)
    )

    # Act
    any_of = await store.search_text("mutual redundancy", top_k=5)
    all_of = await conjunctive.search_text("mutual redundancy", top_k=5)
    await conjunctive.aclose()

    # Assert — the same store, the same corpus, the same question, two answers.
    assert [scored.value.id for scored in any_of] == [both.id, one.id]
    assert [scored.value.id for scored in all_of] == [both.id]


async def test_the_ranking_function_is_a_setting_rather_than_this_packs_opinion(
    store: PgVectorStore,
) -> None:
    """Cover density and frequency answer different questions; which one a corpus wants is not
    knowable from here. Measured on this container: 0.2 against 0.06079271 for the row below.
    """
    # Arrange
    node = _node("mutual information redundancy criterion")
    await store.add([node])
    by_frequency = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(_DSN), text_rank=TextRank.FREQUENCY)
    )

    # Act
    density = await store.search_text("mutual redundancy", top_k=5)
    frequency = await by_frequency.search_text("mutual redundancy", top_k=5)
    await by_frequency.aclose()

    # Assert — same node, same query, a score from a different function.
    assert [scored.value.id for scored in density] == [node.id]
    assert [scored.value.id for scored in frequency] == [node.id]
    assert density[0].score != frequency[0].score


async def test_a_configured_stemmer_reaches_both_the_stored_column_and_the_query(
    fresh_database: str,
) -> None:
    """The `english` case the pack default cannot serve, from a `weft.toml` edit and nothing else.

    `simple` is the right default for a deliberately bilingual corpus, and it is exactly wrong for
    an English-only one: "retrieval" and "retrieved" are unrelated words to it. One value feeds the
    generated column *and* `plainto_tsquery`, so the two cannot disagree about what a word is.
    """
    # Arrange
    store = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), text_search_config="english")
    )
    await store.add([_node("the retrieval of documents")])

    # Act
    results = await store.search_text("retrieved", top_k=5)
    await store.aclose()

    # Assert — a stem match, which `simple` does not make and this database now does.
    assert len(results) == 1


async def test_a_column_generated_under_another_configuration_is_refused_naming_both(
    fresh_database: str,
) -> None:
    """`ADD COLUMN IF NOT EXISTS` no-ops on an existing column, so changing the setting later
    would leave `to_tsvector('simple', …)` stored and `plainto_tsquery('english', …)` asked —
    near-zero matches, no error, and nothing for an operator to notice. It is refused instead.
    """
    # Arrange — a database provisioned under the default, then reopened under another.
    under_simple = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))
    await under_simple.count()
    await under_simple.aclose()
    under_english = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), text_search_config="english")
    )

    # Act / Assert
    with pytest.raises(TextSearchConfigMismatchError) as caught:
        await under_english.count()
    message = str(caught.value)
    assert "simple" in message
    assert "english" in message
    assert "content_tsv" in message


async def test_a_content_tsv_this_store_did_not_write_is_refused_rather_than_searched(
    fresh_database: str,
) -> None:
    """A column generated by something else is not assumed to be equivalent to ours.

    The check reads the configuration back out of the column's own generation expression, so an
    expression in a shape this store never writes leaves it with nothing to compare. Searching
    anyway would report matches against an index whose contents nobody here can account for.
    """
    # Arrange — a `weft_nodes` whose text column is generated by a bare cast, not by `to_tsvector`.
    setup = await psycopg.AsyncConnection.connect(fresh_database, autocommit=True)
    async with setup.cursor() as cur:
        await cur.execute(
            """
            CREATE TABLE weft_nodes (
                id TEXT PRIMARY KEY,
                parents TEXT[] NOT NULL,
                sources TEXT[] NOT NULL,
                content TEXT NOT NULL,
                media_type TEXT NOT NULL,
                embedding TEXT,
                ext JSONB NOT NULL,
                content_tsv tsvector GENERATED ALWAYS AS (content::tsvector) STORED
            )
            """
        )
    await setup.close()
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))

    # Act / Assert — the expression itself is quoted back, since that is the whole of what is known.
    with pytest.raises(TextSearchConfigMismatchError) as caught:
        await store.count()
    message = str(caught.value)
    assert "this store did not write" in message
    assert "(content)::tsvector" in message


async def test_a_text_search_configuration_this_database_has_not_got_is_refused_loudly(
    fresh_database: str,
) -> None:
    """`01` requirement 5, applied to a name an operator can mistype in `weft.toml`."""
    # Arrange
    store = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), text_search_config="klingon")
    )

    # Act / Assert — named, with the configurations this database actually has.
    with pytest.raises(UnknownTextSearchConfigError) as caught:
        await store.count()
    message = str(caught.value)
    assert "klingon" in message
    assert "english" in message
    assert "simple" in message


def test_every_text_search_knob_is_reachable_from_a_configuration_table() -> None:
    """The knobs exist in the settings model, so a `[packs.store]` table reaches all three.

    `.phase2-findings.md` finding 9 item 4: "a knob that exists in the library and not in the
    config model is a knob a third party cannot reach." This is that check, run against the shape
    `weft_engine.registry_bootstrap.pack_settings_from_config` hands to `register()`.
    """
    # Arrange
    table = {
        "dsn": "postgresql://weft:weft@localhost:5433/weft",
        "text_search_config": "english",
        "text_query_mode": "all",
        "text_rank": "frequency",
    }

    # Act
    settings = PgVectorSettings.model_validate(table)

    # Assert
    assert settings.text_search_config == "english"
    assert settings.text_query_mode is TextQueryMode.ALL
    assert settings.text_rank is TextRank.FREQUENCY


def test_a_misspelled_query_mode_is_refused_rather_than_defaulted() -> None:
    # Arrange
    table = {"dsn": "postgresql://weft:weft@localhost:5433/weft", "text_query_mode": "sometimes"}

    # Act / Assert — pydantic names the field and the values it accepts; silently falling back
    # to `any` would give the operator a store that ignored what they wrote.
    with pytest.raises(ValidationError):
        PgVectorSettings.model_validate(table)


async def test_search_text_narrows_by_a_filter_rather_than_refusing_it(
    store: PgVectorStore,
) -> None:
    # Arrange — the same change task 2.6 made to `search_vector`, on the arm that has a
    # `WITH` clause of its own: the predicate has to reach *inside* the ranking statement,
    # not wrap it, or the top_k would be taken before the filter narrowed anything.
    wanted = _node("redundancy criterion", sources=frozenset({SourceId("keep")}))
    unwanted = _node("redundancy criterion elsewhere", sources=frozenset({SourceId("drop")}))
    await store.add([wanted, unwanted])

    # Act
    results = await store.search_text(
        "redundancy",
        top_k=5,
        filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value="keep"),
    )

    # Assert
    assert [scored.value.content for scored in results] == ["redundancy criterion"]


async def test_delete_source_removes_every_node_carrying_that_source(
    store: PgVectorStore,
) -> None:
    # Arrange
    doomed = _node("doomed", sources=frozenset({SourceId("doc-1")}))
    survivor = _node("survivor", sources=frozenset({SourceId("doc-2")}))
    await store.add([doomed, survivor])
    await store.put_source(
        SourceRecord(
            id=SourceId("doc-1"),
            uri="file:///doomed.txt",
            content_hash="abc",
            indexed_at=datetime.now(UTC),
            pipeline="base",
        )
    )

    # Act
    removed = await store.delete_source(SourceId("doc-1"))

    # Assert
    assert removed.node_count == 1
    assert await store.count() == 1
    assert await store.get_source(SourceId("doc-1")) is None


# Task 21.0 — what the text arm does about passage length, and who gets to choose.
#
# `12-roadmap.md` §4 is this phase's citation recovery: the numbers that prompted Phase 21a are
# traceable from nothing Weft cites, and what survived checking is this. `_search_text_sql` called
# `ts_rank_cd(content_tsv, query)` with no third argument, so Postgres applied its documented
# default of `0` — no length normalisation — and nothing in `weft.toml` could say otherwise. That
# is `01` requirement 6 failing in the small: a shipped technique that is not parameterisable.
#
# **The default does not move here.** It is pinned to `0`, which is what every existing corpus was
# ranked with, and `21.2`'s sweep on Weft's own corpus is what would earn a change — `12`'s own
# standing rule, and the reason this task is parameterisation alone.


def _one_alpha_short() -> Node:
    """Three words, one of them the term. Measured against `pgvector/pgvector:pg16`."""
    return _node("alpha beta gamma")


def _one_alpha_long() -> Node:
    """Sixty-one words, one of them the term — the same match, sixty times the haystack."""
    return _node("alpha " + "filler " * 60)


async def test_the_default_normalisation_leaves_passage_length_invisible(
    store: PgVectorStore,
) -> None:
    """The defect, stated as the behaviour rather than as the missing argument.

    Measured directly against the container before this test was written: with normalization `0`,
    `ts_rank_cd` scores both of these **0.1** — a three-word passage and a sixty-one-word passage
    carrying the same single term are indistinguishable, and which one a reader sees first is
    decided by the `id` tiebreak. That is what every corpus indexed before this task was ranked
    with, which is why the default stays here and moves only if `21.2` earns it.
    """
    # Arrange
    short = _one_alpha_short()
    long = _one_alpha_long()
    await store.add([short, long])

    # Act
    results = await store.search_text("alpha", top_k=5)

    # Assert — equal scores, so length contributed nothing.
    assert {scored.value.id for scored in results} == {short.id, long.id}
    assert results[0].score == results[1].score


async def test_a_length_normalising_setting_reaches_the_query_and_reorders_it() -> None:
    """The value's whole job is to travel from `[packs.store]` to a `ts_rank_cd` call.

    `L9.79`: where that is a value's only job, one test must read it off the far end, or the wire
    is untested along its length. Reading it off `PgVectorSettings` would assert that pydantic
    stores what it is given.

    Normalization `2` is Postgres's *"divides the rank by the document length"*. Against the same
    two passages it scores the short one `0.0333` and the long one `0.0016` — an order the default
    cannot produce at all, because the default scores them equal.
    """
    # Arrange — a store of its own, because the setting is what is under test.
    reason = await _database_reachable()
    if reason is not None:
        pytest.skip(reason)
    instance = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(_DSN), text_rank_normalization=2),
    )
    await instance.count()
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
    await conn.close()
    short = _one_alpha_short()
    long = _one_alpha_long()

    # Act
    try:
        await instance.add([short, long])
        results = await instance.search_text("alpha", top_k=5)
    finally:
        await instance.aclose()

    # Assert — the shorter passage first, and strictly, which the default could not produce.
    assert [scored.value.id for scored in results] == [short.id, long.id]
    assert results[0].score > results[1].score


def test_a_normalisation_postgres_does_not_define_is_refused_by_name() -> None:
    """Postgres documents six bits, so `0..63` is every combination and `64` is not one.

    Refused at settings validation, which is where `weft_kernel.discovery` turns a bad pack
    settings block into a `failed` `PackReport` naming the pack and the field — the same loud
    answer `text_search_config` already gets for a configuration name Postgres does not hold.
    """
    # Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        PgVectorSettings(dsn=SecretStr(_DSN), text_rank_normalization=64)

    assert "text_rank_normalization" in str(excinfo.value)


# --- task 21.6: BM25 is a mode a user selects ------------------------------------------------
#
# `12-roadmap.md` §5g. `TextSearch.search_text` promises *ranked text search* and has never
# promised BM25: `content_tsv` is ranked by `ts_rank_cd`, which has no IDF over the collection,
# no term saturation and — since `21.0` measured it — whatever length normalisation the operator
# selects. Real BM25 needs `timescale/pg_textsearch`, which needs PostgreSQL 17 or 18, which the
# floor container is not. So the capability is **selectable** and its absence is **loud**.
#
# **The refusal is the deliverable, and the floor container is what tests it.** Every other test
# in this file runs against `pgvector/pgvector:pg16`, which has no `pg_textsearch` — so the
# unhappy path is the one that runs everywhere, and the happy path needs
# `docker compose --profile bm25 up -d`. That is the right way round: an operator who has not
# opted in is the common case, and what they must never get is a text arm that quietly stopped
# being what they asked for.


def test_the_shipped_default_text_mode_is_postgres_full_text_search() -> None:
    """**The default does not move in this phase.** `21.9` is the measurement that would justify
    moving it, and until then an operator who configures nothing gets exactly what they got
    before this task existed."""
    # Arrange / Act
    settings = PgVectorSettings(dsn=SecretStr(_DSN))

    # Assert
    assert settings.text_mode is TextMode.FTS


def test_text_mode_is_an_enum_so_a_misspelling_is_refused_where_it_is_typed() -> None:
    """`Enum` over `Literal`, per this project's own rule, and the refusal lands in `weft.toml`
    rather than at the first query."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError) as excinfo:
        PgVectorSettings(dsn=SecretStr(_DSN), text_mode="bm-25")  # type: ignore[arg-type]

    assert "text_mode" in str(excinfo.value)


async def test_selecting_bm25_where_the_extension_is_absent_refuses_naming_it(
    fresh_database: str,
) -> None:
    """The failure this task exists to prevent is the silent one.

    Without this, a `text_mode = "bm25"` against the floor container has three plausible wrong
    behaviours and every one of them is worse than a crash: fall back to `ts_rank_cd` and report
    BM25 numbers that are not BM25, return nothing and look like an empty corpus, or fail with
    Postgres's own `operator does not exist: text <@> ...`, which names neither the setting nor
    the fix. `01` requirement 5: say what was wanted, why it is unavailable, and what the options
    are.
    """
    # Arrange — the floor image, which ships pgvector and no pg_textsearch.
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database), text_mode=TextMode.BM25))

    # Act
    with pytest.raises(Bm25NotAvailableError) as caught:
        await store.count()

    # Assert — the extension, and each of the three ways out.
    message = str(caught.value)
    assert "pg_textsearch" in message
    assert "bm25" in message
    assert "fts" in message, "the deliberate full-text alternative is named, not implied"
    assert "qdrant" in message.lower(), "the second store is one of the three routes"


async def test_the_default_mode_never_probes_for_an_extension_it_does_not_need(
    fresh_database: str,
) -> None:
    """An operator who did not ask for BM25 must not be told about it.

    This is the other half of the refusal above and the half that would rot silently: a probe
    written unconditionally would make every `fts` store pay a query it has no use for, and — far
    worse — a probe that *raised* unconditionally would make the floor container unusable. The
    assertion is that provisioning completes, which it cannot do if the check is misplaced.
    """
    # Arrange
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))

    # Act
    count = await store.count()

    # Assert
    assert count == 0
    await store.aclose()


def test_the_bm25_refusal_is_not_in_the_unresolved_name_family() -> None:
    """**Measured against `test_ff12_unresolvable_name_carries_options.py`'s own family, and this
    is a decision rather than an omission.** Every member of that family carries `valid_options`
    naming what the operator could have typed instead. Here `bm25` *is* a valid value of
    `text_mode` — it is the database that cannot serve it — so `valid_options` would have to
    name the very thing that was just asked for. The three alternatives this refusal does name
    are **deployment** choices, not values of this setting, and a plain `WeftError` reaches
    `OPERATION_FAILED` through `exit_code_for`'s default branch: *"something failed"*, which is
    the footing `TextSearchConfigMismatchError` already stands on.
    """
    # Arrange / Act / Assert
    assert issubclass(Bm25NotAvailableError, WeftError)
    assert not issubclass(Bm25NotAvailableError, UnresolvedNameError)


# --- task 21.7: the bm25 mode actually ranks by BM25 ------------------------------------------
#
# **These need a database the floor container is not**, so they skip exactly the way the Qdrant
# suite already does — `docker compose --profile bm25 up -d`, port 5434. CI runs the floor image
# and no BM25 service, so these skip there, and `WEFT_TEST_EXPECTED_SKIPS` carries the count. That
# is the established shape for an opt-in backend in this tree, not a new one.

_BM25_DSN = os.environ.get("WEFT_BM25_DATABASE_URL", "postgresql://weft:weft@localhost:5434/weft")


async def _bm25_database_reachable() -> str | None:
    """`None` when a `pg_textsearch`-carrying database answers, else the reason to skip."""
    try:
        conn = await psycopg.AsyncConnection.connect(_BM25_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"no BM25 database at {_BM25_DSN} (docker compose --profile bm25 up -d): {exc}"
    await conn.close()
    return None


@pytest.fixture
async def bm25_database() -> AsyncIterator[str]:
    """A never-provisioned database on the BM25 server, dropped again afterwards.

    Its own database for `fresh_database`'s reason one server over: the BM25 index is built at
    provisioning from `text_search_config`, so a test about what that index *is* cannot share one
    with a test that already built it under different settings.
    """
    reason = await _bm25_database_reachable()
    if reason is not None:
        pytest.skip(reason)
    name = f"weft_bm25_probe_{uuid4().hex[:12]}"
    admin = await psycopg.AsyncConnection.connect(_BM25_DSN, autocommit=True)
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        yield f"{_BM25_DSN.rsplit('/', 1)[0]}/{name}"
    finally:
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


async def _bm25_store(dsn: str, nodes: Sequence[Node]) -> PgVectorStore:
    """A provisioned `bm25` store holding `nodes`."""
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn), text_mode=TextMode.BM25))
    await store.add(nodes)
    return store


async def test_a_bm25_score_is_higher_is_better_like_every_other_score_in_this_tree(
    bm25_database: str,
) -> None:
    """**The fidelity assertion, and it is measured rather than assumed.**

    `pg_textsearch`'s own operator returns a *negative* score so that ascending order puts the best
    match first: on a three-row probe on 2026-09-13 the best match scored `-1.47`, the next
    `-0.73`, and a row matching nothing scored `0`. `Scored.score` means higher-is-better
    everywhere else in this tree — `weft_retrieve.fusion` sums it, `weft_cli` ranks by it — so the
    adapter converts at its own boundary. Shipping the native sign would invert every ranking that
    touched this arm and raise nothing at all.
    """
    # Arrange
    store = await _bm25_store(
        bm25_database,
        [
            _node("the microkernel knows nothing about pdfs chunking embeddings or graphs"),
            _node("every capability is a plugin discovered through python entry points"),
            _node("pipelines are data derivable from other pipelines"),
        ],
    )

    # Act
    try:
        results = await store.search_text("plugin capability", top_k=3)
    finally:
        await store.aclose()

    # Assert
    assert results, "a matching corpus returns matches"
    assert results[0].value.content.startswith("every capability")
    scores = [hit.score for hit in results]
    assert scores == sorted(scores, reverse=True), "descending, like every other ranking here"
    assert all(score >= 0.0 for score in scores), (
        "the native operator is negative-and-ascending; an unconverted score would be every one "
        "of these below zero and the ordering inverted"
    )
    assert scores[0] > 0.0, "the best match scores above the floor rather than at it"


async def test_bm25_weighs_a_rare_term_above_one_every_document_carries(
    bm25_database: str,
) -> None:
    """**This is the assertion that says BM25 rather than `ts_rank_cd`, and nothing else here
    does.** Postgres's rankers have no collection statistics at all — its own documentation says
    so — so a word in every document counts for exactly as much as a word in one. BM25's IDF is
    the difference: with three documents, a term in all three carries `ln(0.5/3.5 + 1) ≈ 0.13` and
    a term in one carries `ln(2.5/1.5 + 1) ≈ 0.98`, about seven times the weight.

    Asserted as a **comparison between two queries against one corpus**, never against a literal:
    the constant depends on the corpus size and the parameters, and pinning it would make this a
    test of this database's tuning rather than of whether IDF is being applied at all.
    """
    # Arrange — 'shared' is in all three; 'sporadic' is in exactly one.
    store = await _bm25_store(
        bm25_database,
        [
            _node("shared shared sporadic vocabulary"),
            _node("shared shared shared ordinary vocabulary"),
            _node("shared shared shared other vocabulary"),
        ],
    )

    # Act
    try:
        ubiquitous = await store.search_text("shared", top_k=3)
        rare = await store.search_text("sporadic", top_k=3)
    finally:
        await store.aclose()

    # Assert
    assert ubiquitous and rare
    assert rare[0].score > ubiquitous[0].score, (
        "a term one document has must outweigh a term every document has — that is IDF, and it "
        "is the thing ts_rank_cd has no way to compute"
    )


async def test_bm25_narrows_by_a_filter_rather_than_filtering_a_global_top_k(
    bm25_database: str,
) -> None:
    """The review's own words: *"do not fetch a global lexical top-k and apply tenant filters
    afterwards."* A post-filter returns fewer than `top_k` results for a reason the caller cannot
    see, and at a large corpus returns nothing at all while matching rows exist."""
    # Arrange — the *stronger* lexical match is the one the filter excludes, so a post-filter
    # over a global top-k and a predicate inside the ranking give different answers here.
    wanted = _node("plugin capability", sources=frozenset({SourceId("keep")}))
    louder = _node(
        "plugin plugin plugin capability capability", sources=frozenset({SourceId("drop")})
    )
    store = await _bm25_store(bm25_database, [wanted, louder])

    # Act
    try:
        unfiltered = await store.search_text("plugin capability", top_k=5)
        narrowed = await store.search_text(
            "plugin capability",
            top_k=5,
            filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value="keep"),
        )
    finally:
        await store.aclose()

    # Assert
    assert len(unfiltered) == 2
    assert unfiltered[0].value.content == louder.content, "unfiltered, the louder one wins"
    assert [scored.value.content for scored in narrowed] == [wanted.content]


async def test_nothing_matching_is_an_empty_ranking_rather_than_a_failure(
    bm25_database: str,
) -> None:
    """`TextSearch`'s own emptiness rule: *"a store whose index holds nothing matching returns an
    empty sequence; that is the honest answer, and it is a different fact from a store that could
    not look, which raises."* `21.6`'s refusal is the second case; this is the first."""
    # Arrange
    store = await _bm25_store(bm25_database, [_node("pipelines are data")])

    # Act
    try:
        results = await store.search_text("xenopsychology", top_k=5)
    finally:
        await store.aclose()

    # Assert
    assert results == []


def test_the_store_says_which_ranking_its_text_score_came_from() -> None:
    """**Task `21.1`'s rule, which `21.7` would otherwise silently break.**

    `weft_cli.explain` prints a score only with its meaning, read off whatever produced it — and
    the meaning is a fixed sentence naming `ts_rank_cd`. A store switched to `bm25` returning that
    sentence would be `--explain` stating, in the engine's own voice, a fact about a ranking it did
    not run. The sentence is a property of the configured mode, not of the class.
    """
    # Arrange
    fts = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN)))
    bm25 = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN), text_mode=TextMode.BM25))

    # Assert
    assert "ts_rank_cd" in fts.text_score_semantics
    assert "bm25" in bm25.text_score_semantics.lower()
    assert "ts_rank_cd" not in bm25.text_score_semantics
