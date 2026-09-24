"""Ledger task **43.23** — `raptor`'s refusal above `max_leaves` names the remedy that still runs.

A corpus layer stale only because sources were added is joined through `adrap`, whose cost is the
new leaves times the tree's level-1 clusters, so the join runs where a full rebuild is refused.
The refusal is where an operator meets the bound, so that is where the remedy is named.
"""

from weft_index.adrap import NAME as ADRAP_NAME
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, SourceId, Vector


def _leaves(n: int) -> tuple[Node, ...]:
    return tuple(
        Node.synthetic(
            content=f"passage {i}",
            media_type=MediaType.TEXT,
            reason="43.23",
            sources=frozenset({SourceId("doc")}),
        ).with_embedding(Vector(values=(1.0, float(i))))
        for i in range(n)
    )


async def test_the_max_leaves_refusal_names_the_join_as_the_remedy_for_added_sources() -> None:
    # Arrange
    ctx = Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=ServiceRegistry(),
    )
    config = RaptorConfig(similarity_threshold=0.5, max_leaves=2)

    # Act
    outcome = await RaptorSummarizer(config).run(_leaves(3), ctx)

    # Assert
    assert isinstance(outcome, Failed)
    assert "max_leaves" in outcome.reason
    assert ADRAP_NAME in outcome.reason
