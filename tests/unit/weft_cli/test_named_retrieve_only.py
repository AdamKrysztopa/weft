"""`weft ask --retrieve-only --pipeline <name>` — repair **R21.5**.

Phase 21b put real BM25 in both stores and left it behind a model call. `hybrid` is the only
shipped retriever that reaches a store's text arm, every document naming it ends in a `Generator`,
and `weft ask --pipeline hybrid-then-generate` therefore exits 1 with *"no `[llm.roles]` entry maps
role 'generate'"* on a machine with no model configured. The one route that needs no model —
`--retrieve-only` — embeds the question and searches the vector arm, because that is Phase 0's
contract and it is hardwired. So the lexical arm of the store was, from the shipped binary,
unreachable without an account.

**The remedy was already written down in a refusal nobody could take.**
`weft_cli.route_ask._require` tells an operator whose pipeline ended in a retriever to *"run this
pipeline with `--retrieve-only`, which asks for the shape it actually produces"* — and
`AskCommand.run` refused those two flags together. This repair makes the sentence true.

`--retrieve-only` keeps its meaning exactly: **produce passages, call no model**. What changes is
that it can now be given a pipeline to produce them with. A pipeline that ends in a `Generator` is
still refused, by name, before anything runs — `ConflictingAskModeError` keeps its class, its exit
code and its troubleshooting entry, and narrows to the case where the two flags really do
contradict each other.

**This module holds the refusal's own test**, which used to live in
`tests/unit/weft_cli/test_commands.py` as
`test_ask_command_refuses_retrieve_only_and_pipeline_together` against an empty registry and the
name `"specific"`. That could not survive the narrowing — deciding whether a pipeline generates
means resolving it — and the assertion here is stronger than the one it replaces: the message has
to name the pipeline and offer one that would work.

The store double satisfies both search protocols and the embedder **raises if it is ever called**:
the claim under test is not that a text search happened but that no embedding happened, and a
double that merely records calls cannot tell a passing run from one that embedded and discarded it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

import pytest

from weft_cli import commands
from weft_cli.pipeline_catalogue import full_catalogue
from weft_embed.contract import Embedder
from weft_engine.registry_bootstrap import Dependencies, build_dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackReport, PackStatus, PipelineResource
from weft_kernel.payload import ExtModel, MediaType, Node, Outcome, Produced, Vector
from weft_kernel.registry import Registry
from weft_retrieve import ContextPacker, Fuser, Retriever
from weft_retrieve.anchor_promote import AnchorBranch, AnchorPromotion
from weft_retrieve.fusion import SingleList
from weft_retrieve.hybrid import Hybrid
from weft_retrieve.payload import Channel, Passages, Query
from weft_retrieve.repack import Repack
from weft_store.contract import Filter, NodeStore, Scored

LEXICAL_PIPELINE = "lexical-retrieve"


class _RefusingEmbedder:
    """An `Embedder` that fails the test if anything asks it for a vector.

    The property is *no embedding call*, and the only double that can assert it is one that
    cannot be called quietly.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del payload, ctx
        raise AssertionError(
            "the lexical path embedded the question. `--retrieve-only --pipeline "
            f"{LEXICAL_PIPELINE}` exists so a first-hour user reaches the store's text arm with "
            "no account and no model; an embedding call here means the vector arm ran too"
        )


class _BothArmsStore:
    """A store satisfying `VectorSearch` and `TextSearch`, with no node in common between them.

    `hybrid` declares `needs_store = (VectorSearch, TextSearch)` regardless of `channels`, so the
    double has to satisfy both for the run to assemble — and disjoint answers are what make
    "the text arm produced this" an assertion about content rather than about a call count.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def search_vector(
        self, vector: Vector, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del vector, top_k, filter
        raise AssertionError("the vector arm was searched by a text-only document")

    async def search_text(
        self, text: str, top_k: int, filter: Filter | None = None
    ) -> Sequence[Scored[Node]]:
        del text, top_k, filter
        return (_hit("the weft crosses the warp", 7.2), _hit("a loom holds the warp", 3.1))

    async def count(self) -> int:
        return 2

    async def aclose(self) -> None:
        return None


def _hit(content: str, score: float) -> Scored[Node]:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Scored(value=node, score=score)


def _registry() -> Registry:
    registry = Registry()
    registry.add(NodeStore, "fake-store", _BothArmsStore, distribution="weft-store")
    registry.add(Embedder, "refusing-embed", _RefusingEmbedder, distribution="weft-embed")
    registry.add(Retriever, "hybrid", Hybrid, distribution="weft-retrieve")
    registry.add(Fuser, "single-list", SingleList, distribution="weft-retrieve")
    registry.add(ContextPacker, "repack", Repack, distribution="weft-retrieve")
    return registry


def _reports() -> tuple[PackReport, ...]:
    """The shipped document itself, read through the same `importlib.resources` path a real
    install uses — never a copy of its stages written into this file.
    """
    return (
        PackReport(
            pack="retrieve",
            distribution="weft-retrieve",
            status=PackStatus.ACTIVE,
            pipeline_resources=(
                PipelineResource(
                    distribution="weft-retrieve",
                    package="weft_retrieve",
                    resource=f"pipelines/{LEXICAL_PIPELINE}.yaml",
                ),
            ),
        ),
    )


def _ctx(deps: Dependencies) -> Context:
    services = ServiceRegistry()
    services.add(Dependencies, deps)
    return Context(tenant_id="t", run_id="r", trace_id="tr", locale="en", services=services)


def _deps() -> Dependencies:
    return Dependencies(
        registry=_registry(),
        reports=_reports(),
        services=ServiceSelection(embed="refusing-embed", store="fake-store"),
    )


async def test_a_named_retrieval_pipeline_runs_under_retrieve_only_with_no_model() -> None:
    """The happy path, and the repair's whole point: passages out of the text arm, no model."""
    # Arrange
    args = commands.AskArgs(
        question="what does the weft do", retrieve_only=True, pipeline=LEXICAL_PIPELINE
    )

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(_deps()))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    assert result.answer is None, (
        "`--retrieve-only` produced an answer, which means a model was asked for one"
    )
    assert result.pipeline_name == LEXICAL_PIPELINE
    assert [hit.content for hit in result.hits] == [
        "the weft crosses the warp",
        "a loom holds the warp",
    ], "the text arm's passages, best first — `R40.1`: by ranking, not by where `reverse` packed"


async def test_retrieve_only_refuses_a_pipeline_that_ends_in_a_generator() -> None:
    """The narrowed refusal: the two flags still contradict each other when the pipeline
    generates, and the message says which pipeline and what to run instead.
    """
    # Arrange — the real catalogue, so the alternatives the message offers are real names.
    deps = build_dependencies(config_path=Path("weft.toml.does-not-exist"))
    args = commands.AskArgs(
        question="what does the weft do",
        retrieve_only=True,
        pipeline="retrieve-then-generate",
    )

    # Act / Assert
    with pytest.raises(commands.ConflictingAskModeError) as refusal:
        await commands.AskCommand().run(args, _ctx(deps))
    message = str(refusal.value)
    assert "retrieve-then-generate" in message
    assert LEXICAL_PIPELINE in message, (
        "requirement 5's third clause: the refusal names a pipeline that would work, and the "
        "shipped retrieval-only document is one"
    )


def test_the_shipped_lexical_document_searches_the_text_arm_alone() -> None:
    """`R21.5`'s document half, asserted against the resolved pipeline rather than the file.

    The stage list is read through the catalogue every other command resolves names against, so a
    document that stopped being registered fails here rather than passing by not being found.
    """
    # Arrange
    deps = build_dependencies(config_path=Path("weft.toml.does-not-exist"))
    catalogue = full_catalogue(reports=deps.reports)

    # Act
    pipeline = catalogue.get(LEXICAL_PIPELINE)

    # Assert
    assert pipeline is not None, (
        f"`{LEXICAL_PIPELINE}` is not in the shipped catalogue. It is the only route from the "
        f"binary to a store's text arm that needs no model, and `28.6` is written on top of it"
    )
    retrieve = next(stage for stage in pipeline.stages if stage.id == "retrieve")
    assert retrieve.use == "hybrid"
    channels = retrieve.config["channels"]
    assert isinstance(channels, list)
    assert channels == [Channel.TEXT.value], (
        "the document must narrow `hybrid` to the text arm: both arms would embed the question, "
        "which is the model-free property this document exists to have"
    )


async def test_a_derived_pipeline_that_generates_is_refused_like_any_other() -> None:
    """The population question, asked of the refusal's own walk — `L21.5`, `L19.8`.

    `pipelines_producing` reads `pipeline.stages`, and a document written as `extends:` plus
    `replace:` **has none of its own** — so every derived generating rung slipped past the check
    that exists to stop a model being called under `--retrieve-only`. `rewrite-then-retrieve`
    extends `retrieve-then-generate` and ends in `cited-answer`; run against a project with
    `[llm.roles]` configured it would have rewritten the query *and generated an answer*, both
    model calls, before the shape check refused what came back.

    Measured from the shipped binary at Phase 28's close: exit 1, *"no `[llm.roles]` entry maps
    role 'generate'"* — the right refusal only because nothing was configured.
    """
    # Arrange
    deps = build_dependencies(config_path=Path("weft.toml.does-not-exist"))
    args = commands.AskArgs(
        question="what does the weft do",
        retrieve_only=True,
        pipeline="rewrite-then-retrieve",
    )

    # Act / Assert
    with pytest.raises(commands.ConflictingAskModeError) as refusal:
        await commands.AskCommand().run(args, _ctx(deps))
    assert "rewrite-then-retrieve" in str(refusal.value)


# --- Task 40.3 — `--explain` reads the records the pipeline's stages left on what they packed.


class _Undeclared(ExtModel):
    """A record whose producer wrote no sentence for it."""

    __namespace__: ClassVar[str] = "test-undeclared"
    __schema_version__: ClassVar[str] = "1"


@pytest.mark.parametrize("explain", [True, False])
async def test_explain_names_each_record_in_its_producers_own_sentence(
    monkeypatch: pytest.MonkeyPatch, explain: bool
) -> None:
    # Arrange
    record = AnchorPromotion(branch=AnchorBranch.PROMOTED, anchors=("WRH123",), hits_promoted=1)

    async def _packed(question: str, **_kwargs: object) -> Passages:
        return Passages(
            origin=Query(text=question),
            ext={AnchorPromotion.__namespace__: record, _Undeclared.__namespace__: _Undeclared()},
        )

    monkeypatch.setattr(commands, "run_named_retrieve", _packed)
    args = commands.AskArgs(
        question="what does WRH123 mean",
        retrieve_only=True,
        pipeline=LEXICAL_PIPELINE,
        explain=explain,
    )

    # Act
    outcome = await commands.AskCommand().run(args, _ctx(_deps()))

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, commands.AskCommandResult)
    if not explain:
        assert result.records == ()
        return
    assert result.records == (
        "anchor-promote: branch: promoted, anchors 1, hits promoted 1",
        "test-undeclared did not say what it recorded",
    )
