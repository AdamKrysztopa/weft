"""The store conformance kit — one suite, two backends, run against both real containers.

Ledger task **2.6**: "the store contract is satisfied by a second backend of a
genuinely different shape, so it is no longer a guess." A guess is what a
contract with one implementation is, and the only way to stop guessing is to
write the assertions *once* and make two engines that share no code answer them
identically. So every test below takes a `store` fixture it cannot identify:
parameterised over `pgvector` and `qdrant`, it asks the contract's questions and
never the backend's.

`01` → *Runtime shape* is what this discharges — "the contract is proven on
**pgvector and Qdrant**, which have genuinely different shapes, and a store that
only Postgres can satisfy fails that test just as loudly."

**The shapes really are different, and the suite is where that shows.** Postgres
stores a row per node, keyed by the node's own content digest, and can be asked
for text ranking. Qdrant stores a point keyed by a UUID (its ids are integers or
UUIDs, never a sha256 string), fixes a collection's vector width at creation,
holds source records in a second, vector-less collection, and offers no scored
lexical ranking at all. The one test below that names a backend is the one whose
subject *is* that asymmetry.

**Recorded rather than hidden: this is a repository asset, not a published one.** A third
party writing a store cannot import these assertions — they live under `tests/`, so they
are in no distribution, and adding a third backend means an entry in the `store` fixture's
parameters here rather than a factory of their own. `01` → *Runtime shape* names a
conformance kit and pack authors' unit tests as two consumers of the same **in-memory
store**; it does not settle whether the assertions themselves ship, and neither
`.phase2-design.md` nor any ledger task does. Publishing them would mean deciding what a
`weft_store.conformance` module may depend on — `weft_pdf`'s `ExtModel`, `weft_cli`'s run
assembler and `weft_retrieve`'s payload types are all imported below and none of them may
become a `weft-store` dependency. That is a design decision, and it is left as one.

**A third reason stood here and expired.** It read *"and what its own version means while G9 is
Open"* — and **G9 settled 2026-08-21**, four days after this docstring was written, with
per-contract semver bound to the distribution version. So that question has an answer and is no
longer a reason for anything; the two reasons above are the whole refusal. It stood for eight
phases, and `12-roadmap.md` inherited the refusal *by reference* in the meantime, which is how an
expired premise becomes load-bearing in a second document (`docs/internal/lessons.md` `L19.2`).

**Against the real containers, skipped with a reason when they are absent** —
`docs/06-phase-0-build.md` step 8's discipline, applied per backend rather than
per module, so an operator with only Postgres up still gets the pgvector half.
`docker compose up -d` brings Postgres; `docker compose --profile conformance up
-d qdrant` brings the other, which sits behind a profile because `compose.yaml`'s
opening line promises one container.

*(**Ledger task 26.4 moved the assertions out.** Twenty-five of the twenty-seven checks now live in
`weft_store.conformance`, published inside the `weft-rag` wheel so a third party writing a store can
import them — which is what four documents had promised and this file could not deliver. What stays
here is everything that is a claim about **this checkout** rather than about the contract: the two
containers, the DSNs, the collection setup and teardown, the skips, and the two tests whose subject
**is** the pgvector/Qdrant asymmetry. `L6.25` draws that line — `tests/integration` is about the
code and this half is about the environment it runs in.)*

"""

import os
from collections.abc import AsyncIterator, Sequence
from functools import partial
from typing import cast
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from weft_engine.run_services import StoreCapabilityMissingError, check_store_capabilities
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node, Outcome, Produced, SourceId, Vector
from weft_kernel.registry import Registry
from weft_kernel.runner import StageSpec
from weft_qdrant import QdrantSettings, QdrantStore
from weft_retrieve.contract import Retriever
from weft_retrieve.payload import Candidates, QuerySet
from weft_store.conformance import (
    OPERATOR_CASES,
    FilterableSearchableStore,
    FilterableStore,
    FilterableTextStore,
    ReconcilableStore,
    SearchableStore,
    SupersedableStore,
    TargetHoldingStore,
    TextSearchableStore,
    check_a_deleted_nodes_productions_do_not_outlive_it,
    check_a_derived_node_and_a_collided_one_are_told_apart_in_the_same_store,
    check_a_field_no_node_can_have_is_refused_by_name_on_either_backend,
    check_a_filter_reaches_vector_search_rather_than_being_ignored,
    check_a_filtered_search_returns_top_k_in_the_approximate_regime,
    check_a_fresh_store_has_one_live_target_named_default,
    check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext,
    check_a_node_two_documents_each_produced_whole_is_narrowed_not_deleted,
    check_a_node_written_twice_by_one_document_is_one_production_not_two,
    check_a_parent_id_nothing_derives_from_selects_nothing_rather_than_everything,
    check_a_parent_is_one_filter_away_from_its_child_on_either_backend,
    check_a_parents_children_within_an_ordinal_range_are_one_filter_away,
    check_a_source_record_belongs_to_the_target_it_was_written_into,
    check_a_source_record_round_trips_and_is_listed,
    check_a_target_is_created_by_its_first_write_and_isolated_from_every_other,
    check_a_target_name_outside_the_grammar_is_refused_by_name,
    check_add_merges_a_nodes_sources_rather_than_replacing_them,
    check_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend,
    check_claiming_an_identity_creates_the_target_as_a_first_write_does,
    check_delete_source_removes_exactly_the_nodes_carrying_it,
    check_deleting_a_failed_source_removes_it_like_any_other,
    check_deleting_the_last_document_that_produced_a_node_deletes_it,
    check_drop_refuses_a_target_that_does_not_exist_naming_those_that_do,
    check_drop_refuses_the_live_and_previous_targets_and_removes_another,
    check_estimate_counts_the_identical_tombstones_reconcile_itself_examines,
    check_estimate_reports_zero_model_calls_on_either_backend,
    check_every_operator_means_the_same_thing_to_both_backends,
    check_promote_makes_a_target_live_and_rollback_restores_the_previous_one,
    check_promote_refuses_a_target_that_does_not_exist_naming_those_that_do,
    check_reconcile_finishes_a_deletion_that_was_interrupted,
    check_reconcile_leaves_a_healthy_store_alone_on_either_backend,
    check_reconcile_neither_deletes_nor_clears_a_failed_source,
    check_rollback_with_nothing_to_roll_back_to_is_refused,
    check_scan_and_count_see_every_stored_node_whatever_order_a_backend_walks_in,
    check_search_text_answers_nothing_matching_with_an_empty_ranking,
    check_search_text_finds_the_node_that_carries_the_words,
    check_search_text_narrows_by_a_filter_rather_than_ignoring_it,
    check_search_vector_ranks_by_cosine_similarity_on_either_backend,
    check_supersede_is_idempotent_so_an_interrupted_one_can_be_retried,
    check_supersede_refuses_a_replacement_that_drops_a_source,
    check_supersede_replaces_a_node_and_leaves_its_neighbours_alone,
    check_the_first_embedding_identity_claimed_is_the_one_a_target_keeps,
    check_the_multimodal_facts_round_trip_through_every_store,
    check_writing_a_node_again_under_its_id_replaces_its_ext,
    conformance_corpus,
    register_conformance_ext_models,
)
from weft_store.contract import (
    Filter,
    MetadataFilter,
    NodeStore,
    TextSearch,
    VectorIndexKind,
    VectorSearch,
)
from weft_store.memory import MemoryStore
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore

_DSN = os.environ.get("WEFT_DATABASE_URL", "postgresql://weft:weft@localhost:5433/weft")
_QDRANT_URL = os.environ.get("WEFT_QDRANT_URL", "http://localhost:6333")


async def _postgres_unreachable() -> str | None:
    try:
        conn = await psycopg.AsyncConnection.connect(_DSN, connect_timeout=2)
    except psycopg.OperationalError as exc:
        return f"WEFT_DATABASE_URL ({_DSN}) is unreachable: {exc}. `docker compose up -d`."
    await conn.close()
    return None


async def _pgvector_store(index: VectorIndexKind = VectorIndexKind.EXACT) -> PgVectorStore:
    instance = PgVectorStore(PgVectorSettings(dsn=SecretStr(_DSN), index=index))
    await instance.count()  # provisions the schema through the public API
    conn = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with conn.cursor() as cur:
        await cur.execute("TRUNCATE weft_nodes, weft_sources, weft_node_productions")
        # G22 commits the column to the first embedding's width, and that survives a TRUNCATE.
        # This kit's corpus carries 3-component vectors and other checks use 2-component ones
        # against one shared database, so the width goes back to bare here or whichever check
        # ran first would refuse every later one by name.
        await cur.execute("ALTER TABLE weft_nodes ALTER COLUMN embedding TYPE vector")
    await conn.close()
    return instance


async def _qdrant_unreachable() -> str | None:
    client = AsyncQdrantClient(url=_QDRANT_URL, timeout=2)
    try:
        await client.info()
    except (OSError, ValueError, UnexpectedResponse, ResponseHandlingException) as exc:
        return (
            f"WEFT_QDRANT_URL ({_QDRANT_URL}) is unreachable: {exc}. "
            f"`docker compose --profile conformance up -d qdrant`."
        )
    finally:
        await client.close()
    return None


def _qdrant_settings() -> QdrantSettings:
    """A collection of its own per test, so two runs of this suite never share one."""
    return QdrantSettings(
        url=_QDRANT_URL, collection=f"weft_conformance_{uuid4().hex[:12]}", vector_size=3
    )


async def _drop(settings: QdrantSettings) -> None:
    """Delete both collections the store provisioned — the fixture's own cleanup.

    The test owns this rather than the store, exactly as
    `tests/unit/weft_store/test_pgvector_store.py` opens its own connection to
    truncate: a `drop()` on the store would be a destructive method that exists
    only because a test wanted one, and it would be reachable from a pipeline.
    """
    client = AsyncQdrantClient(url=settings.url)
    for name in (settings.collection, f"{settings.collection}__sources"):
        if await client.collection_exists(name):
            await client.delete_collection(name)
    await client.close()


async def _drop_targets(settings: QdrantSettings) -> None:
    """Delete every collection a target check can make under `settings.collection`, by name."""
    client = AsyncQdrantClient(url=settings.url)
    base = settings.collection
    names = [base, f"{base}__sources", f"{base}__targets"]
    for target in ("conformance_candidate", "conformance_other"):
        names += [f"{base}__t_{target}", f"{base}__t_{target}__sources"]
    for name in names:
        if await client.collection_exists(name):
            await client.delete_collection(name)
    await client.close()


#: The two backends *this checkout* provisions, and the fixture's own return type.
#:
#: **It stays a union of concrete classes, and that is the point of the split.** Every assertion
#: carried this annotation until task `26.4`, which made a stranger's store unable to satisfy the
#: type the checks were written against. The published kit in `weft_store.conformance` now names
#: protocols; this alias says what *these containers* hand back, which is a claim about the
#: environment and belongs here (`L6.25`).
type ConformanceStore = PgVectorStore | QdrantStore


register_conformance_ext_models()


@pytest.fixture(params=("pgvector", "qdrant"))
async def store(request: pytest.FixtureRequest) -> AsyncIterator[ConformanceStore]:
    """A provisioned, empty store of whichever backend this parameter names."""
    backend = cast(str, request.param)
    if backend == "pgvector":
        await _require_postgres()
        pg = await _pgvector_store()
        yield pg
        await pg.aclose()
        return
    await _require_qdrant()
    settings = _qdrant_settings()
    qdrant = QdrantStore(settings)
    yield qdrant
    await qdrant.aclose()
    await _drop(settings)


async def test_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(
    store: NodeStore,
) -> None:
    await check_a_node_round_trips_through_the_store_with_its_lineage_and_its_ext(store)


async def test_the_multimodal_facts_round_trip_through_every_store(store: NodeStore) -> None:
    await check_the_multimodal_facts_round_trip_through_every_store(store)


async def test_scan_and_count_see_every_stored_node_whatever_order_a_backend_walks_in(
    store: NodeStore,
) -> None:
    await check_scan_and_count_see_every_stored_node_whatever_order_a_backend_walks_in(store)


async def test_delete_source_removes_exactly_the_nodes_carrying_it(store: NodeStore) -> None:
    await check_delete_source_removes_exactly_the_nodes_carrying_it(store)


async def test_add_merges_a_nodes_sources_rather_than_replacing_them(store: NodeStore) -> None:
    await check_add_merges_a_nodes_sources_rather_than_replacing_them(store)


async def test_a_node_two_documents_each_produced_whole_is_narrowed_not_deleted(
    store: NodeStore,
) -> None:
    await check_a_node_two_documents_each_produced_whole_is_narrowed_not_deleted(store)


async def test_deleting_the_last_document_that_produced_a_node_deletes_it(store: NodeStore) -> None:
    await check_deleting_the_last_document_that_produced_a_node_deletes_it(store)


async def test_a_derived_node_and_a_collided_one_are_told_apart_in_the_same_store(
    store: NodeStore,
) -> None:
    await check_a_derived_node_and_a_collided_one_are_told_apart_in_the_same_store(store)


async def test_a_node_written_twice_by_one_document_is_one_production_not_two(
    store: NodeStore,
) -> None:
    await check_a_node_written_twice_by_one_document_is_one_production_not_two(store)


async def test_a_deleted_nodes_productions_do_not_outlive_it(store: NodeStore) -> None:
    await check_a_deleted_nodes_productions_do_not_outlive_it(store)


async def test_supersede_replaces_a_node_and_leaves_its_neighbours_alone(
    store: SupersedableStore,
) -> None:
    await check_supersede_replaces_a_node_and_leaves_its_neighbours_alone(store)


async def test_supersede_is_idempotent_so_an_interrupted_one_can_be_retried(
    store: SupersedableStore,
) -> None:
    await check_supersede_is_idempotent_so_an_interrupted_one_can_be_retried(store)


async def test_supersede_refuses_a_replacement_that_drops_a_source(
    store: SupersedableStore,
) -> None:
    await check_supersede_refuses_a_replacement_that_drops_a_source(store)


async def test_reconcile_finishes_a_deletion_that_was_interrupted(store: ReconcilableStore) -> None:
    await check_reconcile_finishes_a_deletion_that_was_interrupted(store)


async def test_reconcile_leaves_a_healthy_store_alone_on_either_backend(
    store: ReconcilableStore,
) -> None:
    await check_reconcile_leaves_a_healthy_store_alone_on_either_backend(store)


async def test_estimate_reports_zero_model_calls_on_either_backend(
    store: ReconcilableStore,
) -> None:
    await check_estimate_reports_zero_model_calls_on_either_backend(store)


async def test_estimate_counts_the_identical_tombstones_reconcile_itself_examines(
    store: ReconcilableStore,
) -> None:
    await check_estimate_counts_the_identical_tombstones_reconcile_itself_examines(store)


async def test_a_source_record_round_trips_and_is_listed(store: NodeStore) -> None:
    await check_a_source_record_round_trips_and_is_listed(store)


async def test_deleting_a_failed_source_removes_it_like_any_other(store: NodeStore) -> None:
    await check_deleting_a_failed_source_removes_it_like_any_other(store)


async def test_reconcile_neither_deletes_nor_clears_a_failed_source(
    store: ReconcilableStore,
) -> None:
    await check_reconcile_neither_deletes_nor_clears_a_failed_source(store)


async def test_search_vector_ranks_by_cosine_similarity_on_either_backend(
    store: SearchableStore,
) -> None:
    await check_search_vector_ranks_by_cosine_similarity_on_either_backend(store)


@pytest.mark.parametrize(
    ("label", "filter_", "expected"),
    OPERATOR_CASES,
    ids=[case[0] for case in OPERATOR_CASES],
)
async def test_every_operator_means_the_same_thing_to_both_backends(
    store: FilterableStore, label: str, filter_: Filter, expected: frozenset[str]
) -> None:
    await check_every_operator_means_the_same_thing_to_both_backends(
        store, label=label, filter_=filter_, expected=expected
    )


async def test_a_parent_is_one_filter_away_from_its_child_on_either_backend(
    store: FilterableStore,
) -> None:
    await check_a_parent_is_one_filter_away_from_its_child_on_either_backend(store)


async def test_a_parent_id_nothing_derives_from_selects_nothing_rather_than_everything(
    store: FilterableStore,
) -> None:
    await check_a_parent_id_nothing_derives_from_selects_nothing_rather_than_everything(store)


async def test_a_parents_children_within_an_ordinal_range_are_one_filter_away(
    store: FilterableStore,
) -> None:
    await check_a_parents_children_within_an_ordinal_range_are_one_filter_away(store)


async def test_writing_a_node_again_under_its_id_replaces_its_ext(store: FilterableStore) -> None:
    await check_writing_a_node_again_under_its_id_replaces_its_ext(store)


async def test_search_text_finds_the_node_that_carries_the_words(
    store: TextSearchableStore,
) -> None:
    await check_search_text_finds_the_node_that_carries_the_words(store)


async def test_search_text_answers_nothing_matching_with_an_empty_ranking(
    store: TextSearchableStore,
) -> None:
    await check_search_text_answers_nothing_matching_with_an_empty_ranking(store)


async def test_search_text_narrows_by_a_filter_rather_than_ignoring_it(
    store: FilterableTextStore,
) -> None:
    await check_search_text_narrows_by_a_filter_rather_than_ignoring_it(store)


async def test_a_filter_reaches_vector_search_rather_than_being_ignored(
    store: FilterableSearchableStore,
) -> None:
    await check_a_filter_reaches_vector_search_rather_than_being_ignored(store)


async def test_a_field_no_node_can_have_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    await check_a_field_no_node_can_have_is_refused_by_name_on_either_backend(store)


async def test_a_width_a_store_did_not_commit_to_is_refused_by_name_on_either_backend(
    store: NodeStore,
) -> None:
    """Both backends refuse a second width by name — G22, ledger `29.4`.

    **Here rather than in the published kit, and that is the honest place for it.** The kit's
    checks are what *any* `NodeStore` must satisfy, and `weft_store.memory.MemoryStore` — which
    `01` → *Runtime shape* specifies as "a dict with brute-force cosine", not a backend — has no
    column to type and no width to commit to. It accepted the node and failed the check when this
    lived there. Nor can `checks_for` gate it: every entry in `_CAPABILITY_OF` names a *method*
    that proves a capability, and both backends refuse through `add`, which every store has. So
    this is an assertion about the two persistent backends, which is what `fix-plans/05`'s *Done
    when* asks for — "both backends refuse a width mismatch the same way".

    **Neither backend shares an error class with the other**: `weft_qdrant` raises its own
    `VectorWidthMismatchError` and `weft_store` a sibling of the same name, and the packs do not
    import each other. So the assertion is over `WeftError` and over what both messages must
    carry, because an operator cannot act on a driver's "expected dim: 64, got 1536": the node
    refused, both widths, a remedy naming re-indexing, and the pack that refused it.
    """
    # Arrange — the corpus commits the store to 3 components, whatever the backend does with that.
    await store.add(conformance_corpus())
    wrong = Node.synthetic(
        content="wrong width",
        media_type=MediaType.TEXT,
        reason="G22 width refusal",
        sources=frozenset({SourceId("source-a")}),
    ).with_embedding(Vector(values=tuple(0.1 for _ in range(64))))

    # Act / Assert
    try:
        await store.add([wrong])
    except WeftError as exc:
        message = str(exc)
        assert str(wrong.id) in message, f"the refusal must name the node: {message!r}"
        assert "64" in message, f"the refusal must name the width offered: {message!r}"
        assert "3" in message, f"the refusal must name the width committed: {message!r}"
        assert "re-index" in message.lower(), f"it must say what to do: {message!r}"
        assert exc.pack, f"the refusal must name the pack that refused it: {exc.pack!r}"
    else:
        raise AssertionError(
            "a node of another width was accepted; both backends must refuse it by name, or a "
            "corpus silently holds vectors no search can rank against each other"
        )


async def test_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend(
    store: FilterableStore,
) -> None:
    await check_an_operator_a_field_cannot_carry_is_refused_by_name_on_either_backend(store)


class _HybridRetriever:
    """The `hybrid` shape: a retriever that will call both search arms, so it says so."""

    needs_store: tuple[type, ...] = (VectorSearch, TextSearch)

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        return Produced(value=Candidates(origin=payload.origin))


def _capabilities_of(store: object) -> frozenset[str]:
    """Which published search capabilities a store satisfies, by `isinstance` and nothing else.

    The whole mechanism in one function: no store writes a capability down, so this cannot read a
    declaration even if one existed.
    """
    return frozenset(
        name
        for name, protocol in (
            ("VectorSearch", VectorSearch),
            ("TextSearch", TextSearch),
            ("MetadataFilter", MetadataFilter),
        )
        if isinstance(store, protocol)
    )


async def _require_postgres() -> None:
    """Skip unless `WEFT_DATABASE_URL` is reachable — **the only Postgres skip in this file**.

    Hoisted at task **31.5**, which added a second fixture needing the same guard. One site per
    backend rather than one per consumer: repeating the three-line check would be two more
    `pytest.skip(` calls for one condition, and `.claude/hooks/guard_quality_gates.py` refuses
    that — rightly, since a suppression marker multiplying across a file is exactly how one stops
    being noticed.
    """
    reason = await _postgres_unreachable()
    if reason is not None:
        pytest.skip(reason)


async def _require_qdrant() -> None:
    """Skip unless `WEFT_QDRANT_URL` is reachable — **the only Qdrant skip in this file**."""
    reason = await _qdrant_unreachable()
    if reason is not None:
        pytest.skip(reason)


@pytest.fixture(params=("pgvector", "qdrant"))
async def approximate_store(request: pytest.FixtureRequest) -> AsyncIterator[ConformanceStore]:
    """A store of each backend configured into its **approximate** regime — task **31.5**.

    The `store` fixture hands back each backend at its default, and for both of them that default
    answers exactly: pgvector builds no vector index at all, and a Qdrant collection this small
    sits far below the optimizer's own indexing threshold. So every filtered check in this kit has
    only ever run where the answer is exact by construction — which is the gap this task exists
    for. `29.7` measured pgvector returning a mean of **0.03 rows out of 10** at 0.1% selectivity
    under `hnsw.iterative_scan = off`, and no check here could have seen it, because no check ever
    built an index.

    Both arms are configured to *index*, not merely to name a kind:

    - **pgvector** takes `index=hnsw` **on a database of its own**, created and dropped here. That
      is not tidiness: G22's width commitment is one-way and builds a permanent HNSW index, and
      `_pgvector_store`'s cleanup resets the shared table with `ALTER COLUMN embedding TYPE vector`
      — which Postgres refuses once an HNSW index sits on a fixed-width column (`InvalidParameter
      Value: column does not have dimensions`). Sharing the database would leave every later
      pgvector arm unable to reset, deterministically. The unit suite's own
      `fresh_database` fixture reached this conclusion first, and is the precedent.
    - **Qdrant** takes `indexing_threshold=1`, so its optimizer builds an HNSW segment rather than
      scanning exactly below the default of 20,000 points. **`0` is the wrong value** — Qdrant's
      own documentation defines it as *disabling* indexing — which is the trap this fixture exists
      to not fall into.
    """
    backend = cast(str, request.param)
    if backend == "pgvector":
        await _require_postgres()
        name = f"weft_conformance_{uuid4().hex[:12]}"
        admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
        async with admin.cursor() as cur:
            await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
        pg = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn), index=VectorIndexKind.HNSW))
        try:
            yield pg
        finally:
            await pg.aclose()
            async with admin.cursor() as cur:
                await cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
                )
            await admin.close()
        return
    await _require_qdrant()
    settings = _qdrant_settings().model_copy(update={"indexing_threshold": 1})
    qdrant = QdrantStore(settings)
    yield qdrant
    await qdrant.aclose()
    await _drop(settings)


async def test_a_filtered_search_returns_top_k_in_the_approximate_regime(
    approximate_store: FilterableSearchableStore,
) -> None:
    """The property `31.5` is named for, on backends where it can actually fail.

    A filtered search must return as many results as the caller asked for whenever that many
    stored nodes match the filter. Under an approximate index this is **not** free: pgvector picks
    its candidate set *before* applying the filter, so a selective filter can leave almost nothing
    behind and the search returns a short list with no error at all.
    """
    await check_a_filtered_search_returns_top_k_in_the_approximate_regime(approximate_store)


async def test_the_two_backends_advertise_different_capabilities_and_nobody_declared_them() -> None:
    # Arrange
    await _require_postgres()
    pg = await _pgvector_store()
    qdrant = QdrantStore(_qdrant_settings())

    # Act — `isinstance`, which is the whole mechanism: no store writes a capability down.
    # Neither instance is ever connected: a capability is a fact about a class, and asking a
    # deployment would make this test about whether a container was up.
    try:
        pg_capabilities = frozenset(
            name
            for name, protocol in (
                ("VectorSearch", VectorSearch),
                ("TextSearch", TextSearch),
                ("MetadataFilter", MetadataFilter),
            )
            if isinstance(pg, protocol)
        )
        qdrant_capabilities = frozenset(
            name
            for name, protocol in (
                ("VectorSearch", VectorSearch),
                ("TextSearch", TextSearch),
                ("MetadataFilter", MetadataFilter),
            )
            if isinstance(qdrant, protocol)
        )
    finally:
        await pg.aclose()
        await qdrant.aclose()

    # Assert — **both backends now satisfy all three, and that is the change ledger `21.8` made.**
    # This asserted `qdrant_capabilities == {"VectorSearch", "MetadataFilter"}` until 2026-09-13,
    # on the premise that Qdrant's text matching was a filter predicate rather than a scored
    # ranking. A named sparse vector with `modifier: idf` is a scored ranking, and Qdrant's own —
    # `docs/02-extension-model.md` §1 carries the withdrawal and says which premises expired.
    #
    # What this test still asserts is the mechanism rather than the asymmetry: **nobody declared
    # any of these**. Both sets are computed by `isinstance` against the published Protocols, and
    # the store that now carries the asymmetry is `MemoryStore` one test below.
    assert pg_capabilities == frozenset({"VectorSearch", "TextSearch", "MetadataFilter"})
    assert qdrant_capabilities == frozenset({"VectorSearch", "TextSearch", "MetadataFilter"})
    assert frozenset(_capabilities_of(MemoryStore())) == frozenset({"VectorSearch"}), (
        "a capability refusal needs a shipped store that lacks one, and since 21.8 this is it"
    )


async def test_a_hybrid_run_without_text_search_is_refused_before_any_stage_runs() -> None:
    """**This named `qdrant` until ledger `21.8` gave it a text arm.**

    The subject moved to `MemoryStore`, which satisfies `NodeStore` and `VectorSearch` and nothing
    else. `01` → *Runtime shape* is explicit that the in-memory store *"exists, and is not a
    backend"*, so this is a weaker demonstration than the one it replaces — `02` §1 records that
    as the price of the withdrawal rather than pretending it was an equal trade.
    """
    # Arrange — a real store, never connected: the refusal happens at run assembly, before any
    # stage runs, which is exactly before anything would have opened a connection.
    without_text = MemoryStore()
    registry = Registry()
    registry.add(Retriever, "hybrid", _HybridRetriever, distribution="weft-retrieve")
    registry.add(
        NodeStore,
        "pgvector",
        partial(PgVectorStore, PgVectorSettings(dsn=SecretStr(_DSN))),
        distribution="weft-store",
    )
    registry.add(NodeStore, "memory", MemoryStore, distribution="weft-rag")
    specs: Sequence[StageSpec] = (StageSpec(id="retrieve", contract=Retriever, name="hybrid"),)

    # Act / Assert — named, with where to get what is missing, and no degradation offered.
    with pytest.raises(StoreCapabilityMissingError) as raised:
        check_store_capabilities(
            specs,
            registry=registry,
            store=without_text,
            store_contract=NodeStore,
            store_name="memory",
        )
    message = str(raised.value)
    assert "TextSearch" in message
    assert "'pgvector' (weft-store)" in message


@pytest.fixture(params=("pgvector", "qdrant"))
async def target_store(request: pytest.FixtureRequest) -> AsyncIterator[ConformanceStore]:
    """A store of each backend that holds targets, on storage no other test reads — `34.1`.

    A target check changes which target is live, and every other test on a shared database or
    collection reads whatever target is live, so each arm gets storage of its own: pgvector a
    database created and dropped here by exact name, `approximate_store`'s precedent; Qdrant a
    collection prefix of its own (`34.5`), every collection under it dropped by exact name.
    """
    backend = cast(str, request.param)
    if backend == "qdrant":
        await _require_qdrant()
        settings = _qdrant_settings()
        qdrant = QdrantStore(settings)
        try:
            yield qdrant
        finally:
            await qdrant.aclose()
            await _drop_targets(settings)
        return
    await _require_postgres()
    name = f"weft_conformance_{uuid4().hex[:12]}"
    admin = await psycopg.AsyncConnection.connect(_DSN, autocommit=True)
    async with admin.cursor() as cur:
        await cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    dsn = f"{_DSN.rsplit('/', 1)[0]}/{name}"
    pg = PgVectorStore(PgVectorSettings(dsn=SecretStr(dsn)))
    try:
        yield pg
    finally:
        await pg.aclose()
        async with admin.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )
        await admin.close()


async def test_a_fresh_store_has_one_live_target_named_default(
    target_store: TargetHoldingStore,
) -> None:
    await check_a_fresh_store_has_one_live_target_named_default(target_store)


async def test_a_target_is_created_by_its_first_write_and_isolated_from_every_other(
    target_store: TargetHoldingStore,
) -> None:
    await check_a_target_is_created_by_its_first_write_and_isolated_from_every_other(target_store)


async def test_a_source_record_belongs_to_the_target_it_was_written_into(
    target_store: TargetHoldingStore,
) -> None:
    await check_a_source_record_belongs_to_the_target_it_was_written_into(target_store)


async def test_promote_makes_a_target_live_and_rollback_restores_the_previous_one(
    target_store: TargetHoldingStore,
) -> None:
    await check_promote_makes_a_target_live_and_rollback_restores_the_previous_one(target_store)


async def test_promote_refuses_a_target_that_does_not_exist_naming_those_that_do(
    target_store: TargetHoldingStore,
) -> None:
    await check_promote_refuses_a_target_that_does_not_exist_naming_those_that_do(target_store)


async def test_rollback_with_nothing_to_roll_back_to_is_refused(
    target_store: TargetHoldingStore,
) -> None:
    await check_rollback_with_nothing_to_roll_back_to_is_refused(target_store)


async def test_drop_refuses_the_live_and_previous_targets_and_removes_another(
    target_store: TargetHoldingStore,
) -> None:
    await check_drop_refuses_the_live_and_previous_targets_and_removes_another(target_store)


async def test_drop_refuses_a_target_that_does_not_exist_naming_those_that_do(
    target_store: TargetHoldingStore,
) -> None:
    await check_drop_refuses_a_target_that_does_not_exist_naming_those_that_do(target_store)


async def test_the_first_embedding_identity_claimed_is_the_one_a_target_keeps(
    target_store: TargetHoldingStore,
) -> None:
    await check_the_first_embedding_identity_claimed_is_the_one_a_target_keeps(target_store)


async def test_a_target_name_outside_the_grammar_is_refused_by_name(
    target_store: TargetHoldingStore,
) -> None:
    await check_a_target_name_outside_the_grammar_is_refused_by_name(target_store)


async def test_claiming_an_identity_creates_the_target_as_a_first_write_does(
    target_store: TargetHoldingStore,
) -> None:
    await check_claiming_an_identity_creates_the_target_as_a_first_write_does(target_store)
