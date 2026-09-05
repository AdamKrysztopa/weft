"""Unit tests for `weft_index.hypothetical_questions`.

Mirrors `packages/weft-rag/src/weft_index/hypothetical_questions.py`. Ledger **2.31**:
"a chunk can be found by a question it answers rather than by the words it contains,
because a generated question is its own retrievable node." Covers the happy path (two
nodes, each getting its own derived question-nodes, correctly parented and marked), the
edge case (one node's generation degrades — the node itself survives, unchanged, with no
derived children — while its sibling's own generation is unaffected), the error case (an
unmapped `prompt:` name is a configuration mistake, not a model failure, and propagates
rather than degrading), and a drive through `weft_kernel.seam.wrap`.

**`Prompts` is a stub and `GenerateQuestionsPrompt.render` is real** — the same split
`weft_retrieve.transforms`'s own test module takes for `StageLookup`/`Prompt.render`, for
the identical reason: rendering is exercised against the shape it actually produces, and
only the model's answer is scripted.
"""

import pytest

from weft_index.contract import Expander
from weft_index.hypothetical_questions import (
    NAME,
    HypotheticalQuestionGenerator,
    HypotheticalQuestionsConfig,
)
from weft_index.payload import Representation
from weft_index.prompts import GENERATE_QUESTIONS_NAME, GenerateQuestionsPrompt
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompts

_SOURCE = SourceId("doc-1")


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({_SOURCE}),
    )


class _StubPrompts:
    """A `Prompts` holding this pack's own prompt for real — same shape `test_transforms.py`'s
    `_StubLookup` takes for `StageLookup`, narrowed to the one method this pack calls.
    """

    def __init__(self) -> None:
        self._prompt = GenerateQuestionsPrompt()
        self.asked: list[str] = []

    async def render(self, name: str, values: object, ctx: Context) -> Outcome[Rendered]:
        self.asked.append(name)
        if name != GENERATE_QUESTIONS_NAME:
            raise KeyError(name)
        return await self._prompt.render(values, ctx)  # type: ignore[arg-type]


class _ScriptedLLM:
    """An `LLM` answering `complete` from a per-call script, keyed by call order."""

    def __init__(self, replies: list[Outcome[Completion]]) -> None:
        self._replies = replies
        self.calls: list[str] = []

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, ctx
        self.calls.append(role)
        return self._replies[min(len(self.calls) - 1, len(self._replies) - 1)]

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("hypothetical-questions never asks for structured output")

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("hypothetical-questions never checks tier 1 availability")

    async def close(self) -> None: ...


def _reply(text: str) -> Outcome[Completion]:
    return Produced(value=Completion(text=text, model="stub-model"))


def _ctx(llm: object, prompts: object | None = None) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    services.add(Prompts, prompts if prompts is not None else _StubPrompts())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_each_node_gets_its_own_derived_question_nodes() -> None:
    # Arrange — two chunks, each answered with a distinct set of questions.
    first = _node("Minimum redundancy trades off against maximum relevance.")
    second = _node("Feature selection reduces the dimensionality of the input space.")
    llm = _ScriptedLLM(
        [
            _reply("What does mRMR trade off?\nWhy does relevance alone not suffice?"),
            _reply("What does feature selection reduce?"),
        ]
    )
    generator = HypotheticalQuestionGenerator(HypotheticalQuestionsConfig(questions_per_node=2))

    # Act
    outcome = await generator.run((first, second), _ctx(llm))

    # Assert — both originals survive unchanged, and each grows its own derived children.
    assert isinstance(outcome, Produced)
    nodes = outcome.value
    assert nodes[0] is first
    assert nodes[1] is second
    derived = nodes[2:]
    assert len(derived) == 3  # two for `first`, one for `second`
    for child in derived:
        assert child.embedding is None  # `Expander` derives text; embedding is a later stage
        assert child.media_type is MediaType.TEXT
        marker = child.ext_as(Representation)
        assert marker is not None
        assert marker.technique == NAME
    first_children = [child for child in derived if child.lineage.parents == (first.id,)]
    second_children = [child for child in derived if child.lineage.parents == (second.id,)]
    assert len(first_children) == 2
    assert len(second_children) == 1
    assert all(child.lineage.sources == frozenset({_SOURCE}) for child in derived)
    assert {child.content for child in first_children} == {
        "What does mRMR trade off?",
        "Why does relevance alone not suffice?",
    }


async def test_a_node_whose_generation_degrades_still_survives_unchanged() -> None:
    # Arrange — the first node's completion fails outright; the second's succeeds.
    first, second = _node("passage one"), _node("passage two")
    llm = _ScriptedLLM([Failed(reason="the model declined"), _reply("What is passage two about?")])
    generator = HypotheticalQuestionGenerator()

    # Act
    outcome = await generator.run((first, second), _ctx(llm))

    # Assert — both originals are still in the output; only `first` grew no children.
    assert isinstance(outcome, Produced)
    nodes = outcome.value
    assert first in nodes
    assert second in nodes
    derived = [node for node in nodes if node.id not in (first.id, second.id)]
    assert len(derived) == 1
    assert derived[0].lineage.parents == (second.id,)


async def test_an_empty_batch_is_nothing_to_produce() -> None:
    # Arrange
    generator = HypotheticalQuestionGenerator()

    # Act
    outcome = await generator.run((), _ctx(_ScriptedLLM([])))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_an_unmapped_prompt_name_propagates_rather_than_degrading() -> None:
    # Arrange — a `with:` block naming a prompt nobody registered is an operator mistake,
    # not a model failure, so it must not be swallowed into "no questions for this node".
    generator = HypotheticalQuestionGenerator(HypotheticalQuestionsConfig(prompt="nonexistent"))
    node = _node("passage")

    # Act / Assert
    with pytest.raises(KeyError):
        await generator.run((node,), _ctx(_ScriptedLLM([])))


async def test_hypothetical_questions_runs_through_the_seam() -> None:
    """FF7(b) shape: driven through `weft_kernel.seam.wrap`, not around it — the failure
    mode `tests/unit/weft_retrieve/test_vector_top_k.py:198`'s own module docstring names:
    a plugin whose entire suite calls its methods directly never notices a
    `BlockingCallError` it would raise the first time a real run reaches it.
    """
    # Arrange
    generator = HypotheticalQuestionGenerator()
    assert isinstance(generator, Expander)
    sealed = wrap(
        generator.run, distribution="weft-index", contract="Expander", plugin=NAME, stage="expand"
    )
    node = _node("passage")
    llm = _ScriptedLLM([_reply("What is this passage about?")])

    # Act
    outcome = await sealed((node,), _ctx(llm))

    # Assert — the seam adds spans and a guard, never behaviour: one node in, one node's
    # own question derived beside it.
    assert isinstance(outcome, Produced)
    assert len(outcome.value) == 2
