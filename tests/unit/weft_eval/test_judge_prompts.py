"""Each judge names the prompt it sends — task 44.4.

A run record digests each judge's prompt, so the digest must be of the prompt the judge actually
sends. Each judge declares it as `prompt`, and what reaches the model is that prompt's text: the
record's digest and the judge's call cannot name two different prompts.
"""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import BaseModel

from weft_embed.contract import Embedder
from weft_embed.hash_embedder import HashEmbedder
from weft_eval import Settings, register
from weft_eval.contract import GenerationSample
from weft_eval.judges import (
    AnswerCompleteness,
    AnswerCorrectness,
    AnswerRelevance,
    ContextRecall,
    ContextRelevance,
    Faithfulness,
    JudgeConfig,
)
from weft_eval.prompts import FaithfulnessJudgement, StatementSupport
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompt

_JUDGES = (
    Faithfulness,
    ContextRecall,
    ContextRelevance,
    AnswerRelevance,
    AnswerCorrectness,
    AnswerCompleteness,
)


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script of typed replies."""

    def __init__(self, replies: list[BaseModel]) -> None:
        self._replies = [reply.model_dump_json() for reply in replies]
        self.calls = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> object:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        del rendered, role, ctx
        reply = self._replies[self.calls]
        self.calls += 1
        return Produced(value=Completion(text=reply, model="stub-model"))

    async def close(self) -> None: ...


def _ctx(llm: _StubLLM, *, embedder: HashEmbedder | None = None) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    if embedder is not None:
        services.add(Embedder, embedder)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


class _CapturingLLM(_StubLLM):
    """`_StubLLM`, also keeping each rendered prompt it was sent."""

    def __init__(self, replies: list[FaithfulnessJudgement]) -> None:
        super().__init__(list(replies))
        self.sent: list[Rendered] = []

    async def complete(
        self, rendered: Rendered, *, role: str, ctx: Context
    ) -> Produced[Completion]:
        self.sent.append(rendered)
        return await super().complete(rendered, role=role, ctx=ctx)


async def test_a_judge_sends_the_prompt_it_declares() -> None:
    # Arrange
    llm = _CapturingLLM(
        [FaithfulnessJudgement(statements=(StatementSupport(statement="s", supported=True),))]
    )
    sample = GenerationSample(
        query="q", prediction="The sky is blue.", reference="r", contexts=("The sky is blue.",)
    )

    # Act
    await Faithfulness(JudgeConfig()).evaluate(sample, _ctx(llm))

    # Assert
    assert llm.sent
    sent = llm.sent[0]
    declared = Faithfulness.prompt.texts["en"].system
    assert declared
    assert sent.prompt == Faithfulness.prompt.name
    assert sent.prompt_version == Faithfulness.prompt.prompt_version
    assert sent.conversation.messages[0].content == declared


@pytest.mark.parametrize("judge", _JUDGES, ids=lambda judge: judge.__name__)
def test_every_judge_declares_the_prompt_registered_under_that_prompt_s_name(
    judge: type[Faithfulness],
) -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()

    # Act
    entry = registry.entry(Prompt, judge.prompt.name)

    # Assert
    assert entry.factory is judge.prompt
