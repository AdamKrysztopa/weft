"""`weft route explain "<q>"` shows why a question would go where it goes — task **44.16**.

It runs the configured router — its scorer and policy, never the rung it picks — and prints the
query profile, the corpus profile (from the one `list_sources()` read an ask makes) and the
`Route`. It reads only and answers nothing; under `--json` it is one object with `query_profile`,
`corpus_profile` and `route`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from weft_cli import route_explain as route_explain_module
from weft_cli.exit_codes import ExitCode
from weft_cli.render import render_outcome
from weft_cli.route_explain import RouteExplainArgs, RouteExplainCommand
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_engine.services import ServiceSelection
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import Produced, SourceId
from weft_kernel.registry import Registry
from weft_retrieve.payload import Query, Route, RuleOutcome, Scorecard
from weft_store import NodeStore, SourceRecord, SourceStats
from weft_store.memory import MemoryStore


def _memory(config: object) -> MemoryStore:
    del config
    return MemoryStore()


def _embedder(config: object) -> object:
    del config
    return object()


def _ctx() -> Context:
    registry = Registry()
    registry.add(NodeStore, "memory", _memory, distribution="weft-store")
    registry.add(Embedder, "hash", _embedder, distribution="weft-embed")
    deps = Dependencies(
        registry=registry,
        reports=(PackReport(pack="store", distribution="weft-store", status=PackStatus.ACTIVE),),
        services=ServiceSelection(store="memory"),
    )
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")
    ctx.services.add(Dependencies, deps)
    return ctx


def _records() -> tuple[SourceRecord, ...]:
    return (
        SourceRecord(
            id=SourceId("a"),
            uri="file:///a.txt",
            content_hash="a",
            indexed_at=datetime.now(UTC),
            pipeline="index-text",
            stats=SourceStats(leaves=4, characters=400, tokens=None, tokenizer=None),
        ),
    )


def _route_measuring(features: dict[str, int | float | bool]) -> Route:
    """A `Route` whose scorer measured exactly `features` — what the router itself saw."""
    return Route(
        pipeline="retrieve-then-generate",
        outcome=RuleOutcome.MATCHED,
        rule="always",
        scorecard=Scorecard(query=Query(text="q"), scores={}, features=features),
    )


_MEASURED: dict[str, int | float | bool] = {
    "query.word_count": 5,
    "query.cue.comparison": False,
    "corpus.documents": 1,
}


@pytest.fixture
def explained(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def _explain(question: str, **_kwargs: object) -> Route:
        asked.append(question)
        return _route_measuring(_MEASURED)

    async def _records_read(deps: object, target: object) -> Produced[tuple[SourceRecord, ...]]:
        del deps, target
        return Produced(value=_records())

    monkeypatch.setattr(route_explain_module, "explain_route", _explain)
    monkeypatch.setattr(route_explain_module, "source_records", _records_read)
    return asked


async def test_the_text_output_names_both_profiles_and_the_route(explained: list[str]) -> None:
    # Act
    outcome = await RouteExplainCommand().run(
        RouteExplainArgs(question="How many looms are there?"), _ctx()
    )
    rendered = render_outcome(outcome)

    # Assert
    stdout = rendered.stdout or ""
    assert explained == ["How many looms are there?"]
    assert "route: retrieve-then-generate" in stdout
    assert "query.word_count:" in stdout
    assert "corpus.documents: 1" in stdout
    assert "corpus.leaves: 4" in stdout
    assert rendered.exit_code is ExitCode.SUCCESS


async def test_the_json_output_is_one_object_with_both_profiles_and_the_route(
    explained: list[str],
) -> None:
    # Act
    outcome = await RouteExplainCommand().run(
        RouteExplainArgs(question="How many looms are there?"), _ctx()
    )
    document = json.loads(render_outcome(outcome, as_json=True).stdout or "")

    # Assert
    assert {"query_profile", "corpus_profile", "route"} <= set(document)
    assert document["route"]["pipeline"] == "retrieve-then-generate"
    assert document["corpus_profile"]["documents"] == 1
    assert "query.word_count" in document["query_profile"]


def test_the_command_only_reads() -> None:
    # Assert
    assert RouteExplainCommand.permission_class is PermissionClass.READ
    assert RouteExplainCommand.help


async def _json_of(monkeypatch: pytest.MonkeyPatch, route: Route) -> dict[str, object]:
    async def _explain(question: str, **_kwargs: object) -> Route:
        del question
        return route

    async def _records_read(deps: object, target: object) -> Produced[tuple[SourceRecord, ...]]:
        del deps, target
        return Produced(value=_records())

    monkeypatch.setattr(route_explain_module, "explain_route", _explain)
    monkeypatch.setattr(route_explain_module, "source_records", _records_read)
    outcome = await RouteExplainCommand().run(RouteExplainArgs(question="q"), _ctx())
    return json.loads(render_outcome(outcome, as_json=True).stdout or "")


async def test_the_query_profile_is_what_the_routers_own_scorer_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R44.17: a custom cue set or a third-party scorer is shown as itself."""
    # Arrange — a scorer emitting a feature no default profiler knows, beside the corpus ones.
    route = _route_measuring({"query.word_count": 9, "acme.risk": 0.9, "corpus.documents": 1})

    # Act
    document = await _json_of(monkeypatch, route)

    # Assert
    assert document["query_profile"] == {"query.word_count": 9, "acme.risk": 0.9}


async def test_a_router_whose_scorer_measures_no_feature_shows_an_empty_query_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Act — an LLM scorer emits scores, not features: Weft's defaults are not its measurement.
    document = await _json_of(monkeypatch, _route_measuring({}))

    # Assert
    assert document["query_profile"] == {}
