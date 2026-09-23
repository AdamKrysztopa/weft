"""Ledger task **43.9** — `weft ask` never answers from a layer that is not built everywhere.

Owner's Q2, settled at Phase 43's opening: the router leaves out a rung whose `route.requires`
layer is pending, and `--explain` says which and why; `--pipeline` naming one is refused, naming
the layer, how far it has got and the base document the corpus was indexed with, unless
`--allow-pending` is given, which answers and states the pending layer under the answer. The
counts come from the same one `list_sources` read the coverage line already takes (`43.4`).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from weft_cli import commands, render
from weft_cli.commands import AskCommandResult
from weft_cli.coverage import LayerCoverage, layer_coverage_of, ready_layers
from weft_cli.layers import UnknownLayerError
from weft_cli.output import AskFormat
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_generate.payload import Answer, AnswerStance
from weft_index import Expander
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_retrieve.payload import Query
from weft_store import LayerRecord, LayerStatus, NodeStore, SourceRecord, SourceStatus
from weft_store.memory import MemoryStore

_WHEN = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
_LAYER = "enrich-with-questions"
_STORES: list[MemoryStore] = []


def _store_factory(config: object) -> MemoryStore:
    del config
    return _STORES[-1]


def _null_factory(config: object) -> object:
    del config
    return object()


def _record(name: str, status: SourceStatus, layer: LayerStatus | None) -> SourceRecord:
    layers = (
        ()
        if layer is None
        else (LayerRecord(name=_LAYER, pipeline_identity="q", status=layer, attempts=1, at=_WHEN),)
    )
    return SourceRecord(
        id=SourceId(f"file:///corpus/{name}"),
        uri=f"file:///corpus/{name}",
        content_hash=f"hash-{name}",
        indexed_at=_WHEN,
        pipeline="index-text",
        status=status,
        layers=layers,
    )


_TWO_OF_THREE = (
    _record("a.txt", SourceStatus.ACTIVE, LayerStatus.ACTIVE),
    _record("b.txt", SourceStatus.ACTIVE, LayerStatus.ACTIVE),
    _record("c.txt", SourceStatus.ACTIVE, LayerStatus.FAILED),
    _record("d.txt", SourceStatus.FAILED, None),
)
_ALL_THREE = (
    _record("a.txt", SourceStatus.ACTIVE, LayerStatus.ACTIVE),
    _record("b.txt", SourceStatus.ACTIVE, LayerStatus.ACTIVE),
    _record("c.txt", SourceStatus.ACTIVE, LayerStatus.ACTIVE),
)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A project whose own `pipelines/` holds one rung that requires the questions layer."""
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "needs-questions.yaml").write_text(
        "name: needs-questions\n"
        "vars:\n"
        "  route.summary: answers from the generated questions\n"
        f"  route.requires: {_LAYER}\n"
        "stages:\n"
        "  - {id: retrieve, use: vector-top-k}\n"
    )
    # R43.13: a required layer is checked against the installed layers, so the fixture has one.
    (tmp_path / "pipelines" / f"{_LAYER}.yaml").write_text(
        f"name: {_LAYER}\nstages:\n  - {{id: questions, use: echo-questions}}\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def _ctx_with(records: tuple[SourceRecord, ...]) -> Context:
    _STORES.append(MemoryStore())
    for record in records:
        await _STORES[-1].put_source(record)
    registry = Registry()
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
    registry.add(Expander, "echo-questions", _null_factory, distribution="weft-index")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _answer() -> Answer:
    return Answer(
        origin=Query(text="what changed?"),
        text="the answer",
        stance=AnswerStance.ANSWERED,
        citations=(),
        used=(),
        answered_by="scripted",
    )


class _Named:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, *_args: object, **_kwargs: object) -> Answer:
        self.called = True
        return _answer()


class _Routed:
    def __init__(self) -> None:
        self.kwargs: dict[str, object] = {}

    async def __call__(self, *_args: object, **kwargs: object) -> tuple[str, Answer]:
        self.kwargs = kwargs
        return "retrieve-then-generate", _answer()


def test_each_layer_is_counted_against_the_sources_that_are_indexed() -> None:
    # Act
    layers = layer_coverage_of(_TWO_OF_THREE)

    # Assert
    assert layers == (LayerCoverage(name=_LAYER, built=2, of=3),)
    assert ready_layers(layers) == frozenset()
    assert ready_layers(layer_coverage_of(_ALL_THREE)) == frozenset({_LAYER})


async def test_naming_a_rung_whose_layer_is_pending_is_refused_before_it_runs(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    del project
    named = _Named()
    monkeypatch.setattr(commands, "run_named_ask", named)
    ctx = await _ctx_with(_TWO_OF_THREE)

    # Act
    with pytest.raises(commands.PendingLayerError) as refused:
        await commands.AskCommand().run(
            commands.AskArgs(question="what changed?", pipeline="needs-questions"), ctx
        )

    # Assert
    message = str(refused.value)
    assert f"'{_LAYER}'" in message
    assert "2 of 3" in message
    assert "'index-text'" in message
    assert "--allow-pending" in message
    assert not named.called


async def test_allow_pending_answers_and_states_the_pending_layer(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    del project
    named = _Named()
    monkeypatch.setattr(commands, "run_named_ask", named)
    ctx = await _ctx_with(_TWO_OF_THREE)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", pipeline="needs-questions", allow_pending=True),
        ctx,
    )

    # Assert
    assert named.called
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert result.layers == (LayerCoverage(name=_LAYER, built=2, of=3),)


async def test_a_rung_whose_layer_is_built_everywhere_runs_when_named(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    del project
    named = _Named()
    monkeypatch.setattr(commands, "run_named_ask", named)
    ctx = await _ctx_with(_ALL_THREE)

    # Act
    await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", pipeline="needs-questions"), ctx
    )

    # Assert
    assert named.called


async def test_the_router_is_told_which_layers_are_built_everywhere(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    del project
    routed = _Routed()
    monkeypatch.setattr(commands, "run_routed_ask", routed)
    pending = await _ctx_with(_TWO_OF_THREE)
    await commands.AskCommand().run(commands.AskArgs(question="what changed?"), pending)
    told_pending = routed.kwargs.get("ready_layers")
    built = await _ctx_with(_ALL_THREE)

    # Act
    await commands.AskCommand().run(commands.AskArgs(question="what changed?"), built)

    # Assert
    assert told_pending == frozenset()
    assert routed.kwargs.get("ready_layers") == frozenset({_LAYER})


async def test_explain_names_each_rung_left_out_and_why(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    del project
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    ctx = await _ctx_with(_TWO_OF_THREE)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", explain=True), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert (
        f"not offered: 'needs-questions' needs the '{_LAYER}' layer, built on 2 of 3 sources"
        in result.explanations
    )


def _result(layers: tuple[LayerCoverage, ...], *, format: AskFormat) -> AskCommandResult:
    return AskCommandResult(
        question="what changed?",
        top_k=5,
        format=format,
        pipeline_name="needs-questions",
        answer=_answer(),
        layers=layers,
    )


def test_a_pending_layer_is_stated_under_the_answer_and_a_built_one_is_not() -> None:
    # Act
    pending = render.render_outcome(
        Produced(
            value=_result((LayerCoverage(name=_LAYER, built=412, of=1000),), format=AskFormat.TEXT)
        )
    )
    built = render.render_outcome(
        Produced(value=_result((LayerCoverage(name=_LAYER, built=3, of=3),), format=AskFormat.TEXT))
    )
    none = render.render_outcome(Produced(value=_result((), format=AskFormat.TEXT)))

    # Assert
    assert pending.stdout is not None
    assert f"layers: {_LAYER} 412/1,000" in pending.stdout
    assert built == none


def test_the_json_envelope_carries_a_pending_layer_and_omits_a_built_one() -> None:
    # Act
    pending = render.render_outcome(
        Produced(
            value=_result((LayerCoverage(name=_LAYER, built=412, of=1000),), format=AskFormat.JSON)
        ),
        as_json=True,
    )
    built = render.render_outcome(
        Produced(
            value=_result((LayerCoverage(name=_LAYER, built=3, of=3),), format=AskFormat.JSON)
        ),
        as_json=True,
    )
    none = render.render_outcome(Produced(value=_result((), format=AskFormat.JSON)), as_json=True)

    # Assert
    assert pending.stdout is not None
    assert json.loads(pending.stdout)["layers"] == [{"name": _LAYER, "built": 412, "of": 1000}]
    assert built == none


def _misspelt(project: Path) -> None:
    (project / "pipelines" / "needs-questions.yaml").write_text(
        "name: needs-questions\n"
        "vars:\n"
        "  route.summary: answers from the generated questions\n"
        "  route.requires: enrich-with-questons\n"
        "stages:\n"
        "  - {id: retrieve, use: vector-top-k}\n"
    )


async def test_naming_a_rung_whose_required_layer_is_not_installed_is_refused_listing_them(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — R43.13: the pending refusal's own remedy then failed with UnknownLayerError.
    _misspelt(project)
    named = _Named()
    monkeypatch.setattr(commands, "run_named_ask", named)
    ctx = await _ctx_with(_ALL_THREE)

    # Act
    with pytest.raises(UnknownLayerError) as refused:
        await commands.AskCommand().run(
            commands.AskArgs(question="what changed?", pipeline="needs-questions"), ctx
        )

    # Assert
    message = str(refused.value)
    assert "'needs-questions'" in message
    assert "route.requires" in message
    assert "'enrich-with-questons'" in message
    assert refused.value.valid_options == (_LAYER,)
    assert not named.called


async def test_a_routed_ask_over_a_rung_requiring_an_uninstalled_layer_is_refused(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a typo in a document is a fault, never a layer that is merely not built yet.
    _misspelt(project)
    routed = _Routed()
    monkeypatch.setattr(commands, "run_routed_ask", routed)
    ctx = await _ctx_with(_ALL_THREE)

    # Act
    with pytest.raises(UnknownLayerError) as refused:
        await commands.AskCommand().run(commands.AskArgs(question="what changed?"), ctx)

    # Assert
    assert "'enrich-with-questons'" in str(refused.value)
    assert routed.kwargs == {}


async def test_explain_leaves_out_a_document_the_router_could_never_offer(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — R43.21: no `route.summary`, so it is never a candidate whatever its layer.
    (project / "pipelines" / "unroutable.yaml").write_text(
        "name: unroutable\n"
        "vars:\n"
        f"  route.requires: {_LAYER}\n"
        "stages:\n"
        "  - {id: retrieve, use: vector-top-k}\n"
    )
    monkeypatch.setattr(commands, "run_routed_ask", _Routed())
    ctx = await _ctx_with(_TWO_OF_THREE)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", explain=True), ctx
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert not any("'unroutable'" in line for line in result.explanations)
    assert any("'needs-questions'" in line for line in result.explanations)
