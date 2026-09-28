"""A `Route` for a test double of `weft_cli.route_ask.run_routed_ask`.

Ledger task **44.2**: `run_routed_ask` returns the `Route` it took, not only its pipeline name,
so a double answering for it builds one here rather than each file inventing its own.
"""

from weft_retrieve.payload import Query, Route, RuleOutcome, Scorecard


def routed_to(pipeline: str) -> Route:
    """The `Route` `always` would have produced for `pipeline`."""
    return Route(
        pipeline=pipeline,
        outcome=RuleOutcome.MATCHED,
        rule="always",
        scorecard=Scorecard(query=Query(text="a routed question"), scores={}),
    )
