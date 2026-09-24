"""The retrieve-only store search is a seam call — ledger task **33.3**.

`weft_cli.ask.run_ask` embedded the question through `wrap` and then called
`instance_store.search_vector` directly, so the search — the number Phase 29 benchmarks and the
path `weft eval` scores by default — had no span, no attribution and no stage record. Inside a
recording scope a retrieve-only ask now leaves one record for the embed and one for the search, so
the store's time is separate from the embedder's.

The doubles are `tests/unit/weft_cli/test_ask.py`'s (`L11.17`).
"""

from collections.abc import Sequence

import pytest

from weft_cli.ask import run_ask
from weft_embed import Embedder
from weft_kernel.context import Context
from weft_kernel.errors import WeftError
from weft_kernel.payload import MediaType, Node, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_kernel.seam import OutcomeKind, recording
from weft_store import Filter, NodeStore, Scored


class _FakeEmbedder:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=[node.with_embedding(Vector(values=(1.0,))) for node in payload])


class _FakeVectorSearchStore:
    def __init__(self, config: object) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(value=payload)

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        found = Node.synthetic(content="a passage", media_type=MediaType.TEXT, reason="fixture")
        other = Node.synthetic(content="another", media_type=MediaType.TEXT, reason="fixture")
        return [Scored(value=found, score=0.9), Scored(value=other, score=0.5)]

    async def aclose(self) -> None:
        return None


class _BrokenSearchStore(_FakeVectorSearchStore):
    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        raise RuntimeError("connection refused")


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _registry(store: type[_FakeVectorSearchStore]) -> Registry:
    registry = Registry()
    registry.add(Embedder, "hash", _FakeEmbedder, distribution="weft-embed")
    registry.add(NodeStore, "pgvector", store, distribution="weft-store")
    return registry


async def test_a_retrieve_only_ask_records_the_search_apart_from_the_embed() -> None:
    # Act
    with recording() as scope:
        results = await run_ask(
            "what changed?", registry=_registry(_FakeVectorSearchStore), ctx=_ctx(), top_k=2
        )

    # Assert
    by_label = {record.label: record for record in scope.records}
    assert set(by_label) == {"ask:embed", "ask:search"}
    search = by_label["ask:search"]
    assert (search.pack, search.contract, search.plugin) == ("weft-store", "NodeStore", "pgvector")
    assert search.outcome is OutcomeKind.PRODUCED
    assert search.items_out == len(results) == 2


async def test_a_search_that_raises_is_attributed_to_the_store_and_recorded() -> None:
    """Guards against `ask` calling the store's search directly again, bypassing attribution.

    Through the seam, a store failure names the store — the attribution the direct call
    never had — and the record says the search raised.
    """
    # Act
    with recording() as scope, pytest.raises(WeftError) as failure:
        await run_ask("what changed?", registry=_registry(_BrokenSearchStore), ctx=_ctx(), top_k=2)

    # Assert
    assert failure.value.plugin == "pgvector"
    by_label = {record.label: record for record in scope.records}
    assert by_label["ask:search"].outcome is OutcomeKind.RAISED
