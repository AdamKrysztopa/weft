"""`scripted` — the deterministic, offline `LLMProvider` every gate run resolves against.

The counterpart to `weft_embed.hash_embedder.HashEmbedder`: it makes no network call, needs
no credential and no model download, and it is registered under the same contract a real
vendor registers under so `poe ci-checks` — and any operator's `[llm.roles]` role naming
`provider = "scripted"` — never depends on one. `weft-openai`'s `openai` is what an operator
selects when an answer needs to mean something; this is what makes the selection real rather
than assumed, the same argument `weft_openai`'s own module docstring makes for `hash`.

**Deterministic, not random-but-seeded.** Two calls with the same `Conversation` produce the
identical `Completion`, which is what makes a unit test asserting a technique's `cost_bound`
(`.phase2-design.md` §10 — "a unit test counts calls against the deterministic `scripted`
provider and asserts the bound") a test of call *count* rather than a test that also has to
tolerate variation in what was said.
"""

from collections.abc import AsyncIterator
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.payload import Completion, Conversation, MessageRole

#: The name this provider is registered and selectable under — see `weft_llm.register`.
NAME = "scripted"


class ScriptedConfig(BaseModel):
    """`ScriptedProvider`'s configuration. Every field has a default — see the module docstring.

    `reply`, set, replaces the derived echo below with a fixed string — useful for a unit
    test that wants one exact `Completion.text` without reasoning about `_reply`'s own logic.
    Unset (the default) derives an answer from the conversation, which is what a technique
    plugin's own tests exercise: two different questions must not produce the same answer,
    or a bug that always returns the config's own field would pass silently.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reply: str = ""


class ScriptedProvider:
    """Answers deterministically, from the conversation alone, with nothing behind it to call.

    Satisfies `weft_llm.contract.LLMProvider` structurally: this class never imports it, the
    same path every third-party provider pack takes.
    """

    config_model: ClassVar[type[ScriptedConfig]] = ScriptedConfig

    def __init__(self, config: ScriptedConfig | None = None) -> None:
        self._config = config if config is not None else ScriptedConfig()

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        del ctx  # no service or locale this provider needs
        text = _reply(conv, self._config)
        return Produced(value=Completion(text=text, model=model, finish_reason="stop"))

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        """The same reply `complete` would answer, split into word-sized chunks.

        Never a second code path with its own logic — `.phase2-design.md` decision 10 is
        precisely that a provider's `stream` and `complete` must not be able to diverge, and
        the way this one holds that is by deriving both from `_reply`.

        **Repaired in task 2.10: the chunks now rejoin to exactly what `complete` returns.**
        Re-adding the separator after every word appended a trailing space no `Completion`
        ever carried, and `weft_llm.client` — which always streams — turned that into a
        one-character difference between what this provider says and what a caller receives.
        Deriving both from `_reply` is not enough on its own; the split has to be reversible.
        """
        words = _reply(conv, self._config).split(" ")
        last = len(words) - 1
        for index, word in enumerate(words):
            yield word if index == last else f"{word} "

    async def close(self) -> None:
        """Nothing was ever opened. Present because the contract requires it of every provider."""
        return


def _reply(conv: Conversation, config: ScriptedConfig) -> str:
    """`config.reply` if set; otherwise the last user turn, echoed with a marker.

    The marker (`[scripted]`) is what lets a test — or an operator staring at an answer —
    tell at a glance that no model produced it, the same honesty
    `weft_embed.hash_embedder.HashEmbedder` states about its own vectors.
    """
    if config.reply:
        return config.reply
    for message in reversed(conv.messages):
        if message.role is MessageRole.USER:
            return f"[scripted] {message.content}"
    return f"[scripted] {conv.messages[-1].content}"
