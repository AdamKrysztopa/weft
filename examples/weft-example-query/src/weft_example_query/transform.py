"""`ExampleQueryTransform` — a stranger's `QueryTransform`: adds one shouted variant.

**`QuerySet.origin` is never rewritten** — `weft_retrieve.payload.QuerySet`'s own contract
term, which nothing checks structurally, so every query-path plugin in this pack carries the
obligation as its own test, exactly the discipline ledger 2.13–2.26's own first-party plugins
carry (`weft_retrieve.payload`'s module docstring: "the teeth are owed by the plugins").
"""

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Query, QueryOrigin, QuerySet

NAME = "example-emphasize"


class ExampleQueryTransform:
    """Adds one derived query — the original text, upper-cased — beside every query it is
    handed. Satisfies `weft_retrieve.contract.QueryTransform` structurally.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]:
        del ctx
        shouted = Query(
            text=payload.origin.text.upper(), origin=QueryOrigin.DERIVED, produced_by=NAME
        )
        return Produced(
            value=QuerySet(
                origin=payload.origin,
                queries=(*payload.queries, shouted),
                history=payload.history,
                ext=payload.ext,
            )
        )
