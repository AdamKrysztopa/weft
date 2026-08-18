"""A stranger's model-layer pack — the independence proof for `weft-llm` and `weft-prompts`.

`docs/07-extension-cost.md` §2 clause (c), the task 2.11 backfill: `LLMProvider` (with
`NativeStructured` derived alongside it, structurally) and `Prompt`, both installed the same
way any third-party vendor-provider or prompt pack would be — `examples/weft-example-chunker`
is the precedent this pack's file shape copies exactly.

`tests/architecture/test_ff9c_every_contract_has_a_stranger.py` installs this distribution
(built as a real wheel) into a throwaway environment and asks the resulting registry which
contracts it registered under and which capability Protocols its registered classes satisfy.
"""

from pydantic import BaseModel, ConfigDict

from weft_example_llm.prompt import NAME as PROMPT_NAME
from weft_example_llm.prompt import ExampleGreetingPrompt
from weft_example_llm.provider import ExampleEchoProvider
from weft_kernel.discovery import PackRegistrar
from weft_llm.contract import LLMProvider
from weft_prompts.contract import Prompt


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register this pack's two plugins — a provider and the prompt it can answer."""
    del settings
    registrar.add(LLMProvider, "example-echo", ExampleEchoProvider)
    registrar.add(Prompt, PROMPT_NAME, ExampleGreetingPrompt)


__all__ = ["Settings", "register"]
