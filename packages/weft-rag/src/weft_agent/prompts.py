"""`next-action` — the one question `weft-agent` asks a model: call a tool, or answer.

Task **7.1**. Registered under `weft_prompts.contract.Prompt` through the same public entry
point a third-party prompt pack uses (`weft_agent.register`, task 7.1's own claim). The prompt
text below is authored fresh for Weft, against `NextActionRequest`'s own three fields: it asks
for exactly one decision, given a goal, the tools currently on offer and what has happened in
the run so far — never a rewrite of the shape `weft_agent.payload.NextAction` already states.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel

from weft_agent.payload import NextAction, NextActionRequest
from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under, and `weft_agent.register`'s own
#: `registrar.add(Prompt, NEXT_ACTION_NAME, NextActionPrompt)` call.
NEXT_ACTION_NAME = "next-action"


class NextActionPrompt(TypedPrompt):
    """Ask a model to decide the next step toward a goal: one tool call, or a final answer.

    The instruction is explicit that the model must choose exactly one — never propose a tool
    call and also answer, and never do neither — the same discipline
    `weft_agent.payload.NextAction`'s own validator enforces on the parsed reply, stated here
    in the words the model is actually asked.
    """

    name: ClassVar[str] = NEXT_ACTION_NAME
    input_model: ClassVar[type[BaseModel]] = NextActionRequest
    output_model: ClassVar[type[BaseModel] | None] = NextAction
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You are working toward a goal, one step at a time. At each step you either "
                "call exactly one of the tools you have been offered, or, once you already "
                "have enough to answer, give a final answer instead. You never do both, and "
                "you never do neither."
            ),
            user=(
                "Goal: ${goal}\n\n"
                "Tools available:\n${tools}\n\n"
                "What has happened so far:\n${transcript}\n\n"
                "Decide the next step: call exactly one of the tools above with its "
                "arguments, or, if what has happened so far is already enough, give your "
                "final answer instead. State your reasoning, then either the one tool call "
                "or the final answer — never both."
            ),
        ),
    }
