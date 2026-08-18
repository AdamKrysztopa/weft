"""`ExampleGreetingPrompt` — a stranger's `Prompt`: one templated greeting, two locales.

Built on `weft_prompts.typed_prompt.TypedPrompt`, the public base `weft-prompts` ships for
exactly this: a third-party prompt declares four class attributes and gets the two-direction
template/input-model check `__init_subclass__` runs at class-definition time for free —
`TypedPrompt` satisfies `weft_prompts.contract.Prompt` structurally, and so does this
subclass, transitively, with no import of that Protocol anywhere in this file.
"""

from pydantic import BaseModel, ConfigDict, Field

from weft_prompts import PromptText, TypedPrompt

NAME = "example-greeting"


class GreetingInputs(BaseModel):
    """What this prompt renders — one field, the name to greet."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)


class ExampleGreetingPrompt(TypedPrompt):
    """Greets `name` in whichever of its two locales `ctx.locale` selects, falling back to `en`."""

    name = NAME
    input_model = GreetingInputs
    output_model = None
    texts = {
        "en": PromptText(user="Say hello to ${name}."),
        "pl": PromptText(user="Przywitaj się z ${name}."),
    }
