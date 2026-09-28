"""A prompt's digest identifies its wording — task 44.4.

A run record names each judge's prompt by digest, so two records scored by differently worded judges
cannot be read as one measurement. The digest covers the prompt's name, its version and every
locale's text, and nothing a run chooses.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from weft_prompts.typed_prompt import PromptText, TypedPrompt, prompt_digest


class _Ask(BaseModel):
    question: str


class _Original(TypedPrompt):
    name: ClassVar[str] = "digest-fixture"
    input_model: ClassVar[type[BaseModel]] = _Ask
    texts = {"en": PromptText(system="Judge carefully.", user="Is ${question} answered?")}


class _Reworded(TypedPrompt):
    name: ClassVar[str] = "digest-fixture"
    input_model: ClassVar[type[BaseModel]] = _Ask
    texts = {"en": PromptText(system="Judge strictly.", user="Is ${question} answered?")}


class _Relocalised(TypedPrompt):
    name: ClassVar[str] = "digest-fixture"
    input_model: ClassVar[type[BaseModel]] = _Ask
    texts = {
        "en": PromptText(system="Judge carefully.", user="Is ${question} answered?"),
        "pl": PromptText(system="Oceniaj uważnie.", user="Czy ${question} ma odpowiedź?"),
    }


class _Reversioned(TypedPrompt):
    name: ClassVar[str] = "digest-fixture"
    prompt_version: ClassVar[str] = "2.0.0"
    input_model: ClassVar[type[BaseModel]] = _Ask
    texts = {"en": PromptText(system="Judge carefully.", user="Is ${question} answered?")}


def test_the_same_prompt_has_one_digest() -> None:
    # Act
    first = prompt_digest(_Original)
    second = prompt_digest(_Original)

    # Assert
    assert first == second
    assert len(first) == 64
    assert int(first, 16) >= 0


def test_a_reworded_template_changes_the_digest() -> None:
    # Assert
    assert prompt_digest(_Reworded) != prompt_digest(_Original)


def test_a_new_locale_changes_the_digest() -> None:
    # Assert
    assert prompt_digest(_Relocalised) != prompt_digest(_Original)


def test_a_new_version_changes_the_digest() -> None:
    # Assert
    assert prompt_digest(_Reversioned) != prompt_digest(_Original)
