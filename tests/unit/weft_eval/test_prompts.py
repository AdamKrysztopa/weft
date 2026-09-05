"""Unit tests for `weft_eval.prompts`.

Mirrors `packages/weft-rag/src/weft_eval/prompts.py`. Every prompt's template/input-model
agreement is already checked at class-definition time by `TypedPrompt.__init_subclass__` — this
file's job is proving `render` actually substitutes correctly for one prompt (the happy path), an
answer-model round-trip for the output shapes the judges rely on (the "no score field" property
these output models exist to guarantee), and that a `Prompt` this pack registers refuses a value
of the wrong input model rather than silently rendering nonsense.
"""

import pytest

from weft_eval.prompts import (
    AnswerCompletenessRequest,
    CompletenessJudgement,
    FaithfulnessJudgement,
    FaithfulnessJudgePrompt,
    FaithfulnessRequest,
    StatementSupport,
)
from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_prompts.errors import PromptInputMismatchError


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_faithfulness_prompt_renders_the_answer_and_context_into_the_conversation() -> None:
    # Arrange
    prompt = FaithfulnessJudgePrompt()
    values = FaithfulnessRequest(answer="the sky is blue", contexts="[0] the sky is blue")

    # Act
    outcome = await prompt.render(values, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    text = " ".join(message.content for message in outcome.value.conversation.messages)
    assert "the sky is blue" in text
    assert "[0] the sky is blue" in text


async def test_faithfulness_prompt_refuses_a_mismatched_input_model() -> None:
    # Arrange
    prompt = FaithfulnessJudgePrompt()
    wrong_values = AnswerCompletenessRequest(prediction="x", reference="y")

    # Act / Assert
    with pytest.raises(PromptInputMismatchError):
        await prompt.render(wrong_values, _ctx())


def test_faithfulness_judgement_carries_no_score_field() -> None:
    # Arrange / Act
    judgement = FaithfulnessJudgement(statements=(StatementSupport(statement="x", supported=True),))

    # Assert — the fix for the reference's defect is structural: there is nowhere on this model for
    # a model to have put a ratio.
    assert "score" not in type(judgement).model_fields
    assert "value" not in type(judgement).model_fields


def test_completeness_judgement_round_trips_through_json() -> None:
    # Arrange
    judgement = CompletenessJudgement(covered=("a",), missing=("b", "c"))

    # Act
    restored = CompletenessJudgement.model_validate_json(judgement.model_dump_json())

    # Assert
    assert restored == judgement
