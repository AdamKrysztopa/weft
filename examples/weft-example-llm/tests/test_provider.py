"""This pack's own tests for `ExampleEchoProvider`."""

from weft_example_llm.provider import ExampleEchoProvider

from weft_kernel.context import Context
from weft_kernel.payload import Produced
from weft_kernel.seam import wrap
from weft_llm.contract import LLMProvider, NativeStructured
from weft_llm.payload import Completion, Conversation, Message, MessageRole


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _conversation(text: str) -> Conversation:
    return Conversation(messages=(Message(role=MessageRole.USER, content=text),))


async def test_complete_answers_deterministically_through_the_seam() -> None:
    # Arrange
    provider = ExampleEchoProvider()
    wrapped = wrap(
        provider.complete,
        distribution="weft-example-llm",
        contract="LLMProvider",
        plugin="example-echo",
    )
    conv = _conversation("abc")

    # Act
    outcome = await wrapped(conv, model="any-model", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(outcome.value, Completion)
    assert outcome.value.text == "[example-llm] cba"
    assert outcome.value.model == "any-model"


async def test_stream_reassembles_to_exactly_what_complete_returns() -> None:
    # Arrange
    provider = ExampleEchoProvider()
    conv = _conversation("hello there friend")

    # Act
    completion = await provider.complete(conv, model="m", ctx=_ctx())
    streamed = "".join([chunk async for chunk in provider.stream(conv, model="m", ctx=_ctx())])

    # Assert
    assert isinstance(completion, Produced)
    assert streamed == completion.value.text


async def test_complete_structured_answers_valid_json_for_the_schema() -> None:
    # Arrange
    provider = ExampleEchoProvider()
    conv = _conversation("irrelevant")
    schema = {"properties": {"count": {"type": "integer"}, "label": {"type": "string"}}}

    # Act
    outcome = await provider.complete_structured(conv, schema, model="m", ctx=_ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.text == '{"count": 0, "label": ""}'


async def test_provider_satisfies_llmprovider_and_nativestructured_structurally() -> None:
    # Act / Assert — no import of either Protocol in provider.py itself.
    provider = ExampleEchoProvider()
    assert isinstance(provider, LLMProvider)
    assert isinstance(provider, NativeStructured)
