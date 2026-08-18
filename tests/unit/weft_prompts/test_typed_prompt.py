"""Unit tests for `weft_prompts.typed_prompt`.

Mirrors `packages/weft-prompts/src/weft_prompts/typed_prompt.py`. Covers the happy path (a
declared prompt renders into a `Rendered` carrying its own name and version), the locale
mechanism (a translation is selected by `ctx.locale`, falling back by primary subtag and then
to `en`), and the two definition-time refusals a mis-declared prompt earns.
"""

from collections.abc import Mapping
from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Produced
from weft_llm.payload import MessageRole
from weft_prompts.errors import (
    MissingFallbackLocaleError,
    PromptInputMismatchError,
    TemplateVariableError,
)
from weft_prompts.typed_prompt import PromptText, TypedPrompt


class _Ask(BaseModel):
    question: str


class _Verdict(BaseModel):
    verdict: str


class _Judge(TypedPrompt):
    name: ClassVar[str] = "judge"
    prompt_version: ClassVar[str] = "1.2.0"
    input_model: ClassVar[type[BaseModel]] = _Ask
    output_model: ClassVar[type[BaseModel] | None] = _Verdict
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(system="You judge answers.", user="Judge: ${question}"),
        "pl": PromptText(system="Oceniasz odpowiedzi.", user="Oceń: ${question}"),
    }


def _ctx(locale: str) -> Context:
    return Context(
        tenant_id="t", run_id="r", trace_id="x", locale=locale, services=ServiceRegistry()
    )


async def test_a_declared_prompt_renders_and_records_which_prompt_produced_it() -> None:
    # Arrange
    prompt = _Judge()

    # Act
    outcome = await prompt.render(_Ask(question="is it so?"), _ctx("en"))

    # Assert
    assert isinstance(outcome, Produced)
    rendered = outcome.value
    assert (rendered.prompt, rendered.prompt_version) == ("judge", "1.2.0")
    assert [message.role for message in rendered.conversation.messages] == [
        MessageRole.SYSTEM,
        MessageRole.USER,
    ]
    assert rendered.conversation.messages[1].content == "Judge: is it so?"


async def test_a_locale_with_a_region_falls_back_to_its_primary_subtag() -> None:
    # Arrange
    prompt = _Judge()

    # Act
    outcome = await prompt.render(_Ask(question="czy tak?"), _ctx("pl-PL"))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.conversation.messages[1].content == "Oceń: czy tak?"


async def test_an_untranslated_locale_falls_back_to_english_rather_than_failing() -> None:
    # Arrange
    prompt = _Judge()

    # Act
    outcome = await prompt.render(_Ask(question="wie?"), _ctx("de"))

    # Assert — a missing translation degrades the *language*, which a reader can see, never
    # the answer, which they cannot.
    assert isinstance(outcome, Produced)
    assert outcome.value.conversation.messages[1].content == "Judge: wie?"


async def test_values_of_the_wrong_type_are_refused_naming_both_models() -> None:
    # Arrange
    prompt = _Judge()

    # Act / Assert
    with pytest.raises(PromptInputMismatchError) as raised:
        await prompt.render(_Verdict(verdict="yes"), _ctx("en"))
    message = str(raised.value)
    assert "_Ask" in message
    assert "_Verdict" in message


def test_a_translation_using_a_placeholder_the_input_model_lacks_fails_at_definition() -> None:
    # Act / Assert — at class-definition time, so a mis-declared prompt cannot reach a run.
    with pytest.raises(TemplateVariableError):

        class Broken(TypedPrompt):
            name: ClassVar[str] = "broken"
            input_model: ClassVar[type[BaseModel]] = _Ask
            texts: ClassVar[Mapping[str, PromptText]] = {
                "en": PromptText(user="${question}"),
                "pl": PromptText(user="${pytanie}"),
            }

        # Never reached: the class body above raises. Written so the name is used, which is
        # what tells a checker this class is the subject of the test rather than dead code.
        assert Broken.name == "broken"


def test_a_prompt_set_with_no_english_fallback_is_refused() -> None:
    # Act / Assert
    with pytest.raises(MissingFallbackLocaleError):

        class NoFallback(TypedPrompt):
            name: ClassVar[str] = "no-fallback"
            input_model: ClassVar[type[BaseModel]] = _Ask
            texts: ClassVar[Mapping[str, PromptText]] = {"pl": PromptText(user="${question}")}

        assert NoFallback.name == "no-fallback"  # never reached — see the test above
