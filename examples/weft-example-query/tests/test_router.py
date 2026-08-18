"""This pack's own tests for `ExampleRoutingPolicy`."""

from weft_example_query.router import ExampleRouteConfig, ExampleRoutingPolicy

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import RoutingPolicy
from weft_retrieve.payload import Query, RuleOutcome, Scorecard


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_router_always_names_its_configured_pipeline_through_the_seam() -> None:
    # Arrange
    policy = ExampleRoutingPolicy(ExampleRouteConfig(pipeline="a-third-party-pipeline"))
    wrapped = wrap(
        policy.run,
        distribution="weft-example-query",
        contract="RoutingPolicy",
        plugin="example-always",
    )
    scorecard = Scorecard(query=Query(text="anything"), scores={"complexity": 0.9})

    # Act
    outcome = await wrapped(scorecard, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.pipeline == "a-third-party-pipeline"
    assert outcome.value.outcome is RuleOutcome.MATCHED
    assert outcome.value.scorecard == scorecard


async def test_reachable_names_only_its_own_configured_pipeline() -> None:
    # Arrange
    policy = ExampleRoutingPolicy(ExampleRouteConfig(pipeline="only-this-one"))

    # Act
    names = await policy.reachable(())

    # Assert
    assert names == frozenset({"only-this-one"})


async def test_router_satisfies_the_routingpolicy_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(ExampleRoutingPolicy(), RoutingPolicy)
