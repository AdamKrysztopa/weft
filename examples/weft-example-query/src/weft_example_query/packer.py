"""`ExampleContextPacker` — a stranger's `ContextPacker`: top `top_n`, labelled `[1]`, `[2]`, …

Labels are assigned here and here alone — `weft_retrieve.payload.Passages`'s own validator
refuses a blank or a repeated label, which this plugin satisfies by construction: every
selected passage gets exactly one label, in rank order, and none is skipped.
"""

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Passages, Ranking

_DEFAULT_TOP_N = 5


class ExampleContextPackerConfig(BaseModel):
    """`ExampleContextPacker`'s `with:` config — one real field, defaulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_n: int = Field(default=_DEFAULT_TOP_N, ge=1)


class ExampleContextPacker:
    """Takes the top `top_n` hits and labels them `[1]`, `[2]`, … in rank order.

    Satisfies `weft_retrieve.contract.ContextPacker` structurally — this class never
    imports it.
    """

    def __init__(self, config: ExampleContextPackerConfig | None = None) -> None:
        self._config = config if config is not None else ExampleContextPackerConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Passages]:
        del ctx
        selected = payload.hits[: self._config.top_n]
        labelled = tuple(
            passage.model_copy(update={"label": f"[{index + 1}]"})
            for index, passage in enumerate(selected)
        )
        return Produced(value=Passages(origin=payload.origin, passages=labelled, ext=payload.ext))
