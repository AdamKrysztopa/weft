"""A metric result is sliced by every axis its questions declare — ledger task **38.2**.

`11.12` sliced by `kind` and `9.12` by query modality, each by its own field. Open RAGBench's
questions (`38.4`) carry the dataset's own labels as axes — `evidence`, `answer-form`, `split` —
and a rung that is better on text evidence and worse on table evidence reports one mean in which
the two cancel unless the slice sits beside it. The shape is `by_question_kind`'s, one level up:
a mapping of axis to value to `PartitionSlice`, with a partition nothing scored absent rather
than zero.
"""

from __future__ import annotations

import pytest

from weft_eval import Settings, register
from weft_eval.aggregate import MetricAggregate
from weft_eval.contract import RetrievalSample, RetrievedPassage
from weft_eval.harness import score_retrieval_gate_subset
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _sample(key: str, *, hit: bool, axes: dict[str, str]) -> RetrievalSample:
    return RetrievalSample(
        query=key,
        question_key=key,
        retrieved=(RetrievedPassage(id="doc-a" if hit else "doc-z", text="t"),),
        relevant_ids=frozenset({"doc-a"}),
        axes=axes,
    )


def test_a_sample_carries_no_axis_unless_its_question_declares_one() -> None:
    # Act / Assert
    assert RetrievalSample(query="q").axes == {}


async def test_every_declared_axis_is_sliced_beside_the_whole_run_mean() -> None:
    # Arrange — text questions all hit, the table question misses.
    samples = [
        _sample("q-1", hit=True, axes={"evidence": "text", "answer-form": "extractive"}),
        _sample("q-2", hit=True, axes={"evidence": "text", "answer-form": "abstractive"}),
        _sample("q-3", hit=False, axes={"evidence": "text-table", "answer-form": "extractive"}),
    ]

    # Act
    report = await score_retrieval_gate_subset(_registry(), samples, top_k=1, ctx=_ctx())

    # Assert
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert result.mean == pytest.approx(2 / 3)
    assert set(result.by_axis) == {"evidence", "answer-form"}
    assert result.by_axis["evidence"]["text"].mean == pytest.approx(1.0)
    assert result.by_axis["evidence"]["text"].n == 2
    assert result.by_axis["evidence"]["text-table"].mean == pytest.approx(0.0)
    assert result.by_axis["answer-form"]["extractive"].n == 2


async def test_a_sample_lacking_an_axis_contributes_to_the_mean_and_to_no_slice_of_it() -> None:
    # Arrange
    samples = [
        _sample("q-1", hit=True, axes={"evidence": "text"}),
        _sample("q-2", hit=False, axes={}),
    ]

    # Act
    report = await score_retrieval_gate_subset(_registry(), samples, top_k=1, ctx=_ctx())

    # Assert
    outcome = report.metrics["precision@1"]
    assert isinstance(outcome, Produced)
    assert outcome.value.n == 2
    assert outcome.value.by_axis["evidence"]["text"].n == 1


def test_an_aggregate_written_before_axes_existed_reads_with_none() -> None:
    # Arrange
    older = {
        "reported_name": "precision@1",
        "mean": 0.5,
        "n": 2,
        "stdev": None,
        "excluded": 0,
        "nothing_to_produce": 0,
    }

    # Act
    read = MetricAggregate.model_validate(older)

    # Assert
    assert read.by_axis == {}
