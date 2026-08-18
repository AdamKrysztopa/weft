"""`ExampleRoutingPolicy` — a stranger's `RoutingPolicy`: always the one configured pipeline.

The counterpart to `weft_retrieve.routing.Always`, and stated for the same reason that class
exists — `10 lines, exists only to prove the first two [threshold-ladder, nearest-description]
are genuinely interchangeable` — a policy this simple is what proves a `RoutingPolicy` is
implementable from outside the workspace at all, with no coupling to `QueryScorer`.
"""

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Route, RouteCandidate, RuleOutcome, Scorecard

_DEFAULT_PIPELINE = "default"


class ExampleRouteConfig(BaseModel):
    """`ExampleRoutingPolicy`'s `with:` config — one real field, defaulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(default=_DEFAULT_PIPELINE, min_length=1)


class ExampleRoutingPolicy:
    """Always names the same, configured pipeline, ignoring the `Scorecard` entirely.

    Satisfies `weft_retrieve.contract.RoutingPolicy` structurally — this class never
    imports it.
    """

    def __init__(self, config: ExampleRouteConfig | None = None) -> None:
        self._config = config if config is not None else ExampleRouteConfig()

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]:
        del ctx
        return Produced(
            value=Route(
                pipeline=self._config.pipeline,
                outcome=RuleOutcome.MATCHED,
                rule="example-always",
                scorecard=payload,
            )
        )

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]:
        del candidates  # this policy never looks at what is offered — see the module docstring
        return frozenset({self._config.pipeline})
