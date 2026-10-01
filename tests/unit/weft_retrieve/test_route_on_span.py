"""A routing decision is on the policy stage's span — carried repair **R44.2**, G28.

`Route`'s docstring promised the decision was auditable from the span, and the seam set only
pack, contract and plugin. `Route` now declares `telemetry_attributes()` and the seam applies
them, so the router's own stage span names the pipeline chosen, how it was reached and the rule
that matched. Run here through the shipped `route-fixed` document and the real `Runner`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from weft_cli.compile import to_specs
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine import registry_bootstrap
from weft_kernel import seam
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.runner import Runner
from weft_retrieve import RETRIEVE_CONTRACT_VERSION
from weft_retrieve.payload import Query, Route, RuleOutcome, Scorecard


def _route(rule: str, outcome: RuleOutcome) -> Route:
    return Route(
        pipeline="hyde-fanout-rrf",
        outcome=outcome,
        rule=rule,
        scorecard=Scorecard(query=Query(text="why?"), scores={}),
    )


def test_a_route_declares_its_pipeline_outcome_and_rule() -> None:
    # Act
    attributes = _route("many-hops", RuleOutcome.MATCHED).telemetry_attributes()

    # Assert
    assert attributes["weft.route.pipeline"] == "hyde-fanout-rrf"
    assert attributes["weft.route.outcome"] == "matched"
    assert attributes["weft.route.rule"] == "many-hops"


def test_a_method_on_a_returned_model_is_a_minor_contract_version() -> None:
    # Assert — `09`'s two-audience table, "Add an optional field to a returned model": minor for
    # both audiences, since a policy constructs `Route` and inherits the method.
    assert RETRIEVE_CONTRACT_VERSION == "1.6.0"


def test_a_route_that_matched_no_rule_names_none() -> None:
    # Act
    attributes = _route("", RuleOutcome.FELL_THROUGH).telemetry_attributes()

    # Assert
    assert attributes["weft.route.outcome"] == "fell-through"
    assert attributes.get("weft.route.rule", "") == ""


async def test_the_shipped_router_s_decision_is_on_its_policy_span(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    monkeypatch.chdir(tmp_path)
    config = tmp_path / "weft.toml"
    config.write_text("", encoding="utf-8")
    deps = registry_bootstrap.build_dependencies(config_path=config)
    catalogue = full_catalogue(reports=deps.reports)
    resolved = resolve_in_catalogue(
        catalogue["route-fixed"],
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    specs = to_specs(resolved, registry=deps.registry, reports=deps.reports)
    runner = Runner(deps.registry)
    runnable = runner.resolve(specs, tenant_id="tenant-a", entry_type=Query)
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(seam, "_tracer", provider.get_tracer("weft-test"))
    ctx = Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")

    # Act
    outcome = await runner.run_once(runnable, Query(text="what changed in 2024?"), ctx)

    # Assert
    assert isinstance(outcome, Produced)
    route = outcome.value
    assert isinstance(route, Route)
    policy_spans = [
        span
        for span in exporter.get_finished_spans()
        if span.attributes is not None and span.attributes.get("weft.plugin") == "always"
    ]
    assert len(policy_spans) == 1
    attributes = policy_spans[0].attributes
    assert attributes is not None
    assert attributes["weft.route.pipeline"] == route.pipeline
    assert attributes["weft.route.outcome"] == route.outcome.value
