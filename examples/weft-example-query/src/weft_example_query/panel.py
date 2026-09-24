"""`ExampleJudgePanel` — a stranger's `Reranker` that composes other rerankers into a panel.

Repair **R43.42**: each panelist is a reranker resolved by name through `StageLookup`, named by
a field this pack spells its own way — `reranker`, configured by `settings` — and declared
`Annotated[str, SubPlugin(config="settings")]`. That declaration is what a routed ask follows
into each panelist's own config, so a rung whose panelist calls a model under an unmapped role
is left out before any model call rather than refusing after one.
"""

from collections.abc import Mapping
from typing import Annotated, ClassVar, cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import NodeId, Outcome, Produced
from weft_kernel.runner import Stage
from weft_retrieve import SubPlugin
from weft_retrieve.contract import Reranker, StageLookup
from weft_retrieve.payload import Ranking

NAME = "example-judge-panel"


class ExamplePanelist(BaseModel):
    """One seat on the panel: a registered `Reranker` and its own `with:` block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reranker: Annotated[str, SubPlugin(config="settings")]
    settings: Mapping[str, object] | None = None


class ExamplePanelConfig(BaseModel):
    """`ExampleJudgePanel`'s `with:` shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    panelists: tuple[ExamplePanelist, ...]


class ExampleJudgePanel:
    """Keeps each passage any panelist keeps, in the input's order, re-ranked from 0.

    Satisfies `weft_retrieve.contract.Reranker` structurally, and names it only to ask
    `StageLookup` for each panelist.
    """

    config_model: ClassVar[type[ExamplePanelConfig]] = ExamplePanelConfig

    def __init__(self, config: ExamplePanelConfig) -> None:
        self._config = config

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        lookup = ctx.require(StageLookup)
        reranker = cast("type[Stage[Ranking, Ranking]]", Reranker)
        kept: set[NodeId] = set()
        for panelist in self._config.panelists:
            judge = await lookup.build(reranker, panelist.reranker, panelist.settings)
            judged = await judge(payload, ctx)
            if not isinstance(judged, Produced):
                return judged
            kept.update(hit.node.id for hit in judged.value.hits)
        chosen = (hit for hit in payload.hits if hit.node.id in kept)
        hits = tuple(hit.model_copy(update={"rank": rank}) for rank, hit in enumerate(chosen))
        return Produced(value=payload.model_copy(update={"hits": hits}))
