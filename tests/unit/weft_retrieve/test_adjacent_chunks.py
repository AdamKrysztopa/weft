"""Unit tests for `weft_retrieve.adjacent_chunks` — ledger task **32.3**.

Each hit comes back with up to `window` neighbours on each side from the same parent, read by
`ChunkPosition.ordinal` (`32.1`) through the store's Filter AST (`32.2`). Owner question 2 settled
that each neighbour is its own passage — a stored node `get` can fetch, never a merged one — and
that a neighbour scores as the hit that brought it. Owner question 5 settled the remedy for a
corpus indexed before positions existed: `weft index --reprocess`.

The fake store below evaluates exactly the filter shape the plugin is specified to send —
`lineage.parents contains P` and `ext.weft-chunk.ordinal in (...)` — and refuses any other, so a
plugin that asked for siblings some other way fails here loudly rather than being answered.
"""

from weft_chunk.payload import ChunkPosition
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, Produced
from weft_retrieve.adjacent_chunks import NAME, AdjacentChunks, AdjacentChunksConfig
from weft_retrieve.contract import Reranker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_store.contract import Cursor, Filter, FilterOp, MetadataFilter, NodeStore, Page, Scored


class _ShapeError(AssertionError):
    pass


def _clause_values(filter: Filter) -> tuple[str, frozenset[int]]:
    if filter.op is not FilterOp.AND:
        raise _ShapeError(f"expected an AND of parent and ordinals, got {filter.op}")
    parent: str | None = None
    ordinals: frozenset[int] | None = None
    for clause in filter.clauses:
        if clause.op is FilterOp.CONTAINS and clause.field == "lineage.parents":
            parent = str(clause.value)
        elif clause.op is FilterOp.IN and clause.field == "ext.weft-chunk.ordinal":
            assert isinstance(clause.value, tuple)
            ordinals = frozenset(int(v) for v in clause.value)
        else:
            raise _ShapeError(f"unexpected clause {clause}")
    if parent is None or ordinals is None:
        raise _ShapeError("both the parent and the ordinal clause are required")
    return parent, ordinals


class _FilterStore:
    """`NodeStore` + `MetadataFilter`, answering only the sibling query."""

    def __init__(self, nodes: tuple[Node, ...]) -> None:
        self._nodes = nodes
        self.queries = 0

    async def matching(self, filter: Filter, cursor: Cursor | None = None) -> Page[Node]:
        del cursor
        self.queries += 1
        parent, ordinals = _clause_values(filter)
        found = tuple(
            node
            for node in self._nodes
            if parent in {str(p) for p in node.lineage.parents}
            and (position := node.ext_as(ChunkPosition)) is not None
            and position.ordinal in ordinals
        )
        return Page(items=found)


class _StoreWithoutFilters:
    pass


def _ctx(store: object) -> Context:
    services = ServiceRegistry()
    services.add(NodeStore, store)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _document(name: str, chunks: int) -> tuple[Node, tuple[Node, ...]]:
    parent = Node.synthetic(content=name, media_type=MediaType.TEXT, reason="adjacent fixture")
    children = tuple(
        parent.derive(content=f"{name}-{ordinal}", ordinal=ordinal).with_ext(
            ChunkPosition(ordinal=ordinal, start=ordinal * 10)
        )
        for ordinal in range(chunks)
    )
    return parent, children


def _hit(node: Node, *, score: float, rank: int) -> Passage:
    return Passage(scored=Scored(value=node, score=score), rank=rank, retrieved_by="vector-top-k")


def _ranking(*hits: Passage) -> Ranking:
    return Ranking(origin=Query(text="what surrounds it?"), hits=hits, contributors=("vector",))


def test_it_is_selectable_by_name_is_a_reranker_and_needs_a_filterable_store() -> None:
    # Act / Assert
    assert NAME == "adjacent-chunks"
    assert isinstance(AdjacentChunks(AdjacentChunksConfig()), Reranker)
    assert AdjacentChunks.needs_store == (MetadataFilter,)


def test_the_window_defaults_to_one_neighbour_each_side() -> None:
    # Act / Assert
    assert AdjacentChunksConfig().window == 1


async def test_a_hit_comes_back_between_its_neighbours_in_ordinal_order() -> None:
    # Arrange
    _, chunks = _document("doc", 5)
    store = _FilterStore(chunks)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(
        _ranking(_hit(chunks[2], score=0.9, rank=0)), _ctx(store)
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.node.content for hit in outcome.value.hits] == ["doc-1", "doc-2", "doc-3"]
    assert [hit.rank for hit in outcome.value.hits] == [0, 1, 2]


async def test_each_neighbour_scores_as_the_hit_that_brought_it_and_says_it_was_added() -> None:
    # Arrange
    _, chunks = _document("doc", 5)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(
        _ranking(_hit(chunks[2], score=0.9, rank=0)), _ctx(_FilterStore(chunks))
    )

    # Assert
    assert isinstance(outcome, Produced)
    hits = outcome.value.hits
    assert [hit.score for hit in hits] == [0.9, 0.9, 0.9]
    assert [hit.retrieved_by for hit in hits] == [NAME, "vector-top-k", NAME]
    assert outcome.value.contributors == ("vector",)


async def test_a_hit_at_the_edge_of_its_parent_takes_only_the_neighbours_that_exist() -> None:
    # Arrange
    _, chunks = _document("doc", 3)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig(window=2)).run(
        _ranking(_hit(chunks[0], score=0.5, rank=0)), _ctx(_FilterStore(chunks))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.node.content for hit in outcome.value.hits] == ["doc-0", "doc-1", "doc-2"]


async def test_no_node_appears_twice_when_two_hits_share_a_neighbour() -> None:
    # Arrange — hits at ordinals 1 and 3 both reach ordinal 2; the first hit's group claims it.
    _, chunks = _document("doc", 5)
    ranking = _ranking(_hit(chunks[1], score=0.9, rank=0), _hit(chunks[3], score=0.7, rank=1))

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(ranking, _ctx(_FilterStore(chunks)))

    # Assert
    assert isinstance(outcome, Produced)
    contents = [hit.node.content for hit in outcome.value.hits]
    assert contents == ["doc-0", "doc-1", "doc-2", "doc-3", "doc-4"]
    assert len(contents) == len(set(contents))


async def test_neighbours_come_only_from_the_hits_own_parent() -> None:
    # Arrange — two documents with the same ordinals; only the hit's document contributes.
    _, wanted = _document("wanted", 3)
    _, other = _document("other", 3)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(
        _ranking(_hit(wanted[1], score=0.8, rank=0)), _ctx(_FilterStore(wanted + other))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert [hit.node.content for hit in outcome.value.hits] == ["wanted-0", "wanted-1", "wanted-2"]


async def test_a_hit_with_no_position_is_refused_naming_it_and_the_reindex_that_fixes_it() -> None:
    # Arrange — indexed before `32.1`: a chunk with no `ChunkPosition`.
    parent = Node.synthetic(content="old", media_type=MediaType.TEXT, reason="pre-32.1")
    old_chunk = parent.derive(content="old-0", ordinal=0)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(
        _ranking(_hit(old_chunk, score=0.5, rank=0)), _ctx(_FilterStore((old_chunk,)))
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert NAME in outcome.reason
    assert str(old_chunk.id) in outcome.reason
    assert "weft index --reprocess" in outcome.reason


async def test_a_store_that_cannot_filter_is_refused_by_name() -> None:
    # Arrange
    _, chunks = _document("doc", 3)

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(
        _ranking(_hit(chunks[1], score=0.5, rank=0)), _ctx(_StoreWithoutFilters())
    )

    # Assert
    assert isinstance(outcome, Failed)
    assert "MetadataFilter" in outcome.reason


async def test_an_empty_ranking_passes_through_without_reading_the_store() -> None:
    # Arrange
    store = _FilterStore(())
    empty = Ranking(origin=Query(text="nothing"), contributors=("vector",))

    # Act
    outcome = await AdjacentChunks(AdjacentChunksConfig()).run(empty, _ctx(store))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.hits == ()
    assert store.queries == 0


def test_it_says_what_its_scores_mean() -> None:
    """`weft ask --explain` printed "adjacent-chunks did not say what its score means" at
    `32.13`'s exit: a neighbour carries its anchor hit's score, which is not a similarity.
    """
    # Act / Assert
    assert "neighbour" in AdjacentChunks.score_semantics
