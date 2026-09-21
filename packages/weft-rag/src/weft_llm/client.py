"""The `LLM` service — one code path from a role to an answer, with everything attached.

Task **2.10**: the service `weft_llm.contract`'s own docstring promised "one task later",
"alongside the retry and cascade machinery". It is the assembly point for four things a
technique author must never write again: resolving a role to a provider and a model, retry,
the registration seam, and streaming.

**Streaming attaches here, and that discharges task 2.17 structurally.**
`.phase2-design.md` decision 10 and §7: "the `LLM` client **always** calls `provider.stream(...)`,
accumulates, and emits each chunk to `ctx.require(TokenSink)` tagged with the call's `role`.
`complete()` still returns a decided `Outcome[Completion]`, decided at return and not when a
stream is drained (G6)." One code path means "a generator that forgets to stream cannot exist,
and a streaming twin has nowhere to live" — a design with a separate registry for streaming
variants depends on an author keeping both symmetric by hand, with nothing to test that they
stay so, and that is exactly the shape in which one technique's streaming variant can
silently drift into a different technique from the one it was meant to mirror.

**The cost of always streaming, named rather than discovered.** `LLMProvider.stream` yields
text and nothing else, so a `Completion` built here carries `finish_reason=""` — the vendor's
own word for why generation stopped does not survive. That is acceptable *because the taxonomy
carries the same facts as classes*: a content-filter refusal is an `LLMContentFilterError` and
a truncation is a provider's own concern, so nothing downstream has to string-match a finish
reason to behave correctly. `LLMProvider.complete` remains the contract member a provider
implements and a library caller may call directly; this client does not use it.

**Every provider call goes through `weft_kernel.seam.wrap`.** The client runs a plugin outside
`Runner`, which is exactly the case `weft_cli.ask` already set the precedent for: the span,
the error attribution, the blocking-call guard and the transient strip are the seam's, and
"if you find yourself writing a span by hand, stop."

**Nothing but an `LLMError` escapes.** Anything else a provider lets out is wrapped in
`LLMProviderFaultError` naming the provider — `.phase2-design.md` §7's first enforcement of
"a taxonomy nobody catches is documentation". `CancelledError` is a `BaseException` and is
untouched by every `except Exception` in this file, by construction.

**Task 3.10 adds a fifth thing assembled here: the loop-breaker.** `weft_llm.loop_guard.
detect_generation_loop` needs the whole answer accumulated so far on every call, and `complete`
already builds exactly that (`parts`, joined) before emitting to the sink — the only place in
this tree holding that shape on every token, which is why the guard attaches inside `complete`'s
own accumulation loop rather than living in a `TokenSink` — lifted per `01` → Phase 3
**Lift**. A detected loop raises `LLMGenerationLoopError` — an
`LLMPermanentError`, so it takes the same `except LLMError: raise` path a provider's own errors
do — rather than quietly returning a truncated `Completion`; `weft_cli.cli.run_command` turns
that raise into `TokenSink.close(reason=...)`, so a reader is told the stream was cut short
rather than left to mistake it for one that finished cleanly.
"""

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from typing import cast

from pydantic import BaseModel, ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry, unwrap_factory
from weft_kernel.seam import current_stage, wrap
from weft_llm.contract import (
    LLM,
    LLMProvider,
    NativeStructured,
    TokenCounting,
    TokenSink,
    UsageReporting,
)
from weft_llm.errors import (
    LLMError,
    LLMGenerationLoopError,
    LLMProviderFaultError,
    NativeStructuredUnsupportedError,
    ProviderSettingsUnsupportedError,
    TokenCountUnavailableError,
)
from weft_llm.loop_guard import LoopGuardConfig, detect_generation_loop
from weft_llm.models import ModelRef, find_runtime_match, model_ref
from weft_llm.payload import Completion, Rendered, TokenChunk, TokenUsage
from weft_llm.retry import RetryPolicy, with_retry
from weft_llm.roles import LLMRoles, RoleMapping
from weft_llm.usage import UsageEntry, record_usage

#: The contract name the seam stamps on every span and every attributed error raised through
#: this client. Written once, here, rather than at each of the three call sites.
_CONTRACT = "LLMProvider"


class NullSink:
    """A `TokenSink` that discards. The default, so no plugin ever needs a `try`.

    `.phase2-design.md` §13 item 7 leaves `PrintingSink` to a Phase 3 sequencing call and
    settles this half: "Phase 2 ships `NullSink` and the client-side emit path." Discarding is
    not a fallback — a run nobody is watching genuinely has nowhere to put tokens, and the
    alternative (no sink at all) would put a `try` in every caller.
    """

    async def emit(self, chunk: TokenChunk) -> None:
        """Discards `chunk`. Deliberately not buffered — nothing would ever read the buffer."""
        del chunk

    async def close(self, *, reason: str | None = None) -> None:
        """Nothing was opened. Present because the contract requires it of every sink."""
        del reason


async def _text_only(
    source: AsyncIterator[str | TokenUsage], captured: list[TokenUsage]
) -> AsyncIterator[str]:
    """`source`, with any `TokenUsage` item diverted into `captured` rather than yielded.

    The seam that lets `complete`'s one accumulation loop — the loop-guard, the sink emit, the
    `parts` join — drive a `UsageReporting` provider's stream the same way it drives a plain
    one's, rather than duplicating that loop per provider kind.
    """
    async for item in source:
        if isinstance(item, TokenUsage):
            captured.append(item)
            continue
        yield item


class _Bound:
    """One role's resolved answer: the provider to call, the model to name, who to blame."""

    def __init__(self, *, provider: LLMProvider, raw: object, ref: ModelRef, distribution: str):
        self.provider = provider
        #: The instance *before* retry wrapped it, kept only so `close` reaches the real one
        #: exactly once when two roles share a provider.
        self.raw = raw
        self.ref = ref
        self.distribution = distribution


class LLMClient:
    """Resolves a role to a provider and a model at call time, and answers through it.

    Satisfies `weft_llm.contract.LLM` structurally — this class never imports it as a base,
    the same path every plugin in this tree takes with its own contract.

    **Providers are built once per provider name *and settings*, not once per role.** Two roles
    naming the same provider with different models still share one instance and one connection
    pool, which is the shape `LLMProvider`'s own docstring argues for: "`model` is a per-call
    argument, not constructor state … the same account, many models". Two roles that write
    *different* settings do not, because they are different providers in everything but name —
    `R41.1`, and `OpenAILLMConfig`'s docstring names the case: "a `generate` role and a `grade`
    role sharing one account at two different temperatures".
    """

    def __init__(
        self,
        *,
        registry: Registry,
        roles: LLMRoles,
        retry: RetryPolicy | None = None,
        loop_guard: LoopGuardConfig | None = None,
    ) -> None:
        self._registry = registry
        self._roles = roles
        self._retry = retry if retry is not None else RetryPolicy()
        self._loop_guard = loop_guard if loop_guard is not None else LoopGuardConfig()
        self._bound: dict[tuple[str, str], _Bound] = {}
        #: Every provider name this deployment mapped — what makes a `provider/model` prefix
        #: recognisable as a prefix rather than half of a model id. See `weft_llm.models`.
        self._provider_names = frozenset(mapping.provider for mapping in roles.roles.values())

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        """Continue `rendered`'s conversation under `role`, streaming every chunk to the sink.

        Task **33.6**: a provider satisfying `UsageReporting` is asked through
        `stream_reporting_usage` instead of `stream`, so its cost in tokens reaches both the
        returned `Completion` and, when a `recording_usage()` scope is open, one `UsageEntry`.
        A provider that does not satisfy it still streams exactly as before, `usage=None`.
        """
        bound = self._bind(role)
        sink = ctx.require(TokenSink)
        reporting = isinstance(bound.provider, UsageReporting)

        async def run() -> Outcome[Completion]:
            parts: list[str] = []
            captured: list[TokenUsage] = []
            source = (
                _text_only(
                    cast("UsageReporting", bound.provider).stream_reporting_usage(
                        rendered.conversation, model=bound.ref.model, ctx=ctx
                    ),
                    captured,
                )
                if reporting
                else bound.provider.stream(rendered.conversation, model=bound.ref.model, ctx=ctx)
            )
            try:
                async for chunk in source:
                    parts.append(chunk)
                    await sink.emit(TokenChunk(role=role, stage=current_stage(), text=chunk))
                    # Task 3.10: `parts` already holds the whole answer accumulated so far —
                    # exactly the cumulative-text contract `weft_llm.loop_guard` requires — so
                    # this is where the guard attaches rather than inside a `TokenSink`, which
                    # only ever sees one chunk at a time. The chunk that revealed the loop has
                    # already been emitted above, so a reader still sees it before the stream
                    # stops; nothing after it is generated or shown.
                    accumulated = "".join(parts)
                    if detect_generation_loop(accumulated, config=self._loop_guard):
                        raise self._loop_detected(bound, role, accumulated)
            except LLMError:
                raise
            except Exception as fault:
                raise self._fault(bound, role, fault) from fault
            usage = captured[0] if captured else None
            record_usage(
                UsageEntry(
                    role=role,
                    position=current_stage(),
                    provider=bound.ref.provider,
                    model=bound.ref.model,
                    usage=usage,
                )
            )
            text = "".join(parts)
            if not text:
                # Never an empty `Produced` — a model that answered with nothing did not
                # answer, the trap every contract in this tree documents against.
                return NothingToProduce(
                    reason=(
                        f"provider '{bound.ref.provider}' returned no text for role '{role}' "
                        f"on model '{bound.ref.model or '(provider default)'}'"
                    )
                )
            return Produced(
                value=Completion(text=text, model=bound.ref.model, finish_reason="", usage=usage)
            )

        return await self._sealed(bound, role, run)()

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        """Tier 1 of the cascade: ask the vendor to answer *in* `schema` and check it itself.

        Not streamed. A partial JSON document displayed as it arrives is noise to a reader and
        unparseable to anything else, and the cascade's caller wants a typed value, not tokens.
        """
        bound = self._bind(role)
        native = bound.provider
        if not isinstance(native, NativeStructured):
            raise NativeStructuredUnsupportedError(
                f"provider '{bound.ref.provider}' (role '{role}') does not offer native "
                f"structured output. Ask `native_structured_available('{role}')` first, or "
                f"call the structured-output cascade, which steps down for you.",
                provider=bound.ref.provider,
                model=bound.ref.model,
            )

        async def run() -> Outcome[Completion]:
            try:
                return await native.complete_structured(
                    rendered.conversation, schema, model=bound.ref.model, ctx=ctx
                )
            except LLMError:
                raise
            except Exception as fault:
                raise self._fault(bound, role, fault) from fault

        return await self._sealed(bound, role, run)()

    async def native_structured_available(self, role: str) -> bool:
        """Whether `role`'s provider satisfies `NativeStructured` — derived, never declared."""
        return isinstance(self._bind(role).provider, NativeStructured)

    async def count_tokens(self, role: str, text: str) -> int:
        """`text`'s token count for `role`'s model — task **32.6**, gate **G25**.

        Resolved through `self._bind(role)`, the same role resolution `native_structured_
        available` uses, and with no model call: counting is local to the provider's own
        encoder, never a request the vendor bills for.

        **Checked against `bound.raw`, not `bound.provider`.** `native_structured_available`
        checks `bound.provider` because `weft_llm.retry.with_retry` selects a wrapper class
        that itself implements `complete_structured`/`stream_reporting_usage` whenever the
        wrapped provider satisfies `NativeStructured`/`UsageReporting` — so the retried object
        mirrors the capability and `isinstance` on either object agrees. `TokenCounting` gets
        no such wrapper: every `with_retry` result exposes exactly `complete`/`stream`/`close`
        (and, conditionally, the two above) and never `count_tokens`, so checking `bound.
        provider` here would answer `False` for every provider, retried or not. `bound.raw` is
        the object built before retry wrapped it, which is what actually satisfies or fails to
        satisfy this Protocol.
        """
        bound = self._bind(role)
        model = bound.ref.model or None
        if not isinstance(bound.raw, TokenCounting):
            raise TokenCountUnavailableError(role=role, provider=bound.ref.provider, model=model)
        count = await bound.raw.count_tokens(text, model=bound.ref.model)
        if count is None:
            raise TokenCountUnavailableError(role=role, provider=bound.ref.provider, model=model)
        return count

    async def close(self) -> None:
        """Close every provider this client built, once each, in the order they were built."""
        for bound in self._bound.values():
            await bound.provider.close()

    # --- resolution ---------------------------------------------------------------------

    def _bind(self, role: str) -> _Bound:
        """`role` → the provider instance and the model string a call under it uses.

        Every refusal on this path is loud and names its options: an unmapped role names every
        mapped role (`UnmappedLLMRoleError`), an unregistered provider names every registered
        one (the registry's own `UnknownPluginError`), and a model a provider's declared
        catalogue does not offer names the catalogue (`UnknownModelError`).
        """
        mapping = self._roles.resolve(role)
        entry = self._registry.entry(LLMProvider, mapping.provider)
        ref = model_ref(
            provider=mapping.provider, requested=mapping.model, providers=self._provider_names
        )
        catalogue = _declared_catalogue(entry.factory)
        if catalogue and ref.model:
            ref = find_runtime_match(ref, catalogue)
        #: Keyed on the provider *and* the settings written for this role, not on the provider
        #: alone — `R41.1`. Two roles naming one account at two temperatures are two providers,
        #: which is the case `OpenAILLMConfig`'s docstring describes; with the old key the second
        #: role silently reused the first's instance and its sampler. Roles that write the same
        #: settings still share one instance, so a connection is not paid for twice.
        key = (mapping.provider, mapping.model_dump_json(exclude={"model"}))
        cached = self._bound.get(key)
        if cached is not None:
            return _Bound(
                provider=cached.provider,
                raw=cached.raw,
                ref=ref,
                distribution=cached.distribution,
            )
        raw = entry.factory(_provider_config(entry.factory, mapping))
        bound = _Bound(
            provider=with_retry(cast("LLMProvider", raw), self._retry),
            raw=raw,
            ref=ref,
            distribution=entry.distribution,
        )
        self._bound[key] = bound
        return bound

    def _sealed(
        self, bound: _Bound, role: str, run: Callable[[], Awaitable[Outcome[Completion]]]
    ) -> Callable[[], Awaitable[Outcome[Completion]]]:
        """`run`, through the registration seam, attributed to the provider that will answer."""
        return wrap(
            run,
            distribution=bound.distribution,
            contract=_CONTRACT,
            plugin=bound.ref.provider,
            stage=f"llm:{role}",
        )

    def _fault(self, bound: _Bound, role: str, fault: Exception) -> LLMProviderFaultError:
        return LLMProviderFaultError(
            f"provider '{bound.ref.provider}' (role '{role}') raised "
            f"{type(fault).__name__}: {fault}. That is not an LLMError, so nothing downstream "
            f"could have caught it by class — it is a defect in the provider adapter, not a "
            f"failure mode of the model.",
            provider=bound.ref.provider,
            model=bound.ref.model,
        )

    def _loop_detected(self, bound: _Bound, role: str, accumulated: str) -> LLMGenerationLoopError:
        return LLMGenerationLoopError(
            f"provider '{bound.ref.provider}' (role '{role}') was generating a repeating span "
            f"and was stopped after {len(accumulated)} characters rather than left to keep "
            f"filling the terminal. This is a loop-breaker for a model that got stuck, not a "
            f"judgment about the content — retrying the identical prompt against the same "
            f"model is likely to loop again; try a different prompt, role, or model.",
            provider=bound.ref.provider,
            model=bound.ref.model,
        )


def llm_service(
    *,
    registry: Registry,
    roles: LLMRoles,
    retry: RetryPolicy | None = None,
    loop_guard: LoopGuardConfig | None = None,
) -> LLMClient:
    """Build the run's `LLM`. This pack's own constructor, per `.phase2-design.md` §7.

    "Each pack builds its own service constructor … so a library caller is not forced through
    the CLI." `weft_engine.run_services.build_services` calls this one and adds the result to the
    run's `ServiceRegistry`; an embedding host application calls it directly with a role table
    it built itself.
    """
    return LLMClient(registry=registry, roles=roles, retry=retry, loop_guard=loop_guard)


def _provider_config(factory: Callable[..., object], mapping: RoleMapping) -> object | None:
    """A role's own settings, validated by the provider's `config_model` — `R41.1`.

    `None` when the role wrote none, so a provider built for a bare `{provider, model}` entry is
    constructed exactly as it was before this existed. Read through `unwrap_factory` for
    `_declared_catalogue`'s reason: `functools.partial` does not proxy attribute access, so a pack
    binding its settings at registration would otherwise appear to declare nothing.

    A provider that declares no `config_model` and is handed settings anyway **refuses**, naming
    them. Dropping them would leave an operator who set a temperature unable to tell that it never
    applied, which is the failure this whole repair exists to end.
    """
    settings = mapping.settings
    if not settings:
        return None
    declared = getattr(unwrap_factory(factory), "config_model", None)
    if not (isinstance(declared, type) and issubclass(declared, BaseModel)):
        raise ProviderSettingsUnsupportedError(
            f"role settings {sorted(settings)} were written for provider "
            f"'{mapping.provider}', which declares no configuration of its own — remove them "
            f"from this '[llm.roles]' entry, or name a provider that accepts them.",
            provider=mapping.provider,
            settings=tuple(sorted(settings)),
        )
    try:
        return declared.model_validate(settings)
    except ValidationError as invalid:
        #: `7.4`'s defect, one route later: a config model reached through a *new* path lets
        #: pydantic's own error — and its documentation URL — out to an operator who mistyped a
        #: key. Named here instead, with the keys this provider does accept, which is what
        #: `UnresolvedNameError`'s family does for every other name in this tree.
        accepted = tuple(sorted(declared.model_fields))
        offered = tuple(sorted(settings))
        raise ProviderSettingsUnsupportedError(
            f"[llm.roles] settings {list(offered)} are not all valid for provider "
            f"'{mapping.provider}': {invalid.error_count()} rejected. That provider accepts "
            f"{list(accepted)}.",
            provider=mapping.provider,
            settings=offered,
        ) from invalid


def _declared_catalogue(factory: Callable[..., object]) -> Sequence[str]:
    """A provider's declared `models`, read the documented way — through `unwrap_factory`.

    `functools.partial` does not proxy attribute access, so a pack binding its settings at
    registration (`partial(Provider, settings)` — `weft-store`'s shape) would otherwise
    advertise nothing and the model check would silently never run.

    A provider declaring nothing gets `()`, which turns the check off rather than refusing
    every model: a name this code cannot check must be passed through, not guessed at.
    """
    declared = getattr(unwrap_factory(factory), "models", ())
    if isinstance(declared, str) or not isinstance(declared, Sequence):
        return ()
    return [str(entry) for entry in cast("Sequence[object]", declared)]


#: Stated so a reader of this module sees that the service Protocol is satisfied structurally,
#: the same way a plugin satisfies its contract, and so a checker verifies it once here rather
#: than at every `ServiceRegistry.add(LLM, ...)` call site.
_: type[LLM] = LLMClient
