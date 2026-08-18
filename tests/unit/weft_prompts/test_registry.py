"""Unit tests for `weft_prompts.registry`.

Mirrors `packages/weft-prompts/src/weft_prompts/registry.py`. Covers the happy path (a
registered prompt renders by name) and the error case (an unregistered name is refused by the
kernel registry's own message, naming every prompt that *is* registered).

**Driven through the seam.** `Prompts.render` runs a plugin outside `Runner`, so the service
wraps it in `weft_kernel.seam.wrap`; the second test asserts on the attribution the seam adds,
which is the only evidence that the wrap is really in the path.
"""

from collections.abc import Mapping
from typing import ClassVar

import pytest
from pydantic import BaseModel

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.errors import WeftError
from weft_kernel.payload import Produced
from weft_kernel.registry import Registry, UnknownPluginError
from weft_prompts.contract import Prompt
from weft_prompts.registry import prompts_service
from weft_prompts.typed_prompt import PromptText, TypedPrompt


class _Ask(BaseModel):
    question: str


class _Judge(TypedPrompt):
    name: ClassVar[str] = "judge"
    input_model: ClassVar[type[BaseModel]] = _Ask
    texts: ClassVar[Mapping[str, PromptText]] = {"en": PromptText(user="Judge: ${question}")}


def _ctx() -> Context:
    return Context(tenant_id="t", run_id="r", trace_id="x", locale="en", services=ServiceRegistry())


def _registry() -> Registry:
    registry = Registry()
    registry.add(Prompt, "judge", _Judge, distribution="weft-example-prompts")
    return registry


async def test_a_registered_prompt_renders_by_name() -> None:
    # Arrange
    prompts = prompts_service(_registry())

    # Act
    outcome = await prompts.render("judge", _Ask(question="why?"), _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.conversation.messages[-1].content == "Judge: why?"


async def test_an_unregistered_prompt_name_is_refused_listing_the_registered_ones() -> None:
    # Arrange
    prompts = prompts_service(_registry())

    # Act / Assert
    with pytest.raises(UnknownPluginError) as raised:
        await prompts.render("summarise", _Ask(question="why?"), _ctx())
    assert "judge" in str(raised.value)


async def test_a_failure_inside_a_prompt_is_attributed_by_the_seam() -> None:
    # Arrange
    class _Exploding:
        input_model: ClassVar[type[BaseModel]] = _Ask
        output_model: ClassVar[type[BaseModel] | None] = None

        def __init__(self, config: object = None) -> None:
            del config

        async def render(self, values: BaseModel, ctx: Context) -> Produced[object]:
            del values, ctx
            raise WeftError("the template source was unreadable")

    registry = Registry()
    registry.add(Prompt, "boom", _Exploding, distribution="weft-example-prompts")
    prompts = prompts_service(registry)

    # Act / Assert — pack, contract and plugin are filled in by the seam, not by this pack.
    with pytest.raises(WeftError) as raised:
        await prompts.render("boom", _Ask(question="why?"), _ctx())
    assert raised.value.pack == "weft-example-prompts"
    assert raised.value.contract == "Prompt"
    assert raised.value.plugin == "boom"
