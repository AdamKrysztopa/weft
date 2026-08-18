"""Model strings — what the operator asked for, and what the vendor is handed.

Task **2.10**: "the prompt layer, the cascade, **model strings** and the `LLMError` taxonomy
ship outside the kernel." `docs/04-reference-inventory.md`:294 files the reference's `model_strings`
as a **rewrite**, and names precisely what is worth carrying: "the **two-field distinction**:
`requested_provider` (catalog identity) vs `litellm_provider` (runtime prefix). Subtle,
learned the hard way, and what keeps telemetry attributing cost to the real vendor. Carry the
4-step `find_runtime_match` disambiguation explicitly — that is the hard part." The row also
records why none of its code is worth lifting: `ResolvedLiteLLMTarget` had "zero consumers
outside its own module and zero tests". So this is the *distinction*, written fresh, with
consumers: `weft_llm.client` resolves every role's model string through both functions below.

**Weft has no litellm, so the second field is not a runtime prefix — it is the string the
`LLMProvider` plugin is handed at the call.** The distinction survives the translation intact:
`ModelRef.provider` is the catalogue identity (a registry plugin name, what telemetry and an
invoice attribute cost to), and `ModelRef.model` is the runtime identity (what
`LLMProvider.complete(..., model=...)` receives). Collapsing them is exactly the mistake the
reference's row warns about: `"openai/gpt-4o-mini"` handed straight to the OpenAI SDK is a 404,
and `"gpt-4o-mini"` recorded as the provider attributes a bill to nobody.

**A slash is not evidence of a prefix, and that is the whole of the disambiguation.**
`meta-llama/Llama-3-8B` is one model id; `openai/gpt-4o-mini` is a provider and a model. The
only thing that separates them is whether the segment before the slash names a provider *this
deployment mapped* — so `providers` is an argument, never a hard-coded vendor list this module
would then have to maintain. With no providers named, no string is ever split, which is the
safe direction: a model id survives untouched and nothing is silently truncated.
"""

from collections.abc import Collection, Sequence

from pydantic import BaseModel, ConfigDict

from weft_kernel.errors import UnresolvedNameError
from weft_llm.errors import LLMPermanentError


class ModelProviderMismatchError(LLMPermanentError):
    """A role's model string carries a provider prefix naming a *different* provider.

    `generate = { provider = "scripted", model = "openai/gpt-4o-mini" }` is two answers to
    one question, and guessing which one the operator meant is the silent-coercion defect
    `docs/02-extension-model.md` §5 records four times over. Refused, naming both.
    """


class UnknownModelError(LLMPermanentError, UnresolvedNameError):
    """A provider declares a model catalogue and the requested model is not in it.

    Names the model asked for and every model the provider advertises — requirement 5, moved
    one hop earlier than the vendor's own 404 so the remedy is a `weft.toml` line rather than
    an HTTP status code.

    Fitness function 12's family: `valid_options` is every model the provider's own
    catalogue advertises.
    """

    def __init__(
        self, message: str, *, valid_options: tuple[str, ...], provider: str, model: str
    ) -> None:
        LLMPermanentError.__init__(self, message, provider=provider, model=model)
        self.valid_options = valid_options


class AmbiguousModelError(LLMPermanentError, UnresolvedNameError):
    """A short model name matches two catalogue entries, and neither is more right.

    The fourth step of the disambiguation refuses instead of taking the first match: picking
    `eu/small-v2` over `us/small-v2` because it sorts first is a data-residency decision made
    by an accident of ordering.

    Fitness function 12's family: `valid_options` is every catalogue entry the short name
    matched — the choice this code refuses to make by ordering.
    """

    def __init__(
        self, message: str, *, valid_options: tuple[str, ...], provider: str, model: str
    ) -> None:
        LLMPermanentError.__init__(self, message, provider=provider, model=model)
        self.valid_options = valid_options


class ModelRef(BaseModel):
    """One resolved model string, in the two fields the reference's row says must stay apart."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Exactly what the operator wrote in `[llm.roles]`, prefix and all. Kept so an error
    #: message can quote the line rather than the parsed halves. `""` when the role named no
    #: model at all.
    requested: str
    #: Catalogue identity — the `LLMProvider` plugin name that will answer. This is what
    #: telemetry and cost attribution key on.
    provider: str
    #: Runtime identity — the string handed to `LLMProvider.complete(..., model=...)`. `""`
    #: when the role named no model, which a single-model provider legitimately ignores.
    model: str


def model_ref(*, provider: str, requested: str | None, providers: Collection[str] = ()) -> ModelRef:
    """Split a role's `model` string into the two fields, refusing a prefix that disagrees.

    `providers` is the set of provider names this deployment actually mapped; a slash is read
    as a provider prefix only when the segment before it is in that set. See the module
    docstring for why that test, and not the presence of a slash, is the deciding one.
    """
    if not requested:
        return ModelRef(requested="", provider=provider, model="")
    head, slash, tail = requested.partition("/")
    if not slash or head not in providers:
        return ModelRef(requested=requested, provider=provider, model=requested)
    if head != provider:
        raise ModelProviderMismatchError(
            f"model string '{requested}' names provider '{head}', but the [llm.roles] entry "
            f"using it resolves to provider '{provider}'. Refused rather than guessed: drop "
            f"the prefix, or point the role at '{head}'.",
            provider=provider,
            model=requested,
        )
    return ModelRef(requested=requested, provider=provider, model=tail)


def find_runtime_match(ref: ModelRef, catalogue: Sequence[str]) -> ModelRef:
    """Resolve `ref.model` against a provider's declared catalogue, in four ordered steps.

    1. the model as written is a catalogue entry — nothing to disambiguate;
    2. the catalogue writes entries provider-qualified (`acme/small-v2`) and the operator
       did not;
    3. exactly one entry ends in the model as written, whatever it is qualified by;
    4. nothing, or more than one — refused by name, never resolved by ordering.

    Only called for a provider that declares a catalogue: a provider advertising nothing is
    asked for whatever the operator wrote, which is the only honest thing to do with a name
    this code cannot check.
    """
    if ref.model in catalogue:
        return ref
    qualified = f"{ref.provider}/{ref.model}"
    if qualified in catalogue:
        return ref.model_copy(update={"model": qualified})
    suffixed = [entry for entry in catalogue if entry.rpartition("/")[2] == ref.model]
    if len(suffixed) == 1:
        return ref.model_copy(update={"model": suffixed[0]})
    advertised = ", ".join(catalogue) or "(none declared)"
    if not suffixed:
        raise UnknownModelError(
            f"provider '{ref.provider}' does not offer model '{ref.model}' (from "
            f"'{ref.requested}'). Models it advertises: {advertised}.",
            valid_options=tuple(catalogue),
            provider=ref.provider,
            model=ref.model,
        )
    raise AmbiguousModelError(
        f"model '{ref.model}' (from '{ref.requested}') matches {len(suffixed)} entries in "
        f"provider '{ref.provider}''s catalogue: {', '.join(suffixed)}. Write one of them in "
        f"full — choosing between them by ordering is a decision this code must not make.",
        valid_options=tuple(suffixed),
        provider=ref.provider,
        model=ref.model,
    )
