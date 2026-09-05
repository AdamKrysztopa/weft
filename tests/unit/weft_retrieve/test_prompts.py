"""Unit tests for `weft_retrieve.prompts`.

Mirrors `packages/weft-rag/src/weft_retrieve/prompts.py`. Task **2.7** ships the first
registered `Prompt` in this tree, and it belongs to the pack whose plugin asks the question —
task 2.10's ledger line: "every first-party prompt belongs to the plugin that asks it a
question." Covers the happy path (the English text rendered into the two-message conversation
a provider continues), the edge case (a locale with no text of its own falls back to `en`
rather than failing), and the error case (a caller handing this prompt the wrong model is
refused by name, never rendered around).

The two-direction template check runs at *class definition* time, so it is exercised by
importing this module at all; what is asserted below is that the declared texts and the input
model actually agree, which is the property that check exists to hold.
"""

import pytest

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_llm.payload import MessageRole
from weft_prompts.contract import Prompt
from weft_prompts.errors import PromptInputMismatchError
from weft_prompts.typed_prompt import FALLBACK_LOCALE
from weft_retrieve.prompts import (
    MULTI_QUERY_VARIANTS_NAME,
    PASSAGE_RELEVANCE_NAME,
    STANDALONE_QUESTION_NAME,
    MultiQueryVariantsPrompt,
    MultiQueryVariantsRequest,
    PassageRelevance,
    PassageRelevancePrompt,
    PassageRelevanceRequest,
    SeedVariants,
    StandaloneQuestion,
    StandaloneQuestionPrompt,
    StandaloneQuestionRequest,
)


def _ctx(locale: str = "en") -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale=locale)


async def test_rendering_puts_the_question_and_the_offered_passages_in_the_conversation() -> None:
    # Arrange
    values = PassageRelevanceRequest(
        question="why is mRMR preferred to plain relevance ranking?",
        passages="[0] mRMR penalises redundancy between selected features.\n[1] Unrelated.",
    )

    # Act
    outcome = await PassageRelevancePrompt().render(values, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    rendered = outcome.value
    assert rendered.prompt == PASSAGE_RELEVANCE_NAME
    assert [message.role for message in rendered.conversation.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    user = rendered.conversation.messages[-1].content
    assert values.question in user
    assert "[1] Unrelated." in user


async def test_a_locale_with_no_text_of_its_own_degrades_the_language_not_the_answer() -> None:
    # Arrange — selection is exact locale, then primary subtag, then `en`. A run under a
    # locale nobody translated still asks the question; it asks it in English.
    values = PassageRelevanceRequest(question="czy to działa?", passages="[0] tak")

    # Act
    outcome = await PassageRelevancePrompt().render(values, _ctx(locale="de-AT"))

    # Assert
    assert isinstance(outcome, Produced)
    english = PassageRelevancePrompt.texts[FALLBACK_LOCALE].user
    assert outcome.value.conversation.messages[-1].content.startswith(english.split("$")[0])


async def test_the_wrong_input_model_is_refused_by_name_rather_than_rendered_around() -> None:
    # Arrange — `PassageRelevance` is this prompt's *output* model; handing it in as input is
    # the confusion a `Mapping[str, object]` prompt API would have rendered into a template
    # full of `${question}` a reader only notices in the answer.
    wrong = PassageRelevance(judgements=())

    # Act / Assert
    with pytest.raises(PromptInputMismatchError, match=PASSAGE_RELEVANCE_NAME):
        await PassageRelevancePrompt().render(wrong, _ctx())


def test_this_prompt_satisfies_the_published_contract_structurally() -> None:
    # Act / Assert — capability derived by `isinstance`, never declared, the same way every
    # other plugin in this tree is checked against the contract it registers under.
    assert isinstance(PassageRelevancePrompt(), Prompt)


def test_every_declared_locale_renders_the_same_two_placeholders() -> None:
    # Act / Assert — `TypedPrompt.__init_subclass__` refuses a translation that drops a
    # `${placeholder}`, so this asserts the fact that check protects rather than re-running
    # it: a translator cannot quietly stop showing the model the passages it is judging.
    for locale, text in PassageRelevancePrompt.texts.items():
        joined = f"{text.system}\n{text.user}"
        assert "${question}" in joined, locale
        assert "${passages}" in joined, locale


async def test_standalone_question_renders_the_history_and_the_follow_up() -> None:
    # Arrange — task 2.15's own prompt: a follow-up plus the history it depends on.
    values = StandaloneQuestionRequest(
        question="and what about the second one?", history="user: what is mRMR?"
    )

    # Act
    outcome = await StandaloneQuestionPrompt().render(values, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.prompt == STANDALONE_QUESTION_NAME
    user = outcome.value.conversation.messages[-1].content
    assert values.question in user
    assert values.history in user


def test_standalone_question_satisfies_the_published_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(StandaloneQuestionPrompt(), Prompt)


def test_standalone_question_output_refuses_an_empty_rewrite() -> None:
    # Act / Assert — `Query.text` itself refuses `""`; this stops a blank cascade tier from
    # ever reaching that far.
    with pytest.raises(ValueError, match="text"):
        StandaloneQuestion(text="")


def test_every_declared_locale_of_standalone_question_renders_both_placeholders() -> None:
    # Act / Assert — same property as `passage-relevance`'s own version of this test, over
    # this prompt's two fields.
    for locale, text in StandaloneQuestionPrompt.texts.items():
        joined = f"{text.system}\n{text.user}"
        assert "${question}" in joined, locale
        assert "${history}" in joined, locale


async def test_multi_query_variants_renders_the_numbered_seeds_and_the_expansion_clause() -> None:
    # Arrange — task 2.18a's own prompt: one or more numbered seed questions, how many
    # alternatives to write for each, and the rendering strategy as a full instruction clause
    # (`weft_retrieve.transforms._EXPANSION_INSTRUCTIONS` builds it; this prompt only renders
    # whatever string it is handed).
    values = MultiQueryVariantsRequest(
        questions="[0] what causes catalyst poisoning?",
        variants=4,
        expansion="each covering a different facet of the same underlying question",
    )

    # Act
    outcome = await MultiQueryVariantsPrompt().render(values, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.prompt == MULTI_QUERY_VARIANTS_NAME
    user = outcome.value.conversation.messages[-1].content
    assert values.questions in user
    assert "4" in user
    assert values.expansion in user


def test_multi_query_variants_satisfies_the_published_contract_structurally() -> None:
    # Act / Assert
    assert isinstance(MultiQueryVariantsPrompt(), Prompt)


def test_multi_query_variants_output_refuses_a_blank_alternative() -> None:
    # Act / Assert — the same refusal `HydeDocuments` makes for a blank hypothetical passage,
    # against a blank alternative here instead: caught before it ever reaches `Query.text`.
    with pytest.raises(ValueError, match="blank"):
        SeedVariants(index=0, variants=("a real alternative", "   "))


def test_every_declared_locale_of_multi_query_variants_renders_all_three_placeholders() -> None:
    # Act / Assert — same property as `passage-relevance`'s own version of this test, over
    # this prompt's three fields.
    for locale, text in MultiQueryVariantsPrompt.texts.items():
        joined = f"{text.system}\n{text.user}"
        assert "${questions}" in joined, locale
        assert "${variants}" in joined, locale
        assert "${expansion}" in joined, locale
