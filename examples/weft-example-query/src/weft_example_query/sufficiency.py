"""`ExampleSufficiency` — a stranger's `Sufficiency`: enough iff there is any evidence at all.

`observed` is always `True` here because this plugin genuinely looked — it read `evidence`
and answered. `weft_retrieve.contract.Sufficiency`'s own rule: an implementation that could
not look answers `observed=False`, never `sufficient=False` standing in for "I could not tell".
"""

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Assessment, Passages, Query

_ENOUGH_PASSAGES = 3


class ExampleSufficiency:
    """Sufficient once at least one passage is in hand; confident once `_ENOUGH_PASSAGES` are.

    Satisfies `weft_retrieve.contract.Sufficiency` structurally — this class never imports it.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]:
        del ctx, draft
        sufficient = bool(evidence.passages)
        confidence = min(1.0, len(evidence.passages) / _ENOUGH_PASSAGES) if sufficient else 0.0
        missing = () if sufficient else (question.text,)
        return Produced(
            value=Assessment(
                sufficient=sufficient, confidence=confidence, missing=missing, observed=True
            )
        )
