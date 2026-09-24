"""A second account for the OpenAI protocol — the same adapters, a separate `[packs.*]` block.

Phase 20a task **20.1**. `weft_openai.register()` binds one `Settings` into all three of its
plugins through `functools.partial`, and a pack receives exactly one settings block — so
`openai-embeddings` and `openai` necessarily shared one `base_url` and one `api_key`. *Local
embeddings with hosted chat* was therefore not a configuration an operator could get wrong: it was
a sentence `weft.toml` had no way to write, with no error to read because nothing was in error.
This pack is the second block.

**It is named for the protocol, not for the deployment.** `openai-compatible` is true whether the
server answering is on localhost, behind a corporate gateway, or another vendor speaking the same
API. `local` was the alternative and was rejected on `docs/10-technique-catalogue.md` §2.1 rule 6:
it claims a deployment property nothing here enforces, and this pack points at a hosted URL just as
happily as at `127.0.0.1`. `12-roadmap.md` §5a carries the argument and the owner's settlement.

**It re-exports `weft_openai`'s classes rather than subclassing them, and — since repair
**R33.1** — subclasses its `Settings` for the one field this account needs on top.** Nothing
about a second account differs in *shape* otherwise — the same credential, the same endpoint,
the same patience knobs — but whether a local server accepts `stream_options.include_usage` is
not a fact `weft_openai`'s vendor account can answer for it, so `Settings` here adds
`stream_usage`, defaulting off. `weft_kernel.discovery` validates `[packs.openai-compatible]`
against this subclass and hands the result here, and `register()` binds that instance rather than
the one `[packs.openai]` produced.

**Three names, three contracts, and that is fitness function 18 rather than taste.** Registering
these same classes a second time is precisely the shape that produced the defect FF18 exists for:
until ledger task 8.15 one `NAME` constant was passed to two `registrar.add` calls, and the result
was an embedder that was registered, listed, catalogued, selectable through `[services] embed` and
**placeable by no pipeline document in existence**, because `weft_cli.compile._contract_for`
refuses a name answering to two contracts. Sharing an account is not sharing a name, and neither is
sharing an implementation.

**The alternative that was not built**, recorded here because a shape decided by direction is still
a shape someone will want the argument for: a mapping of accounts inside one settings block,
`[packs.openai.accounts.<name>]`, with plugins registered per account. It is more general and costs
more — it changes what a pack's `settings` *is*, from one model to a model over a keyed collection,
in a surface every pack shares and `02` §2 owns. With exactly one pack wanting two accounts, that
mechanism would be built for a population of one, which is the shape `L5.19` refuses. A second pack
wanting it is the trigger to reopen this as a gate.
"""

from collections.abc import AsyncIterator, Mapping
from functools import partial
from typing import ClassVar, cast

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_kernel.payload import Outcome
from weft_llm.contract import LLMProvider, NativeStructured, UsageReporting
from weft_llm.payload import Completion, Conversation, TokenUsage
from weft_openai.embedder import OpenAIEmbedder
from weft_openai.llm import (
    ChatClient,
    NativeStructuredOpenAILLMProvider,
    OpenAILLMConfig,
    OpenAILLMProvider,
)
from weft_openai.settings import Settings as VendorSettings
from weft_openai.vision import OpenAIVisionDescriber
from weft_vision import Describer

#: Each is the `openai` pack's own name with this account's prefix, so a reader of
#: `weft plugins list` can see at a glance which block configures which row. Three constants
#: rather than one, for the reason `weft_openai.__init__`'s docstring gives at length: one
#: constant serving two `registrar.add` calls is ledger task 8.15's defect exactly.
#: This pack's `weft.packs` entry-point name, and therefore the `[packs.<name>]` block whose
#: absence the three plugins must name when they refuse. Passed explicitly into each — the
#: defect `20.2`'s Exit caught was exactly a refusal naming `[packs.openai]` while the block an
#: operator had to edit was this one.
ACCOUNT = "openai-compatible"

EMBEDDER_NAME = "openai-compatible-embeddings"
PROVIDER_NAME = "openai-compatible"
VISION_NAME = "openai-compatible-vision"

#: **The disclosure names this pack's own block, and that is the one thing it may not copy.**
#: `weft_openai`'s says `[packs.openai] base_url`; repeating that sentence in a pack configured by
#: a different block sends an operator to the wrong place in their own file, which is worse than
#: saying nothing — `02` §2's argument for prose naming a setting rather than a boolean assumes
#: the setting named is the one that decides.
#:
#: No default host is named, and that is the substantive difference from `weft_openai`'s
#: disclosure: an account whose whole purpose is to be pointed somewhere else has no host an
#: operator can be told in advance.
DISCLOSURE = Disclosure(
    network=("whatever [packs.openai-compatible] base_url names",),
    filesystem=(),
    subprocess=(),
    note=(
        "A second account for the same OpenAI-compatible API `weft_openai` speaks, configured "
        "independently: prompts, text to be embedded and the image bytes of any figure a "
        "pipeline asks to have described leave this process for whatever [packs.openai-compatible] "
        "base_url names, using the credential in that same block. It exists so an operator can "
        "send embeddings to one server and completions to another — which means the two accounts "
        "must be read as two disclosures, not one: what leaves through this pack and what leaves "
        "through `openai` may go to different places and be governed by different agreements. "
        "Registers an Embedder, an LLMProvider and a Describer, the same three `openai` does; "
        "nothing else in Weft calls out unless a pipeline names one of them."
    ),
)


class Settings(VendorSettings):
    """`weft_openai.settings.Settings`, plus the one knob this account needs on top.

    **Repair R33.1.** Task 33.6 made `OpenAILLMProvider` satisfy `weft_llm.contract.UsageReporting`,
    so it sends `stream_options={"include_usage": true}` on every generation — documented for
    OpenAI's own API, never measured against an arbitrary OpenAI-compatible server. Whether the
    server this account points at accepts that field is exactly the fact `base_url` already says
    this pack cannot know in advance, so the account gets to say it itself.
    """

    #: Default `False`: a server that rejects an unknown `stream_options` field answers exactly
    #: as it did before task 33.6. Set `true` once the server this account points at is known to
    #: honour it.
    stream_usage: bool = False


class StreamOnlyOpenAILLMProvider:
    """`OpenAILLMProvider`, without the methods that satisfy `UsageReporting` and `TokenCounting`.

    `OpenAILLMProvider`, with the methods that satisfy `UsageReporting` and `TokenCounting`
    withheld.

    Registered for `openai-compatible` instead of `OpenAILLMProvider` itself whenever
    `Settings.stream_usage` is false — see `register`. Delegation, not subclassing: a subclass
    would inherit `stream_reporting_usage` and `count_tokens` and still satisfy
    `weft_llm.contract.UsageReporting` and `weft_llm.contract.TokenCounting` by `isinstance`,
    which is exactly the claim this class exists to withhold. `LLMClient` then streams this
    provider through plain `stream`, and the call is recorded as not reporting usage rather
    than as reporting zero.

    **Withholding `count_tokens` is not the same repair as withholding usage reporting, and
    task 32.6 is what forces it into this class rather than a third one:** a local server's
    model names are not the vendor's, so `tiktoken`'s encoding for an aliased name would count
    the wrong model's tokens, silently — the failure `TokenCounting`'s own `None` return exists
    to name rather than guess past.
    """

    config_model: ClassVar[type[OpenAILLMConfig]] = OpenAILLMConfig
    #: The class the delegated calls actually run against. Overridden by the two `Structured*`
    #: subclasses below to `NativeStructuredOpenAILLMProvider`, so `self._inner` carries
    #: `complete_structured` only when the account this wrapper serves opted in — repair
    #: **R41.5**. Declared here rather than duplicating `__init__` per combination.
    _inner_cls: ClassVar[type[OpenAILLMProvider]] = OpenAILLMProvider

    def __init__(
        self,
        settings: VendorSettings,
        config: OpenAILLMConfig | None = None,
        *,
        client: ChatClient | None = None,
        account: str = ACCOUNT,
    ) -> None:
        self._inner = self._inner_cls(settings, config, client=client, account=account)

    async def complete(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        """Ask the wrapped provider for one completion.

        Args:
            conv: The conversation to complete.
            model: The model name the server is asked for.
            ctx: The run's context.

        Returns:
            The wrapped provider's `Outcome`, unchanged.
        """
        return await self._inner.complete(conv, model=model, ctx=ctx)

    async def stream(self, conv: Conversation, *, model: str, ctx: Context) -> AsyncIterator[str]:
        """Stream the wrapped provider's completion text.

        Args:
            conv: The conversation to complete.
            model: The model name the server is asked for.
            ctx: The run's context.

        Yields:
            Each text piece as the wrapped provider streams it.
        """
        async for piece in self._inner.stream(conv, model=model, ctx=ctx):
            yield piece

    async def close(self) -> None:
        """Close the wrapped provider."""
        await self._inner.close()


class UsageReportingOnlyOpenAILLMProvider(StreamOnlyOpenAILLMProvider):
    """`StreamOnlyOpenAILLMProvider`, with `stream_reporting_usage` added back.

    Registered for `openai-compatible` instead of `OpenAILLMProvider` itself whenever
    `Settings.stream_usage` is true — see `register`. Before task 32.6 that setting registered
    `OpenAILLMProvider` directly, because the class had nothing else `isinstance` could find
    that this account should not claim; `count_tokens` is now exactly such a thing, so the
    direct registration would have made an `openai-compatible` account satisfy `TokenCounting`
    by accident of sharing a class with the vendor account. Delegation, the same shape
    `StreamOnlyOpenAILLMProvider` already takes: `weft_llm.contract.UsageReporting` is derived
    from the presence of `stream_reporting_usage` alone, and this class forwards exactly that
    one method and nothing named `count_tokens`.
    """

    async def stream_reporting_usage(
        self, conv: Conversation, *, model: str, ctx: Context
    ) -> AsyncIterator[str | TokenUsage]:
        """Stream the wrapped provider's completion text and its token usage.

        Args:
            conv: The conversation to complete.
            model: The model name the server is asked for.
            ctx: The run's context.

        Yields:
            Each text piece, and the `TokenUsage` the server reports.
        """
        async for item in cast("UsageReporting", self._inner).stream_reporting_usage(
            conv, model=model, ctx=ctx
        ):
            yield item


class StructuredStreamOnlyOpenAILLMProvider(StreamOnlyOpenAILLMProvider):
    """`StreamOnlyOpenAILLMProvider`, with `complete_structured` added back — repair **R41.5**.

    Registered for `openai-compatible` when `Settings.structured_output` is true and
    `Settings.stream_usage` is false — see `register`. `_inner_cls` is the only override:
    `self._inner` is a `NativeStructuredOpenAILLMProvider`, so the delegated method exists to
    forward, the same shape `stream_reporting_usage` above already takes for usage reporting.
    """

    _inner_cls: ClassVar[type[OpenAILLMProvider]] = NativeStructuredOpenAILLMProvider

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        """Ask the wrapped provider for a completion constrained to `schema`.

        Args:
            conv: The conversation to complete.
            schema: The JSON schema the answer must satisfy.
            model: The model name the server is asked for.
            ctx: The run's context.

        Returns:
            The wrapped provider's `Outcome`, unchanged.
        """
        return await cast("NativeStructured", self._inner).complete_structured(
            conv, schema, model=model, ctx=ctx
        )


class StructuredUsageReportingOnlyOpenAILLMProvider(UsageReportingOnlyOpenAILLMProvider):
    """`UsageReportingOnlyOpenAILLMProvider`, with `complete_structured` added back.

    Registered for `openai-compatible` when both `Settings.structured_output` and
    `Settings.stream_usage` are true — see `register`. Inherits `stream_reporting_usage` from
    `UsageReportingOnlyOpenAILLMProvider` and `complete_structured` below forwards the same way
    `StructuredStreamOnlyOpenAILLMProvider` does; still not `TokenCounting`, for the reason
    `UsageReportingOnlyOpenAILLMProvider`'s own docstring gives.
    """

    _inner_cls: ClassVar[type[OpenAILLMProvider]] = NativeStructuredOpenAILLMProvider

    async def complete_structured(
        self, conv: Conversation, schema: Mapping[str, object], *, model: str, ctx: Context
    ) -> Outcome[Completion]:
        """Ask the wrapped provider for a completion constrained to `schema`.

        Args:
            conv: The conversation to complete.
            schema: The JSON schema the answer must satisfy.
            model: The model name the server is asked for.
            ctx: The run's context.

        Returns:
            The wrapped provider's `Outcome`, unchanged.
        """
        return await cast("NativeStructured", self._inner).complete_structured(
            conv, schema, model=model, ctx=ctx
        )


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register the three `weft_openai` adapters against this account's own settings.

    `settings` is `[packs.openai-compatible]`, validated by `weft_kernel.discovery` against the
    model this pack subclasses from `weft_openai` — a different instance of a related class,
    which is the whole mechanism: one class describes what an account *is*, and each pack's block
    says what one account *holds*.

    **The `LLMProvider` class is chosen from `settings.stream_usage` and
    `settings.structured_output` at registration time** (repair R33.1, widened by task
    **32.6** and again by **R41.5**): the `Structured*` variant when the account has opted in
    to `response_format`, plain otherwise; `UsageReportingOnlyOpenAILLMProvider` or its
    `Structured` sibling when the account has opted in to the vendor's
    `stream_options.include_usage` field, `StreamOnlyOpenAILLMProvider` or its `Structured`
    sibling otherwise — none of the four satisfies `weft_llm.contract.TokenCounting`. Never
    `OpenAILLMProvider` or `NativeStructuredOpenAILLMProvider` directly: both also satisfy
    `TokenCounting`, and this account's model names are not the vendor's to count.

    `partial`, never a closure, for the reason `weft_openai.register` states and ledger task 9.4
    paid for: `weft_kernel.registry.unwrap_factory` peels a `partial` and nothing else, so a
    closure makes the class invisible to every reader that inspects a factory rather than an
    instance — which once cost a pack a silent absence from `weft delete`'s fan-out (`L9.55`).
    """
    registrar.add(Embedder, EMBEDDER_NAME, partial(OpenAIEmbedder, settings, account=ACCOUNT))
    provider_class: type[StreamOnlyOpenAILLMProvider]
    if settings.structured_output:
        provider_class = (
            StructuredUsageReportingOnlyOpenAILLMProvider
            if settings.stream_usage
            else StructuredStreamOnlyOpenAILLMProvider
        )
    else:
        provider_class = (
            UsageReportingOnlyOpenAILLMProvider
            if settings.stream_usage
            else StreamOnlyOpenAILLMProvider
        )
    registrar.add(LLMProvider, PROVIDER_NAME, partial(provider_class, settings, account=ACCOUNT))
    registrar.add(Describer, VISION_NAME, partial(OpenAIVisionDescriber, settings, account=ACCOUNT))


__all__ = [
    "ACCOUNT",
    "DISCLOSURE",
    "EMBEDDER_NAME",
    "PROVIDER_NAME",
    "VISION_NAME",
    "Settings",
    "StreamOnlyOpenAILLMProvider",
    "StructuredStreamOnlyOpenAILLMProvider",
    "StructuredUsageReportingOnlyOpenAILLMProvider",
    "UsageReportingOnlyOpenAILLMProvider",
    "register",
]
