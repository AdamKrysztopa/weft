"""A routed ask keeps the decision it took — ledger task **44.2**.

`run_routed_ask` used to return the chosen pipeline's name and drop the `Route`, so how the
choice was reached (`outcome`, `rule`) reached no surface. It now travels on
`AskCommandResult.route`, into the `--json` envelope additively and into `--explain`. A named
ask took no routing decision, so it carries none, and its envelope is byte-identical to before.
"""

from __future__ import annotations

import json

import pytest

from tests.unit.weft_cli.routed import routed_to
from weft_cli import commands, render
from weft_cli.commands import AskCommandResult
from weft_cli.output import AskFormat
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_generate.payload import Answer, AnswerStance
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_retrieve.payload import Query, Route
from weft_store import NodeStore
from weft_store.memory import MemoryStore

_STORE = MemoryStore()


def _store_factory(config: object) -> MemoryStore:
    del config
    return _STORE


def _null_factory(config: object) -> object:
    del config
    return object()


def _ctx() -> Context:
    registry = Registry()
    registry.add(NodeStore, "memory", _store_factory, distribution="weft-store")
    registry.add(Embedder, "hash", _null_factory, distribution="weft-embed")
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


def _result(route: Route | None, *, format: AskFormat = AskFormat.TEXT) -> AskCommandResult:
    return AskCommandResult(
        question="what changed?",
        top_k=5,
        format=format,
        pipeline_name="retrieve-then-generate",
        answer=_answer(),
        route=route,
    )


async def test_a_routed_ask_keeps_the_route_it_took(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    route = routed_to("specific")

    async def _fake_run_routed_ask(*_args: object, **_kwargs: object) -> tuple[Route, Answer]:
        return route, _answer()

    monkeypatch.setattr(commands, "run_routed_ask", _fake_run_routed_ask)

    # Act
    outcome = await commands.AskCommand().run(commands.AskArgs(question="what changed?"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert result.route == route
    assert result.pipeline_name == "specific"


async def test_a_named_ask_took_no_routing_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    async def _fake_run_named_ask(*_args: object, **_kwargs: object) -> Answer:
        return _answer()

    monkeypatch.setattr(commands, "run_named_ask", _fake_run_named_ask)

    def _nothing_pending(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(commands, "_raise_if_pending", _nothing_pending)

    # Act
    outcome = await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", pipeline="retrieve-then-generate"), _ctx()
    )

    # Assert
    assert isinstance(outcome, Produced)
    result = outcome.value
    assert isinstance(result, AskCommandResult)
    assert result.route is None


def test_the_json_envelope_carries_the_route_and_omits_it_on_a_named_ask() -> None:
    # Act
    routed = render.render_outcome(
        Produced(value=_result(routed_to("specific"), format=AskFormat.JSON)), as_json=True
    )
    named = render.render_outcome(
        Produced(value=_result(None, format=AskFormat.JSON)), as_json=True
    )

    # Assert
    assert routed.stdout is not None
    assert named.stdout is not None
    envelope = json.loads(routed.stdout)
    assert envelope["route"] == {"pipeline": "specific", "outcome": "matched", "rule": "always"}
    assert envelope["envelope_version"] == json.loads(named.stdout)["envelope_version"]
    assert "route" not in json.loads(named.stdout)


async def test_explain_states_how_the_route_was_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    async def _fake_run_routed_ask(*_args: object, **_kwargs: object) -> tuple[Route, Answer]:
        return routed_to("specific"), _answer()

    monkeypatch.setattr(commands, "run_routed_ask", _fake_run_routed_ask)

    # Act
    explained = await commands.AskCommand().run(
        commands.AskArgs(question="what changed?", explain=True), _ctx()
    )
    plain = await commands.AskCommand().run(commands.AskArgs(question="what changed?"), _ctx())

    # Assert
    assert isinstance(explained, Produced)
    assert isinstance(plain, Produced)
    assert isinstance(explained.value, AskCommandResult)
    assert isinstance(plain.value, AskCommandResult)
    assert "route: matched by rule 'always'" in explained.value.explanations
    assert plain.value.explanations == ()
