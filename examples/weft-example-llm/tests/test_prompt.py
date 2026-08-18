"""This pack's own tests for `ExampleGreetingPrompt`."""

from weft_example_llm.prompt import ExampleGreetingPrompt, GreetingInputs

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_prompts.contract import Prompt


def _ctx(locale: str) -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale=locale)


async def test_render_fills_the_template_in_the_requested_locale_through_the_seam() -> None:
    # Arrange
    prompt = ExampleGreetingPrompt()
    wrapped = wrap(
        prompt.render, distribution="weft-example-llm", contract="Prompt", plugin="example-greeting"
    )

    # Act
    outcome = await wrapped(GreetingInputs(name="Ada"), _ctx("pl"))

    # Assert
    assert isinstance(outcome, Produced)
    message = outcome.value.conversation.messages[-1]
    assert message.content == "Przywitaj się z Ada."


async def test_render_falls_back_to_english_for_an_untranslated_locale() -> None:
    # Arrange
    prompt = ExampleGreetingPrompt()

    # Act
    outcome = await prompt.render(GreetingInputs(name="Ada"), _ctx("de"))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.conversation.messages[-1].content == "Say hello to Ada."


def test_prompt_satisfies_the_prompt_contract_structurally() -> None:
    # Act / Assert — no import of Prompt in prompt.py itself.
    assert isinstance(ExampleGreetingPrompt(), Prompt)
