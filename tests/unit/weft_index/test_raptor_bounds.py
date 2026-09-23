"""Ledger task **43.13** — `raptor` refuses, by name, a corpus it cannot cluster in reasonable time.

`43.12` measured the pure-Python pass `similarity_threshold: auto` makes: every pairwise cosine,
about 172 µs a pair on 3,072-dimension vectors — 86 s and 339 MB at 1,000 leaves, and about 8.6
hours and 9 GB at the 19,000 a 100-PDF corpus holds. So `auto` is refused above `max_pairs`
(500,000, the measured 1,000-leaf point), and clustering is refused above `max_leaves` (5,000)
whatever the threshold. Each refusal names the leaf count, the bound and the remedies, and comes
before the expensive pass rather than after it. Fixtures are built at the real bounds (`L28.12`):
one leaf over refuses, the bound itself runs.
"""

import pytest

import weft_index.raptor as raptor_module
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, SourceId, Vector


def _leaves(n: int) -> tuple[Node, ...]:
    return tuple(
        Node.synthetic(
            content=f"passage {i}",
            media_type=MediaType.TEXT,
            reason="raptor bounds",
            sources=frozenset({SourceId("doc")}),
        ).with_embedding(Vector(values=(1.0, float(i % 7))))
        for i in range(n)
    )


def _ctx() -> Context:
    return Context(
        tenant_id="tenant-a",
        run_id="run-1",
        trace_id="trace-1",
        locale="en",
        services=ServiceRegistry(),
    )


class _Spy:
    """Stands in for the expensive pass: records that it was reached, then answers degenerately
    so `run` stops without a model call."""

    def __init__(self, answer: object) -> None:
        self.calls = 0
        self._answer = answer

    def __call__(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        return self._answer


def test_the_bounds_default_to_what_43_12_measured() -> None:
    # Act
    config = RaptorConfig()

    # Assert
    assert (config.max_pairs, config.max_leaves) == (500_000, 5_000)


async def test_auto_above_max_pairs_is_refused_before_any_pair_is_computed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — 1,001 leaves are 500,500 pairs, one step over the default bound.
    threshold = _Spy((0.5, -1.0))
    monkeypatch.setattr(raptor_module, "_resolve_similarity_threshold", threshold)

    # Act
    outcome = await RaptorSummarizer().run(_leaves(1001), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert threshold.calls == 0
    for fact in ("1,001", "500,500", "500,000", "similarity_threshold", "max_pairs"):
        assert fact in outcome.reason, fact


async def test_auto_at_max_pairs_reaches_the_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — 1,000 leaves are 499,500 pairs, inside the bound.
    threshold = _Spy((0.5, -1.0))
    monkeypatch.setattr(raptor_module, "_resolve_similarity_threshold", threshold)

    # Act
    outcome = await RaptorSummarizer().run(_leaves(1000), _ctx())

    # Assert — past the bound: the degenerate median the spy answered is what stopped it.
    assert threshold.calls == 1
    assert isinstance(outcome, Failed)
    assert "max_pairs" not in outcome.reason


async def test_any_threshold_above_max_leaves_is_refused_before_clustering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — a typed threshold skips the pairwise pass, but not the leaf bound.
    clustering = _Spy([])
    monkeypatch.setattr(raptor_module, "_cluster_by_similarity", clustering)
    config = RaptorConfig(similarity_threshold=0.5)

    # Act
    outcome = await RaptorSummarizer(config).run(_leaves(5001), _ctx())

    # Assert
    assert isinstance(outcome, Failed)
    assert clustering.calls == 0
    for fact in ("5,001", "5,000", "max_leaves"):
        assert fact in outcome.reason, fact


async def test_a_typed_threshold_at_max_leaves_reaches_clustering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    clustering = _Spy([])
    monkeypatch.setattr(raptor_module, "_cluster_by_similarity", clustering)
    config = RaptorConfig(similarity_threshold=0.5)

    # Act
    await RaptorSummarizer(config).run(_leaves(5000), _ctx())

    # Assert
    assert clustering.calls == 1


def test_a_bound_below_its_floor_is_refused_at_configuration() -> None:
    # Act / Assert
    with pytest.raises(ValueError):
        RaptorConfig(max_pairs=0)
    with pytest.raises(ValueError):
        RaptorConfig(max_leaves=1)
