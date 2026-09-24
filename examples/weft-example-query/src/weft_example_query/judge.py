"""`ExampleLlmJudge` — a stranger's `Reranker` that asks a model whether each passage answers.

Repair **R43.35**: its role field is `judge_role`, a name no first-party plugin uses. It is
declared `Annotated[str, LLMRole()]`, which is what a routed ask reads to learn the role a rung
calls a model under — so a rung naming this plugin with that role unmapped is left out before
any model call rather than refusing after one.
"""

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm import LLMRole
from weft_llm.contract import LLM
from weft_llm.payload import Conversation, Message, MessageRole, Rendered
from weft_retrieve.payload import Passage, Ranking

NAME = "example-llm-judge"


class ExampleJudgeConfig(BaseModel):
    """`ExampleLlmJudge`'s `with:` shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_role: Annotated[str, LLMRole()] = Field(default="judge", min_length=1)


class ExampleLlmJudge:
    """Keeps each passage the model judges to answer the original question, in order.

    Satisfies `weft_retrieve.contract.Reranker` structurally — this class never imports it.
    """

    config_model: ClassVar[type[ExampleJudgeConfig]] = ExampleJudgeConfig

    def __init__(self, config: ExampleJudgeConfig | None = None) -> None:
        self._config = config if config is not None else ExampleJudgeConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Keep only the hits the model says help answer the question.

        Args:
            payload: The ranking to judge.
            ctx: The run's context, from which `LLM` is required.

        Returns:
            `Produced` carrying the kept hits, re-ranked, or the first non-`Produced` outcome a
            model call returned.
        """
        llm = ctx.require(LLM)
        kept: list[Passage] = []
        for hit in payload.hits:
            rendered = Rendered(conversation=Conversation(messages=(_ask(payload, hit),)))
            judged = await llm.complete(rendered, role=self._config.judge_role, ctx=ctx)
            if not isinstance(judged, Produced):
                return judged
            if judged.value.text.strip().lower().startswith("yes"):
                kept.append(hit)
        hits = tuple(hit.model_copy(update={"rank": rank}) for rank, hit in enumerate(kept))
        return Produced(value=payload.model_copy(update={"hits": hits}))


def _ask(payload: Ranking, hit: Passage) -> Message:
    return Message(
        role=MessageRole.USER,
        content=(
            "Answer yes or no: does this passage help answer the question?\n"
            f"Question: {payload.origin.text}\n"
            f"Passage: {hit.node.content}"
        ),
    )
