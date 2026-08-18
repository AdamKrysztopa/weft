"""`ExampleQueryScorer` — a stranger's `QueryScorer`: word count as a stand-in for complexity.

Never a model call, on `10` §1.1's `query-scorer` row's own precedent for a keyword-shaped
scorer — this one is even simpler, a pure function of word count, deliberately, so this
pack's own tests need no `LLM` service either.
"""

from typing import Final

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Query, Scorecard

#: A question this long or longer scores `complexity=1.0` — a cap, not a claim about English.
_LONG_QUERY_WORDS: Final[int] = 20


class ExampleQueryScorer:
    """Two dimensions, both derived from word count alone: `complexity` and its complement.

    Satisfies `weft_retrieve.contract.QueryScorer` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Query, ctx: Context) -> Outcome[Scorecard]:
        del ctx
        complexity = min(1.0, len(payload.text.split()) / _LONG_QUERY_WORDS)
        scores = {"complexity": complexity, "specificity": 1.0 - complexity}
        return Produced(value=Scorecard(query=payload, scores=scores))
