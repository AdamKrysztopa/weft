"""Tests for `weft_store.pgvector_store`, against a real Postgres + pgvector container.

Mirrors `packages/weft-store/src/weft_store/pgvector_store.py`. Per
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
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr, ValidationError

from weft_kernel.context import Context
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
    PgVectorSettings,
    PgVectorStore,
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
        await cur.execute("TRUNCATE weft_nodes, weft_sources")
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
    `weft_cli.registry_bootstrap.pack_settings_from_config` hands to `register()`.
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
