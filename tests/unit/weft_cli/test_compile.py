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
    RefusedStagePluginError,
    UnknownStagePluginError,
    contracts_for,
    to_specs,
)
from weft_cli.exit_codes import ExitCode, exit_code_for
from weft_generate.contract import Generator
from weft_generate.payload import Answer
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
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
    contracts = contracts_for(pipeline, registry=registry, reports=(), parents=parents)
    resolved = resolve(pipeline, registry=registry, contracts=contracts, parents=parents)
    return to_specs(resolved, registry=registry, reports=())


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
        slot="enrich", distribution="weft-kg", stage=StageDeclaration(id="extra", use="hyde")
    )

    # Act
    contracts = contracts_for(
        _with_slot(), registry=registry, reports=(), parents={}, contributions=(contribution,)
    )

    # Assert
    assert contracts["weft-kg:extra"] is QueryTransform


def test_contracts_for_ignores_a_contribution_whose_slot_no_ancestor_declares() -> None:
    # Arrange — the plugin name is nonsense on purpose: if this contribution were not
    # filtered out, resolving it would raise `UnknownStagePluginError` for a pipeline the
    # contribution was never meant for at all.
    registry = _registry()
    contribution = Contribution(
        slot="not-declared-anywhere",
        distribution="weft-kg",
        stage=StageDeclaration(id="extra", use="plugin-nobody-registered"),
    )

    # Act
    contracts = contracts_for(
        _baseline(), registry=registry, reports=(), parents={}, contributions=(contribution,)
    )

    # Assert
    assert "weft-kg:extra" not in contracts


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
            contracts=contracts_for(_baseline(), registry=registry, reports=(), parents={}),
        ),
        registry=registry,
        reports=(),
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
        contracts_for(pipeline, registry=registry, reports=(), parents={})
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
        contracts_for(pipeline, registry=registry, reports=(), parents={})
    assert "vector-top-kk" in str(caught.value)
    assert "vector-top-k" in str(caught.value)


def test_an_inherited_stage_id_is_in_the_mapping_resolve_demands() -> None:
    # Arrange
    registry = _registry()
    parents = {"retrieve-then-generate": _baseline()}

    # Act
    contracts = contracts_for(_derived(), registry=registry, reports=(), parents=parents)

    # Assert — every id the derived document inherits, not only the three it introduces
    assert set(contracts) == {"hyde", "fanout", "retrieve", "fuse", "rerank", "pack", "generate"}


def _report(pack: str | None, status: PackStatus, *, reason: str = "") -> PackReport:
    """One `weft plugins doctor` row, built the way discovery builds it.

    `distribution` is `weft-rag` throughout because that is the fact the install line is
    derived from — G19 leaves exactly two published names, so a capability that needs an
    outside library is an **extra** of this distribution and never a distribution of its
    own. `pack` is the `weft.packs` entry-point name, which is what a `[packs.<pack>]`
    block keys on and what the extra is named after.
    """
    return PackReport(pack=pack, distribution="weft-rag", status=status, reason=reason)


def test_a_plugin_from_a_failed_pack_is_refused_with_that_packs_own_reason() -> None:
    # Arrange — carried repair **R11.3**, and `02` §2 promises it in as many words: "a name
    # lost to `failed` or `partial` stays 4 with its reason attached". `weft plugins doctor`
    # is already holding that reason; the document path threw it away and printed a bare
    # list of every installed name instead. The dimension this varies against the control
    # below is `reports` — the same registry, the same document, the same missing name.
    registry = _registry()
    reports = (
        _report("qdrant", PackStatus.FAILED, reason="No module named 'qdrant_client'"),
        _report("chunk", PackStatus.ACTIVE),
    )
    pipeline = Pipeline(name="q", stages=(StageDeclaration(id="store", use="qdrant"),))

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    message = str(caught.value)
    assert "qdrant" in message
    assert "No module named 'qdrant_client'" in message
    assert exit_code_for(caught.value) is ExitCode.RESOLUTION_FAILED


def test_the_refusal_names_the_extra_that_would_supply_the_missing_pack() -> None:
    # Arrange — the half R11.3 opens by complaining about: "the one thing an operator can
    # act on (install the extra) is the one thing the message does not say". The install
    # line is derived from the distribution's **own** metadata (`Provides-Extra`), never
    # from a table in this tree, so it cannot claim an extra that does not exist — and
    # `weft-rag` genuinely declares `qdrant`, which is why this reads the real thing rather
    # than a double (`L7.6`: a metadata API is asked where it actually runs).
    registry = _registry()
    reports = (_report("qdrant", PackStatus.FAILED, reason="No module named 'qdrant_client'"),)
    pipeline = Pipeline(name="q", stages=(StageDeclaration(id="store", use="qdrant"),))

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    assert "weft-rag[qdrant]" in str(caught.value)


def test_no_install_line_is_offered_for_a_pack_the_distribution_declares_no_extra_for() -> None:
    # Arrange — `chunk` ships unconditionally in the same wheel and has no extra, so there
    # is no `pip install` that would fix it and the message must not invent one. This is
    # the branch that keeps the line above honest: an install line printed for every failed
    # pack would be advice that is right five times and wrong the sixth.
    registry = _registry()
    reports = (_report("chunk", PackStatus.FAILED, reason="'chunk' settings failed validation"),)
    pipeline = Pipeline(name="q", stages=(StageDeclaration(id="chunk", use="fixed-sizes"),))

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    message = str(caught.value)
    assert "'chunk' settings failed validation" in message
    assert "weft-rag[chunk]" not in message
    assert "pip install" not in message


def test_a_plugin_from_a_refused_pack_exits_three_naming_the_key_that_would_permit_it() -> None:
    # Arrange — `02` §2's other clause, which the document path owed just as much: "A
    # pipeline naming a plugin from a `refused` pack exits 3, refused, and names the config
    # key that would permit it." A refused pack is never imported, so nothing here can
    # prove it is the one that would have claimed the name — the message says that rather
    # than asserting it, exactly as `require_plugin` already does for `[services]`.
    registry = _registry()
    reports = (_report(None, PackStatus.REFUSED),)
    pipeline = Pipeline(name="q", stages=(StageDeclaration(id="store", use="qdrant"),))

    # Act / Assert
    with pytest.raises(RefusedStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    message = str(caught.value)
    assert "[packs] allow" in message
    assert exit_code_for(caught.value) is ExitCode.POLICY_REFUSED


def test_a_name_no_report_can_explain_is_unchanged_and_still_lists_what_is_installed() -> None:
    # Arrange — the control. Every pack is `ACTIVE`, so no report explains anything and the
    # message is what it was before this repair: a typo, answered with the names that do
    # exist. Without this, a change that attached a reason unconditionally would pass every
    # assertion above while making the ordinary typo worse.
    registry = _registry()
    reports = (_report("retrieve", PackStatus.ACTIVE),)
    pipeline = Pipeline(name="typo", stages=(StageDeclaration(id="retrieve", use="vector-top-kk"),))

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    message = str(caught.value)
    assert "vector-top-k" in message
    assert "pip install" not in message
    assert exit_code_for(caught.value) is ExitCode.RESOLUTION_FAILED


def test_to_specs_attributes_a_failed_pack_the_same_way_contracts_for_does() -> None:
    # Arrange — both seams call `_contract_for`, and a repair that fixed only the one the
    # transcript came from would leave the other printing the bare list. `to_specs` is
    # reached on every run that gets past `contracts_for`, so the two must not disagree.
    registry = _registry()
    reports = (_report("qdrant", PackStatus.FAILED, reason="No module named 'qdrant_client'"),)
    resolved = resolve(
        _baseline(),
        registry=registry,
        contracts=contracts_for(_baseline(), registry=registry, reports=(), parents={}),
        parents={},
    )
    broken = resolved.model_copy(
        update={
            "stages": tuple(
                stage.model_copy(update={"use": "qdrant"}) if stage.id == "retrieve" else stage
                for stage in resolved.stages
            )
        }
    )

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        to_specs(broken, registry=registry, reports=reports)
    assert "No module named 'qdrant_client'" in str(caught.value)
    assert "weft-rag[qdrant]" in str(caught.value)


def test_two_failed_packs_in_one_distribution_are_told_apart_in_the_message() -> None:
    # Arrange — **carried repair R11.3, second half, and this test exists because the binary
    # found it and the six above did not.** The first real run of this repair printed
    # `weft-rag (failed); weft-rag (failed); weft-rag (partial); ...` — seven rows keyed on a
    # string that G19 made identical for every first-party pack, one of which was the answer.
    # Every assertion above passed throughout, because each used one report and one report
    # cannot collide with itself. The dimension this varies is the one that was missing:
    # **two** reports, same distribution, different packs.
    registry = _registry()
    reports = (
        _report("qdrant", PackStatus.FAILED, reason="No module named 'qdrant_client'"),
        _report("pdf", PackStatus.FAILED, reason="No module named 'pdfplumber'"),
    )
    pipeline = Pipeline(name="q", stages=(StageDeclaration(id="store", use="qdrant"),))

    # Act / Assert
    with pytest.raises(UnknownStagePluginError) as caught:
        contracts_for(pipeline, registry=registry, reports=reports, parents={})
    message = str(caught.value)
    assert "qdrant" in message
    assert "pdf" in message
    # The distribution alone would render both rows as the identical string, which is what
    # `PackReport`'s own docstring says a report carrying only that fact can no longer do:
    # "tell fourteen rows apart".
    assert "weft-rag (failed); weft-rag (failed)" not in message
    assert "weft-rag[qdrant]" in message
    assert "weft-rag[pdf]" in message
