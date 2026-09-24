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
from typing import Any, cast
from uuid import uuid4

import psycopg
import pytest
from pgvector.psycopg import register_vector_async
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
    VectorIndexKind,
    VectorPrecision,
    VectorSearch,
)
from weft_store.pgvector_store import (
    Bm25NotAvailableError,
    DiskannNotAvailableError,
    IterativeScan,
    MixedVectorWidthError,
    PgVectorSettings,
    PgVectorStore,
    TextMode,
    TextQueryMode,
    TextRank,
    TextSearchConfigMismatchError,
    UnknownTextSearchConfigError,
    UnsupportedIndexKindError,
    UnsupportedPrecisionError,
    VectorWidthMismatchError,
    reject_width_over_index_ceiling,
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
        # G22 commits the column to the first embedding's width, and that survives a
        # TRUNCATE. This file's tests use 2- and 3-component vectors against one shared
        # database, so the width goes back to bare here or whichever test ran first would
        # refuse every later one by name.
        await cur.execute("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector")
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


async def test_a_search_repeated_on_one_connection_is_never_planned_generically(
    store: PgVectorStore,
) -> None:
    """Repair R38.7: a generic plan misestimates a `tsquery`'s matches by orders of magnitude.

    Repair R38.7. psycopg prepares a statement on its fifth execution and Postgres may then
    switch it to one generic plan, which for a `tsquery` cannot know how many rows the words
    match: over 189,523 Open RAGBench chunks it estimated 948 matches for a question matching
    ~150,000, and each lexical search went from 373 ms to 1,880 ms once `R38.6` gave a scored
    run one connection. Read from the store's own session, because a plan cache is per session.
    """
    # Arrange
    await store.add([_node("mutual information redundancy criterion"), _node("the cat sat")])
    for question in ("mutual redundancy", "cat", "the criterion", "information", "sat", "mat"):
        await store.search_text(question, top_k=5)
        await store.search_text(question, top_k=5)

    # Act
    connection = cast(psycopg.AsyncConnection[dict[str, Any]], vars(store)["_conn"])
    async with connection.cursor() as cur:
        await cur.execute(
            "SELECT coalesce(sum(generic_plans), 0) AS generic FROM pg_prepared_statements"
        )
        row = await cur.fetchone()

    # Assert
    assert row is not None
    assert row["generic"] == 0, f"{row['generic']} executions used a generic plan"


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
    """Cover density and frequency answer different questions.

    Which one a corpus wants is not knowable from here. Measured on this container: 0.2 against
    0.06079271 for the row below.
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
    """Changing the text-search configuration on an existing column is refused.

    `ADD COLUMN IF NOT EXISTS` no-ops on an existing column, so changing the setting later
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
        # G22 commits the column to the first embedding's width, and that survives a
        # TRUNCATE. This file's tests use 2- and 3-component vectors against one shared
        # database, so the width goes back to bare here or whichever test ran first would
        # refuse every later one by name.
        await cur.execute("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector")
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
    """`text_mode` defaults to `fts`, so an unconfigured store ranks text exactly as before.

    **The default does not move in this phase.** `21.9` is the measurement that would justify
    moving it, and until then an operator who configures nothing gets exactly what they got
    before this task existed.
    """
    # Arrange / Act
    settings = PgVectorSettings(dsn=SecretStr(_DSN))

    # Assert
    assert settings.text_mode is TextMode.FTS


def test_text_mode_is_an_enum_so_a_misspelling_is_refused_where_it_is_typed() -> None:
    """A misspelt `text_mode` fails `PgVectorSettings` validation, naming the field, before a query.

    `Enum` over `Literal`, per this project's own rule, and the refusal lands in `weft.toml`
    rather than at the first query.
    """
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
    """Measured against FF12's family: a decision rather than an omission.

    **Measured against `test_ff12_unresolvable_name_carries_options.py`'s own family, and this
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
# and no BM25 service, so these skip there as `SkipCause.BM25_UNREACHABLE`. That
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
    """**The fidelity assertion, and it is measured rather than assumed**.

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
    """IDF is applied: a rare term outscores a ubiquitous one, which `ts_rank_cd` cannot do.

    **This is the assertion that says BM25 rather than `ts_rank_cd`, and nothing else here
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
    """The review's own words: tenant filters are applied in the query, not afterwards.

    The review's own words: *"do not fetch a global lexical top-k and apply tenant filters
    afterwards."* A post-filter returns fewer than `top_k` results for a reason the caller cannot
    see, and at a large corpus returns nothing at all while matching rows exist.
    """
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
    """`TextSearch`'s own emptiness rule: nothing matching is an empty sequence.

    `TextSearch`'s own emptiness rule: *"a store whose index holds nothing matching returns an
    empty sequence; that is the honest answer, and it is a different fact from a store that could
    not look, which raises."* `21.6`'s refusal is the second case; this is the first.
    """
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
    """**Task `21.1`'s rule, which `21.7` would otherwise silently break**.

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


# --- G22: the width is committed at first write -------------------------------------------------
#
# Settled 2026-09-16 as position 1 (`docs/internal/05-grilling-sessions.md` → G22): the store learns
# `n` from the first embedded node it is handed, types the column to `vector(n)`, records the width,
# and thereafter refuses a node of any other width by name. These tests pin that behaviour, and each
# needs a database that has never been provisioned — a width is only *learned* once.


async def _column_width(dsn: str) -> int | None:
    """The declared width of `weft_nodes.embedding`, or `None` while the column is still bare.

    `atttypmod` rather than a row's `vector_dims`: the question is what the *column* was declared
    as, which an empty table still answers and a row-level function cannot.
    """
    conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT atttypmod FROM pg_attribute
                WHERE attrelid = 'weft_nodes'::regclass AND attname = 'embedding'
                """
            )
            row = await cur.fetchone()
    finally:
        await conn.close()
    if row is None:
        return None
    return None if int(row[0]) < 0 else int(row[0])


def _embedded(content: str, width: int) -> Node:
    return _node(content).with_embedding(Vector(values=tuple(0.1 for _ in range(width))))


async def test_the_first_embedded_node_types_the_column_and_the_store_records_that_width(
    fresh_database: str,
) -> None:
    # Arrange — a database that has never been written to: the width is not known yet.
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))
    await store.count()

    # Act
    assert await _column_width(fresh_database) is None
    await store.add([_embedded("first", 1536)])

    # Assert — the column carries the width, and the store answers with the same number.
    assert await _column_width(fresh_database) == 1536
    assert await store.committed_width() == 1536
    await store.aclose()


async def test_a_node_of_another_width_is_refused_by_name_once_the_width_is_committed(
    fresh_database: str,
) -> None:
    # Arrange
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))
    await store.add([_embedded("first", 1536)])

    # Act / Assert — Qdrant's shape: the node, both widths, and what to do about it.
    with pytest.raises(VectorWidthMismatchError) as raised:
        await store.add([_embedded("second", 64)])
    message = str(raised.value)
    assert "64" in message
    assert "1536" in message
    assert raised.value.pack == "weft-store"
    assert await store.count() == 1
    await store.aclose()


async def test_a_table_already_holding_two_widths_is_refused_with_both_numbers(
    fresh_database: str,
) -> None:
    # Arrange — the confident-nonsense case, written behind the store's back into a bare column.
    conn = await psycopg.AsyncConnection.connect(fresh_database, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # After the extension, never before: the adapter looks the type up in this database's
    # own catalogue, and a fresh database has no `vector` type until the statement above.
    await register_vector_async(conn)
    async with conn.cursor() as cur:
        await cur.execute(
            "CREATE TABLE weft_nodes (id TEXT PRIMARY KEY, parents TEXT[] NOT NULL, "
            "sources TEXT[] NOT NULL, content TEXT NOT NULL, media_type TEXT NOT NULL, "
            "embedding VECTOR, ext JSONB NOT NULL)"
        )
        for node_id, width in (("a", 64), ("b", 1536)):
            await cur.execute(
                "INSERT INTO weft_nodes VALUES (%s, '{}', '{}', 'x', 'text/plain', %s, '{}')",
                (node_id, list(Vector(values=tuple(0.1 for _ in range(width))).values)),
            )
    await conn.close()
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))

    # Act / Assert — refused with both widths, and never migrated.
    with pytest.raises(MixedVectorWidthError) as raised:
        await store.add([_embedded("third", 1536)])
    message = str(raised.value)
    assert "64" in message
    assert "1536" in message
    assert await _column_width(fresh_database) is None


# --- Task 31.9 — the index kind is configuration, and its unsafe default is the backend's own ---


async def _index_definitions(dsn: str) -> list[str]:
    """Every index definition on `weft_nodes`, read from the database's own catalogue.

    `pg_indexes` rather than a flag this store sets: the question is what the *database* holds,
    which is the only side of it a caller's search actually meets.
    """
    conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'weft_nodes'")
            return [str(row[0]) for row in await cur.fetchall()]
    finally:
        await conn.close()


def test_the_index_kind_defaults_to_the_exact_scan_this_store_has_always_done() -> None:
    # Arrange / Act
    settings = PgVectorSettings(dsn=SecretStr(_DSN))

    # Assert — `exact` is what every release before this task served, so the default changing
    # would silently re-index every existing corpus on its next connection.
    assert settings.index is VectorIndexKind.EXACT


def test_pgvector_now_serves_every_index_kind_the_vocabulary_names() -> None:
    """**Superseded at task 31.11, and the supersession is the point**.

    This test asserted that `diskann` is refused at settings validation — task `31.9`'s
    behaviour, with its own comment already anticipating that `31.11` would change it. `31.11`
    moved that refusal *out of the settings and into the database*, because whether `diskann`
    works is a fact about the deployment rather than about `weft.toml`, so the old assertion and
    the new one were mutually exclusive: no implementation could satisfy both.

    What replaces it records the consequence honestly. pgvector now serves **every** member of
    `VectorIndexKind`, so `_reject_unsupported_index` has nothing left to refuse and **cannot
    fire today**. The validator stays for a member added to the shared vocabulary later, on the
    same footing as Qdrant's `UnsupportedPrecisionError` — defined for the shape, unreachable
    until the vocabulary grows — and this assertion is what makes that claim checkable rather
    than assumed. It fails the moment a member is added that this backend has no answer for,
    which is exactly when somebody needs to decide what that answer is.
    """
    # Arrange / Act — every kind constructs; none is refused at settings validation.
    for kind in VectorIndexKind:
        assert PgVectorSettings(dsn=SecretStr(_DSN), index=kind).index is kind

    # Assert — and the refusal machinery is still there, for a member that does not exist yet.
    assert issubclass(UnsupportedIndexKindError, UnresolvedNameError)


def test_iterative_scan_defaults_to_relaxed_order_because_off_loses_rows_silently() -> None:
    """Phase 29 `29.7`: the default stays `relaxed_order`, since `off` loses filtered rows silently.

    Phase 29 `29.7`, on 100,142 real chunks: at 0.1% selectivity `hnsw.iterative_scan = off`
    returns recall@10 **0.003** — a mean of 0.03 rows out of 10 — while `relaxed_order` recovers
    0.8895. `off` is pgvector's own default, so inheriting the backend's default here is the one
    choice that makes a filtered search quietly wrong. This assertion is the whole point of the
    task: it fails if anyone ever "simplifies" the default back to the backend's.
    """
    # Arrange / Act
    settings = PgVectorSettings(dsn=SecretStr(_DSN))

    # Assert
    assert settings.iterative_scan is IterativeScan.RELAXED_ORDER


async def test_an_hnsw_store_builds_its_index_once_the_column_has_a_width(
    fresh_database: str,
) -> None:
    # Arrange — HNSW cannot be built on a bare `vector` column, and G22 leaves the column bare
    # until the first embedded node commits a width. So the index cannot be provisioned at
    # connection time; it has to follow the width.
    store = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), index=VectorIndexKind.HNSW)
    )
    await store.count()
    assert await _column_width(fresh_database) is None
    assert not [d for d in await _index_definitions(fresh_database) if "hnsw" in d.lower()]

    # Act — the first embedded node types the column, and the index follows it.
    await store.add([_embedded("first", 3)])

    # Assert
    assert await _column_width(fresh_database) == 3
    hnsw = [d for d in await _index_definitions(fresh_database) if "hnsw" in d.lower()]
    assert hnsw, (
        f"no hnsw index was built; weft_nodes holds {await _index_definitions(fresh_database)}"
    )
    await store.aclose()


async def test_an_exact_store_builds_no_vector_index_at_all(fresh_database: str) -> None:
    # Arrange / Act — the default must not start building indexes on existing corpora.
    store = PgVectorStore(PgVectorSettings(dsn=SecretStr(fresh_database)))
    await store.add([_embedded("first", 3)])

    # Assert
    definitions = await _index_definitions(fresh_database)
    assert not [d for d in definitions if "hnsw" in d.lower()]
    await store.aclose()


async def test_a_filtered_search_under_hnsw_still_returns_top_k(fresh_database: str) -> None:
    """The property the task is named for, and the one `29.7` measured failing.

    The corpus is deliberately larger than `top_k` by a wide margin with a filter matching a
    small slice of it, because that is the shape where `iterative_scan = off` returns a short
    list: pgvector scans a fixed candidate set *before* the filter is applied, so a selective
    filter can leave almost nothing behind, with no error to notice it by.
    """
    # Arrange
    store = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), index=VectorIndexKind.HNSW)
    )
    wanted = SourceId("wanted")
    nodes = [
        _node(f"filler {i}", sources=frozenset({SourceId("other")})).with_embedding(
            Vector(values=(float(i % 7), float(i % 5), 1.0))
        )
        for i in range(400)
    ] + [
        _node(f"match {i}", sources=frozenset({wanted})).with_embedding(
            Vector(values=(1.0, 1.0, float(i)))
        )
        for i in range(40)
    ]
    await store.add(nodes)

    # Act
    ranked = await store.search_vector(
        Vector(values=(1.0, 1.0, 1.0)),
        top_k=10,
        filter=Filter(op=FilterOp.CONTAINS, field="lineage.sources", value=str(wanted)),
    )

    # Assert — ten asked for, forty match, ten returned.
    assert len(ranked) == 10
    assert all(str(wanted) in scored.value.lineage.sources for scored in ranked)
    # Relaxed ordering lets pgvector return rows slightly out of distance order, and this store
    # ranks by score everywhere else, so the ordering is restored before anything is handed back.
    assert [scored.score for scored in ranked] == sorted(
        (scored.score for scored in ranked), reverse=True
    )
    await store.aclose()


# --- Task 31.10 — compressed indexes, rescored at full precision ------------------------------


async def _index_definitions_in(dsn: str) -> list[str]:
    """Every index definition on `weft_nodes`, from the database's own catalogue."""
    conn = await psycopg.AsyncConnection.connect(dsn, autocommit=True)
    try:
        async with conn.cursor() as cur:
            await cur.execute("SELECT indexdef FROM pg_indexes WHERE tablename = 'weft_nodes'")
            return [str(row[0]) for row in await cur.fetchall()]
    finally:
        await conn.close()


def test_the_precision_defaults_to_float32_until_a_run_moves_it() -> None:
    # Arrange / Act / Assert — the owner's Q2 rule: a compressed arm becomes the default only
    # through a commit citing a persisted `weft eval` run whose recall@10 lands inside the
    # float32 baseline's interval. `29.8` is a store-level measurement, not that run.
    assert PgVectorSettings(dsn=SecretStr(_DSN)).precision is VectorPrecision.FLOAT32


def test_rescore_oversampling_defaults_to_the_factor_that_stopped_paying() -> None:
    """Rescore oversampling defaults to four, where recall@10 stopped improving.

    `29.8` on 100,142 real chunks, binary quantisation, recall@10 against the exact scan:

    | oversampling | 1 | 2 | 4 | 10 |
    |---|---|---|---|---|
    | recall@10 | 0.8075 | 0.9565 | **0.989** | 0.989 |

    Four is where the curve flattens — ten is *identical*, so every candidate past four is paid
    for and buys nothing measurable. That plateau is the whole argument for the number, and it is
    a measurement rather than a convention borrowed from a vendor's example.
    """
    # Arrange / Act / Assert
    assert PgVectorSettings(dsn=SecretStr(_DSN)).rescore_oversampling == 4


def test_a_precision_pgvector_cannot_index_is_refused_naming_what_it_serves() -> None:
    # Arrange / Act / Assert — pgvector's HNSW indexes `vector`, `halfvec` and `bit`, and has no
    # int8 form at all; Qdrant serves it as scalar quantization. The vocabulary is shared and the
    # subsets are not, which is exactly what the refusal exists to say out loud.
    with pytest.raises(UnsupportedPrecisionError) as raised:
        PgVectorSettings(dsn=SecretStr(_DSN), precision=VectorPrecision.INT8)

    message = str(raised.value)
    assert "int8" in message
    assert "pgvector" in message
    assert raised.value.valid_options == ("float32", "float16", "binary")


@pytest.mark.parametrize(
    ("precision", "ceiling"),
    [(VectorPrecision.FLOAT16, 4_000), (VectorPrecision.BINARY, 64_000)],
)
def test_a_width_past_the_compressed_index_ceiling_is_refused_by_name(
    precision: VectorPrecision, ceiling: int
) -> None:
    """Pgvector's own documented limits — `halfvec` 4,000 dimensions, `bit` 64,000.

    **This is a function rather than a settings validator because of G22.** Every other refusal
    this store makes is a `model_validator`; this one cannot be, because pgvector's width is
    *learned from the first embedded node* rather than configured — there is no `vector_size`
    field to validate against, and adding one to make the check convenient would reopen that gate.
    So the refusal fires where the width first becomes known, and the decision is lifted into a
    pure function so it is reachable without a database.
    """
    # Arrange / Act / Assert — one past the ceiling is refused, the ceiling itself is not.
    reject_width_over_index_ceiling(precision, ceiling)

    with pytest.raises(UnsupportedPrecisionError) as raised:
        reject_width_over_index_ceiling(precision, ceiling + 1)

    message = str(raised.value)
    assert str(ceiling) in message
    assert str(ceiling + 1) in message
    assert precision.value in message
    assert raised.value.valid_options == ("float32",)


def test_diskann_is_no_longer_refused_at_settings_validation() -> None:
    """Task **31.11** moves the `diskann` refusal from the settings to the database.

    `31.9` refused it at settings validation because this backend served nothing for it. That is
    now the wrong place: whether `diskann` works is a fact about **this deployment** — does its
    Postgres carry `vectorscale`? — and a setting that is valid on one database and not on another
    cannot honestly be refused by reading `weft.toml` alone. `Bm25NotAvailableError` already draws
    this exact line for `text_mode = "bm25"`, and this follows it.
    """
    # Arrange / Act / Assert — constructing the settings is fine; the deployment decides.
    assert PgVectorSettings(dsn=SecretStr(_DSN), index=VectorIndexKind.DISKANN).index is (
        VectorIndexKind.DISKANN
    )


async def test_diskann_on_a_database_without_vectorscale_is_refused_naming_the_way_out(
    fresh_database: str,
) -> None:
    """The refusal half of **31.11**, on the floor image — which genuinely has no `vectorscale`.

    Measured on the running container: `SELECT count(*) FROM pg_available_extensions WHERE name =
    'vectorscale'` returns **0**. So this is not a mocked absence; it is the deployment every
    developer of this project actually has, and the one an operator most likely hits.

    **Refused before any write**, like `Bm25NotAvailableError` and for the same reason: an
    extension that is not *available* cannot be created no matter what runs next, so asking the
    catalogue first is the honest question. Falling through would build no index and silently
    serve a sequential scan under a name that promises otherwise.
    """
    # Arrange
    store = PgVectorStore(
        PgVectorSettings(dsn=SecretStr(fresh_database), index=VectorIndexKind.DISKANN)
    )

    # Act / Assert — the first embedded write is where an index would be provisioned.
    with pytest.raises(DiskannNotAvailableError) as raised:
        await store.add([_embedded("first", 3)])

    message = str(raised.value)
    assert "vectorscale" in message
    # The way out is a compose profile, not a setting change — name it, or the operator is told
    # what is wrong and not what to do about it.
    assert "bm25" in message
    assert "hnsw" in message, "an operator staying on this image needs the alternative named"

    # And nothing was written: the refusal precedes the insert, so the corpus is untouched.
    assert await store.count() == 0
    await store.aclose()


def test_the_diskann_refusal_is_about_the_deployment_not_the_setting() -> None:
    # Arrange / Act / Assert — `Bm25NotAvailableError`'s own reasoning, applied one extension
    # over: every `UnresolvedNameError` carries `valid_options` naming what the operator could
    # have typed instead, and `diskann` *is* a valid `VectorIndexKind`. Naming `hnsw` as a
    # `valid_options` entry would say the setting was wrong when the deployment was.
    assert not issubclass(DiskannNotAvailableError, UnresolvedNameError)
    assert issubclass(DiskannNotAvailableError, WeftError)


def test_float32_carries_no_index_width_ceiling_at_all() -> None:
    # Arrange / Act / Assert — it builds no cast, so nothing bounds it. A width that would be
    # refused under either compressed precision passes here, which is what makes the ceiling a
    # property of the *compression* rather than of the store.
    reject_width_over_index_ceiling(VectorPrecision.FLOAT32, 100_000)


@pytest.mark.parametrize(
    ("precision", "operator_class"),
    [(VectorPrecision.FLOAT16, "halfvec_cosine_ops"), (VectorPrecision.BINARY, "bit_hamming_ops")],
)
async def test_a_compressed_store_builds_an_index_over_the_compressed_expression(
    fresh_database: str, precision: VectorPrecision, operator_class: str
) -> None:
    # Arrange — a compressed index is an *expression* index: the column stays full-precision
    # `vector(n)` and the index is built over a cast of it, which is what lets the rescore below
    # compare against the original vectors rather than the lossy ones.
    store = PgVectorStore(
        PgVectorSettings(
            dsn=SecretStr(fresh_database), index=VectorIndexKind.HNSW, precision=precision
        )
    )

    # Act — the first embedded node commits the width, and the index follows it (31.9's point).
    await store.add([_embedded("first", 3)])

    # Assert
    definitions = await _index_definitions_in(fresh_database)
    compressed = [d for d in definitions if operator_class in d]
    assert compressed, f"no {operator_class} index was built; weft_nodes holds {definitions}"
    await store.aclose()


async def test_a_compressed_search_is_rescored_against_the_full_precision_column(
    fresh_database: str,
) -> None:
    """The ranking a compressed store returns is the full-precision one.

    Binary quantisation alone gets recall@10 of 0.8075 (`29.8`); rescoring an oversampled
    candidate set against the original vectors is what lifts it to 0.989. So the score handed
    back must be the **full-precision** cosine, never the Hamming distance the index ranked by —
    otherwise the number means something different from every other score this store returns, and
    a caller comparing two backends' rankings is comparing two different quantities.
    """
    # Arrange — `near` is nearest in full precision; the others are placed so a 1-bit
    # quantisation of all four collapses them into the same corner of the space.
    store = PgVectorStore(
        PgVectorSettings(
            dsn=SecretStr(fresh_database),
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.BINARY,
        )
    )
    near = _node("near").with_embedding(Vector(values=(1.0, 0.9, 0.8)))
    mid = _node("mid").with_embedding(Vector(values=(1.0, 0.5, 0.4)))
    far = _node("far").with_embedding(Vector(values=(1.0, 0.1, 0.05)))
    await store.add([near, mid, far])

    # Act
    ranked = await store.search_vector(Vector(values=(1.0, 0.95, 0.85)), top_k=3)

    # Assert — full-precision order, and a cosine score rather than a bit distance.
    assert [scored.value.content for scored in ranked] == ["near", "mid", "far"]
    assert all(0.0 <= scored.score <= 1.0 for scored in ranked)
    await store.aclose()


async def test_the_query_plan_shows_the_compressed_index_is_the_one_used(
    fresh_database: str,
) -> None:
    """Postgres matches an expression index **textually** — this is the task's sharpest risk.

    A compressed search whose `ORDER BY` expression stops matching the index expression by so
    much as a cast silently falls back to a sequential scan: same results, same order, no error,
    and the entire point of building the index gone. Nothing about the returned rows can detect
    that, which is why this reads the plan rather than the output.
    """
    # Arrange
    store = PgVectorStore(
        PgVectorSettings(
            dsn=SecretStr(fresh_database),
            index=VectorIndexKind.HNSW,
            precision=VectorPrecision.BINARY,
        )
    )
    await store.add([_embedded(f"node-{i}", 3) for i in range(50)])

    # Act — the plan for the statement the store itself issues, not one rewritten by this test:
    # a copy would be a comparison whose two sides come from one source (`L5.6`).
    plan = await store.explain_search_vector(Vector(values=(0.1, 0.1, 0.1)), top_k=5)

    # Assert
    assert "weft_nodes_embedding_hnsw_idx" in plan, plan
    assert "Seq Scan" not in plan, plan
    await store.aclose()
