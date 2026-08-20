"""Unit tests for `weft_eval.contract`.

Mirrors `packages/weft-eval/src/weft_eval/contract.py`. Task 4.2's split: `Metric`/`Sample` from
4.1 are now `GenerationMetric`/`GenerationSample` and `RetrievalMetric`/`RetrievalSample`, two
distinct contracts sharing the one `MetricScore` result shape. Covers capability being derived by
`isinstance` for both, `GenerationSample`/`RetrievalSample` refusing an unknown field, and the two
version constants fitness function 6 will eventually check.
"""

import pytest
from pydantic import ValidationError

from weft_eval.contract import (
    GENERATION_METRIC_CONTRACT_VERSION,
    RETRIEVAL_METRIC_CONTRACT_VERSION,
    GenerationMetric,
    GenerationSample,
    MetricScore,
    RetrievalMetric,
    RetrievalSample,
    RetrievedPassage,
)
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import MissingRequiredDeclarationError, Registry


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


class _AlwaysScoresGeneration:
    """Satisfies `GenerationMetric` structurally — no inheritance."""

    version = GENERATION_METRIC_CONTRACT_VERSION

    def __init__(self, config: object = None) -> None:
        del config

    async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        return Produced(value=MetricScore(metric_name="always", value=1.0))


class _AlwaysScoresRetrieval:
    """Satisfies `RetrievalMetric` structurally — no inheritance."""

    version = RETRIEVAL_METRIC_CONTRACT_VERSION

    def __init__(self, config: object = None) -> None:
        del config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        return Produced(value=MetricScore(metric_name="always", value=1.0))


async def test_a_structurally_conforming_generation_metric_evaluates_through_the_contract() -> None:
    # Arrange
    metric = _AlwaysScoresGeneration()
    sample = GenerationSample(query="q", reference="r")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.metric_name == "always"


async def test_a_structurally_conforming_retrieval_metric_evaluates_through_the_contract() -> None:
    # Arrange
    metric = _AlwaysScoresRetrieval()
    sample = RetrievalSample(query="q")

    # Act
    outcome = await metric.evaluate(sample, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.metric_name == "always"


def test_metric_capability_is_derived_by_isinstance_not_declared() -> None:
    # Arrange
    class _MissingEvaluate:
        version = GENERATION_METRIC_CONTRACT_VERSION

    class _OnlyEvaluate:
        async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
            del payload, ctx
            return Produced(value=MetricScore(metric_name="x", value=0.0))

    # Act / Assert — declaring `version` neither helps nor is required; only `evaluate` matters.
    assert isinstance(_AlwaysScoresGeneration(), GenerationMetric)
    assert not isinstance(_MissingEvaluate(), GenerationMetric)
    assert isinstance(_OnlyEvaluate(), GenerationMetric)


def test_generation_sample_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        GenerationSample.model_validate({"query": "q", "reference": "r", "bogus": "x"})


def test_retrieval_sample_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        RetrievalSample.model_validate({"query": "q", "bogus": "x"})


def test_retrieval_sample_carries_rank_ordered_passages_and_a_relevance_set() -> None:
    # Arrange / Act
    sample = RetrievalSample(
        query="q",
        retrieved=(RetrievedPassage(id="a"), RetrievedPassage(id="b", text="passage b")),
        relevant_ids=frozenset({"b"}),
    )

    # Assert
    assert sample.retrieved[0].id == "a"
    assert sample.retrieved[1].text == "passage b"
    assert sample.relevant_ids == frozenset({"b"})


def test_generation_and_retrieval_metric_versions_are_declared_and_distinct() -> None:
    # Act / Assert
    assert GenerationMetric.version == GENERATION_METRIC_CONTRACT_VERSION
    assert RetrievalMetric.version == RETRIEVAL_METRIC_CONTRACT_VERSION


def test_both_metric_contracts_require_runs_in_gate() -> None:
    # Task 4.7, Q6: the same mechanism `Command.required_declarations` already uses for
    # `permission_class`, extended rather than duplicated.
    assert GenerationMetric.required_declarations == ("runs_in_gate",)
    assert RetrievalMetric.required_declarations == ("runs_in_gate",)


def test_a_metric_that_never_declares_runs_in_gate_fails_to_register() -> None:
    # Arrange — a structurally-conforming metric that never states `runs_in_gate`.
    class _NoDeclaration:
        async def evaluate(self, payload: GenerationSample, ctx: Context) -> Outcome[MetricScore]:
            del payload, ctx
            return Produced(value=MetricScore(metric_name="x", value=0.0))

    registry = Registry()

    # Act / Assert — refused at registration, not silently accepted with a default.
    with pytest.raises(MissingRequiredDeclarationError):
        registry.add(GenerationMetric, "no-declaration", _NoDeclaration, distribution="test")
