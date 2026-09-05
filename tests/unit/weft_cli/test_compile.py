"""Unit tests for `weft_cli.compile`.

Mirrors `packages/weft-rag/src/weft_cli/compile.py`. Covers the bridge task 2.4
builds between a resolved pipeline *document* and the `StageSpec` list
`weft_kernel.runner.Runner.resolve` consumes — the contract mapping inferred from the
registry rather than from a table, and the specs that mapping produces.

**This file is also where Phase 2's central architectural claim is re-verified rather
than trusted.** The design record's thesis is that multiplicity lives in the payload
*type* — `QuerySet` means n queries, `Candidates` means k ranked lists, `Ranking` means
one — so every query-path stage is a plain `Stage[In, Out]` in one ordered list and
`weft_kernel.runner._check_composition` stays load-bearing on the query path. That claim
is only worth anything if the real runner agrees, so the four-stage baseline and the
seven-stage derived pipeline are both driven through the real `resolve` here, and the
two orderings the thesis says must be impossible — a reranker before the fuser, a
reranker before the retriever — are asserted to raise `StageCompositionError` from the
kernel with no pack-side inspector anywhere.
"""

import pytest
from pydantic import BaseModel, ConfigDict

from weft_cli.compile import (
    AmbiguousStageContractError,
    UnknownStagePluginError,
    contracts_for,
    to_specs,
)
from weft_generate.contract import Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import InsertOperator, Pipeline, SlotDeclaration, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, resolve
from weft_kernel.runner import Runner, StageCompositionError, StageSpec
from weft_retrieve.contract import (
    ContextPacker,
    Fuser,
    QueryTransform,
    Reranker,
    Retriever,
)
from weft_retrieve.payload import (
    Candidates,
    Passages,
    Query,
    QuerySet,
    Ranking,
)


class _TopKConfig(BaseModel):
    """A stub `with:` block, so `to_specs` has a validated model instance to carry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_k: int = 10


class _Transform:
    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        return Produced(value=payload)


class _Retrieve:
    config_model: type[_TopKConfig] = _TopKConfig

    def __init__(self, config: _TopKConfig | None = None) -> None:
        self.config = config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        return Produced(value=Candidates(origin=payload.origin))


class _Fuse:
    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]:
        return Produced(value=Ranking(origin=payload.origin))


class _Rerank:
    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        return Produced(value=payload)


class _Pack:
    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Passages]:
        return Produced(value=Passages(origin=payload.origin))


class _Generate:
    def __init__(self, config: object = None) -> None: ...

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        return Produced(
            value=Answer(origin=payload.origin, text="an answer", answered_by="cited-answer")
        )


def _registry() -> Registry:
    """Every plugin name the two shipped Phase 2 pipelines will name, under its real contract."""
    registry = Registry()
    registry.add(QueryTransform, "hyde", _Transform, distribution="weft-retrieve")
    registry.add(QueryTransform, "multi-query", _Transform, distribution="weft-retrieve")
    registry.add(Retriever, "vector-top-k", _Retrieve, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", _Fuse, distribution="weft-retrieve")
    registry.add(Fuser, "reciprocal-rank-fusion", _Fuse, distribution="weft-retrieve")
    registry.add(Reranker, "llm-rerank", _Rerank, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", _Pack, distribution="weft-retrieve")
    registry.add(Generator, "cited-answer", _Generate, distribution="weft-generate")
    return registry


def _baseline() -> Pipeline:
    """`retrieve-then-generate`, the V3 baseline, as the design record writes it."""
    return Pipeline(
        name="retrieve-then-generate",
        stages=(
            StageDeclaration(id="retrieve", use="vector-top-k", config={"top_k": 20}),
            StageDeclaration(id="fuse", use="single-list"),
            StageDeclaration(id="pack", use="repack"),
            StageDeclaration(id="generate", use="cited-answer"),
        ),
    )


def _derived() -> Pipeline:
    """`hyde-fanout-rrf` — a one-document delta over the baseline, never a copy of it."""
    return Pipeline(
        name="hyde-fanout-rrf",
        extends="retrieve-then-generate",
        insert=(
            InsertOperator(before="retrieve", stage=StageDeclaration(id="hyde", use="hyde")),
            InsertOperator(
                before="retrieve", stage=StageDeclaration(id="fanout", use="multi-query")
            ),
            InsertOperator(after="fuse", stage=StageDeclaration(id="rerank", use="llm-rerank")),
        ),
        replace=(StageDeclaration(id="fuse", use="reciprocal-rank-fusion"),),
    )


def _specs_for(
    pipeline: Pipeline, registry: Registry, parents: dict[str, Pipeline]
) -> tuple[StageSpec, ...]:
    contracts = contracts_for(pipeline, registry=registry, parents=parents)
    resolved = resolve(pipeline, registry=registry, contracts=contracts, parents=parents)
    return to_specs(resolved, registry=registry)


async def test_the_baseline_pipeline_compiles_composes_and_runs() -> None:
    # Arrange
    registry = _registry()
    engine = Runner(registry)
    question = QuerySet(origin=Query(text="why mRMR?"), queries=(Query(text="why mRMR?"),))

    # Act
    specs = _specs_for(_baseline(), registry, {})
    runnable = engine.resolve(specs, tenant_id="tenant-a")
    outcome = await engine.run_once(
        runnable,
        question,
        Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en"),
    )

    # Assert
    assert [(spec.id, spec.contract, spec.name) for spec in specs] == [
        ("retrieve", Retriever, "vector-top-k"),
        ("fuse", Fuser, "single-list"),
        ("pack", ContextPacker, "repack"),
        ("generate", Generator, "cited-answer"),
    ]
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, Answer)


def test_the_derived_pipeline_composes_over_seven_stages() -> None:
    # Arrange
    registry = _registry()
    engine = Runner(registry)
    parents = {"retrieve-then-generate": _baseline()}

    # Act
    specs = _specs_for(_derived(), registry, parents)
    engine.resolve(specs, tenant_id="tenant-a")

    # Assert
    assert [(spec.id, spec.contract) for spec in specs] == [
        ("hyde", QueryTransform),
        ("fanout", QueryTransform),
        ("retrieve", Retriever),
        ("fuse", Fuser),
        ("rerank", Reranker),
        ("pack", ContextPacker),
        ("generate", Generator),
    ]


# --- slot contributions (task 5.3a, S8) -------------------------------------------------


def _with_slot() -> Pipeline:
    return Pipeline(
        name="with-slot",
        stages=(StageDeclaration(id="retrieve", use="vector-top-k"),),
        slots=(SlotDeclaration(id="enrich", after="retrieve"),),
    )


def test_contracts_for_adds_an_entry_for_a_contribution_whose_slot_this_pipeline_declares() -> None:
    # Arrange — `hyde` is a real `QueryTransform` plugin `_registry()` already publishes;
    # reused here as the contribution's own plugin, since `contracts_for` infers a
    # contribution's contract off the registry exactly as it does for an authored stage.
    registry = _registry()
    contribution = Contribution(
        slot="enrich", distribution="weft-graph", stage=StageDeclaration(id="extra", use="hyde")
    )

    # Act
    contracts = contracts_for(
        _with_slot(), registry=registry, parents={}, contributions=(contribution,)
    )

    # Assert
    assert contracts["weft-graph:extra"] is QueryTransform


def test_contracts_for_ignores_a_contribution_whose_slot_no_ancestor_declares() -> None:
    # Arrange — the plugin name is nonsense on purpose: if this contribution were not
    # filtered out, resolving it would raise `UnknownStagePluginError` for a pipeline the
    # contribution was never meant for at all.
    registry = _registry()
    contribution = Contribution(
        slot="not-declared-anywhere",
        distribution="weft-graph",
        stage=StageDeclaration(id="extra", use="plugin-nobody-registered"),
    )

    # Act
    contracts = contracts_for(
        _baseline(), registry=registry, parents={}, contributions=(contribution,)
    )

    # Assert
    assert "weft-graph:extra" not in contracts


def _document(name: str, *stages: tuple[str, str]) -> Pipeline:
    return Pipeline(
        name=name,
        stages=tuple(StageDeclaration(id=stage_id, use=use) for stage_id, use in stages),
    )


@pytest.mark.parametrize(
    ("name", "stages", "failing_pair"),
    [
        (
            "rerank-before-fuse",
            (
                ("retrieve", "vector-top-k"),
                ("rerank", "llm-rerank"),
                ("fuse", "single-list"),
                ("pack", "repack"),
                ("generate", "cited-answer"),
            ),
            ("retrieve", "rerank"),
        ),
        (
            "rerank-before-retrieve",
            (
                ("rerank", "llm-rerank"),
                ("retrieve", "vector-top-k"),
                ("fuse", "single-list"),
                ("pack", "repack"),
                ("generate", "cited-answer"),
            ),
            ("rerank", "retrieve"),
        ),
        (
            "generate-before-pack",
            (
                ("retrieve", "vector-top-k"),
                ("fuse", "single-list"),
                ("generate", "cited-answer"),
            ),
            ("fuse", "generate"),
        ),
        (
            "two-retrievers-in-a-row",
            (("retrieve", "vector-top-k"), ("retrieve-again", "vector-top-k")),
            ("retrieve", "retrieve-again"),
        ),
    ],
)
def test_an_order_the_type_algebra_forbids_is_refused_at_document_resolution(
    name: str, stages: tuple[tuple[str, str], ...], failing_pair: tuple[str, str]
) -> None:
    # Arrange
    registry = _registry()
    broken = _document(name, *stages)

    # Act / Assert — `weft_kernel.resolution.resolve` is where an operator meets it
    with pytest.raises(StageCompositionError) as caught:
        _specs_for(broken, registry, {})
    assert caught.value.stages == failing_pair


@pytest.mark.parametrize(
    ("stages", "failing_pair"),
    [
        (
            (
                ("retrieve", Retriever, "vector-top-k"),
                ("rerank", Reranker, "llm-rerank"),
                ("fuse", Fuser, "single-list"),
            ),
            ("retrieve", "rerank"),
        ),
        (
            (
                ("rerank", Reranker, "llm-rerank"),
                ("retrieve", Retriever, "vector-top-k"),
            ),
            ("rerank", "retrieve"),
        ),
        (
            (
                ("fuse", Fuser, "single-list"),
                ("generate", Generator, "cited-answer"),
            ),
            ("fuse", "generate"),
        ),
        (
            (
                ("retrieve", Retriever, "vector-top-k"),
                ("retrieve-again", Retriever, "vector-top-k"),
            ),
            ("retrieve", "retrieve-again"),
        ),
    ],
)
def test_the_same_order_is_refused_again_by_the_runners_own_check(
    stages: tuple[tuple[str, type[object], str], ...], failing_pair: tuple[str, str]
) -> None:
    # Arrange — a hand-built `StageSpec` list never passes through a document, so this is
    # the kernel check on its own. Both resolvers must refuse, or the property holds only
    # for pipelines that happened to arrive as YAML.
    registry = _registry()
    engine = Runner(registry)
    specs = tuple(
        StageSpec(id=stage_id, contract=contract, name=use) for stage_id, contract, use in stages
    )

    # Act / Assert
    with pytest.raises(StageCompositionError) as caught:
        engine.resolve(specs, tenant_id="tenant-a")
    assert caught.value.stages == failing_pair


def test_a_validated_with_block_reaches_the_stage_spec_and_an_empty_one_becomes_none() -> None:
    # Arrange
    registry = _registry()

    # Act
    specs = to_specs(
        resolve(
            _baseline(),
            registry=registry,
            contracts=contracts_for(_baseline(), registry=registry, parents={}),
        ),
        registry=registry,
    )

    # Assert
    by_id = {spec.id: spec.config for spec in specs}
    assert by_id["retrieve"] == _TopKConfig(top_k=20)
    assert by_id["fuse"] is None


def test_a_plugin_name_two_contracts_register_is_refused_by_name() -> None:
    # Arrange
    registry = _registry()
    registry.add(Fuser, "vector-top-k", _Fuse, distribution="weft-third-party")
    pipeline = Pipeline(
        name="ambiguous",
        stages=(StageDeclaration(id="retrieve", use="vector-top-k"),),
    )

    # Act / Assert
    with pytest.raises(AmbiguousStageContractError) as caught:
        contracts_for(pipeline, registry=registry, parents={})
    assert "Fuser" in str(caught.value)
    assert "Retriever" in str(caught.value)


def test_a_plugin_no_distribution_registered_is_refused_naming_what_is_installed() -> None:
    # Arrange
    registry = _registry()
    pipeline = Pipeline(
        name="typo",
        stages=(StageDeclaration(id="retrieve", use="vector-top-kk"),),
    )

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, parents={})
    assert "vector-top-kk" in str(caught.value)
    assert "vector-top-k" in str(caught.value)


def test_an_inherited_stage_id_is_in_the_mapping_resolve_demands() -> None:
    # Arrange
    registry = _registry()
    parents = {"retrieve-then-generate": _baseline()}

    # Act
    contracts = contracts_for(_derived(), registry=registry, parents=parents)

    # Assert — every id the derived document inherits, not only the three it introduces
    assert set(contracts) == {"hyde", "fanout", "retrieve", "fuse", "rerank", "pack", "generate"}
