"""`ExampleEchoProvider` — a stranger's `LLMProvider`, structurally a `NativeStructured` too.

The counterpart to `weft_llm.scripted.ScriptedProvider`: deterministic, no network call, no
credential, marked so nobody mistakes its answer for a real model's. `complete_structured` is
what makes this class satisfy `weft_llm.contract.NativeStructured` as well — a provider
either has the method or it does not, capability derived rather than declared, and this one
does.

**`stream` and `complete` never diverge** — the same discipline `ScriptedProvider`'s own
module docstring states and its own repair enforced: both are derived from `_reply`, and the
chunk boundaries reassemble to exactly the string `complete` would have returned.
"""

import json
from collections.abc import AsyncIterator, Mapping
from typing import Final, cast

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.payload import Completion, Conversation, MessageRole

#: What a placeholder value looks like for each JSON Schema primitive type — good enough to
#: satisfy a shape check, never a claim about what the field should actually hold.
_PLACEHOLDER_BY_TYPE: Final[dict[str, object]] = {
    "string": "",
    "integer": 0,
    "number": 0.0,
    "boolean": False,
    "array": [],
    "object": {},
}


class ExampleProviderConfig(BaseModel):
    """`ExampleEchoProvider`'s `with:` config — one real field, defaulted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    marker: str = "[example-llm]"


class ExampleEchoProvider:
    """Answers with the last user turn, reversed and marked. Satisfies `weft_llm.contract.
    LLMProvider` and `NativeStructured` structurally — this class never imports either.
    """

    def __init__(self, config: ExampleProviderConfig | None = None) -> None:
        self._config = config if config is not None else ExampleProviderConfig()

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del ctx
        return Produced(
            value=Completion(
                text=_reply(conv, self._config.marker), model=model, finish_reason="stop"
            )
        )

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        del ctx, model
        words = _reply(conv, self._config.marker).split(" ")
        last = len(words) - 1
        for index, word in enumerate(words):
            yield word if index == last else f"{word} "

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del ctx
        text = json.dumps(_placeholder(schema, marker=self._config.marker))
        return Produced(value=Completion(text=text, model=model, finish_reason="stop"))

    async def close(self) -> None:
        """Nothing was ever opened. Present because the contract requires it of every provider."""
        return


def _reply(conv: Conversation, marker: str) -> str:
    """The last user turn, reversed — deterministic, and unmistakably not a real answer."""
    for message in reversed(conv.messages):
        if message.role is MessageRole.USER:
            return f"{marker} {message.content[::-1]}"
    return f"{marker} {conv.messages[-1].content[::-1]}"


def _placeholder(schema: Mapping[str, object], *, marker: str) -> dict[str, object]:
    """One value per property `schema` declares — a shape check passes, never a claim of truth."""
    raw_properties = schema.get("properties", {})
    if not isinstance(raw_properties, Mapping):
        return {"note": marker}
    properties = cast("Mapping[str, object]", raw_properties)
    return {str(name): _placeholder_for_one(spec) for name, spec in properties.items()}


def _placeholder_for_one(spec: object) -> object:
    if not isinstance(spec, Mapping):
        return None
    fields = cast("Mapping[str, object]", spec)
    kind = fields.get("type")
    return _PLACEHOLDER_BY_TYPE.get(kind) if isinstance(kind, str) else None
