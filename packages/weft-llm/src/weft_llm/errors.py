"""The fourteen-class `LLMError` taxonomy every `LLMProvider` raises from.

`.phase2-design.md` §7: "a taxonomy nobody catches is documentation." This one is caught in
two places by construction — the retry wrapper (one task later) retries exactly
`LLMTransientError` and nothing else, and the three-tier structured-output cascade
(`weft-prompts`, also one task later) re-raises `LLMPermissionDeniedError` rather than
stepping down a tier, because a bad credential surfacing as a low structured-output score
is the worst failure mode a cascade can produce. Both consumers decide on the *class*, never
on a vendor's own string, which is the whole reason this hierarchy exists rather than every
provider inventing its own.

**Two branches under `LLMError`, plus one sibling.** `LLMTransientError` is worth retrying —
`transient=True` is set once, on the branch, so a leaf class cannot forget it.
`LLMPermanentError` never is. `LLMCompletionError` is neither: the vendor answered
successfully and the *answer* could not be used (the JSON-rescue cascade's last tier failing
to parse anything at all), so retrying the identical call is exactly as likely to fail again
— it is not a fact about the transport, which is what `transient` describes.

**`provider` and `model` are carried on every instance**, not only on the four attribution
fields `weft_kernel.errors.WeftError` already has. Attribution answers "which pack, which
plugin, which stage" — useful for finding the code, not for reading the message. An operator
staring at a raised `LLMRateLimitError` wants to know which *account* and which *model* hit
the limit without opening a traceback, and a run mixing `generate` (`gpt-4o-mini`) and
`grade` (a different model, same or different provider) can raise the same error class from
either role.
"""

from weft_kernel.errors import WeftError


class LLMError(WeftError):
    """Root of the taxonomy. Every exception an `LLMProvider` raises is one of these.

    Catching `LLMError` catches everything this pack and every provider pack raise from a
    generation call, without also swallowing an unrelated `KeyError` a caller would want to
    see — the same discipline `WeftError` itself states, narrowed to this one family.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        transient: bool = False,
        pack: str | None = None,
        contract: str | None = None,
        plugin: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(
            message, transient=transient, pack=pack, contract=contract, plugin=plugin, stage=stage
        )
        self.provider = provider
        self.model = model


class LLMTransientError(LLMError):
    """Worth retrying — the vendor's own answer to "is this the connection or the request?".

    `transient` is fixed to `True` here so no leaf below can forget to set it; a provider
    pack raising one of the four leaves never touches the keyword at all.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        pack: str | None = None,
        contract: str | None = None,
        plugin: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            model=model,
            transient=True,
            pack=pack,
            contract=contract,
            plugin=plugin,
            stage=stage,
        )


class LLMRateLimitError(LLMTransientError):
    """The account is over its request or token budget for the window the vendor tracks."""


class LLMTimeoutError(LLMTransientError):
    """The request was sent and no answer arrived before the client's own deadline."""


class LLMConnectionError(LLMTransientError):
    """The request never reached the vendor at all — DNS, TLS, a dropped socket."""


class LLMServiceUnavailableError(LLMTransientError):
    """The vendor accepted the connection and answered with its own failure — a 5xx class."""


class LLMPermanentError(LLMError):
    """Will refuse identically on retry. `transient` is fixed to `False` for the same reason
    `LLMTransientError` fixes it to `True` — a leaf class states nothing about the keyword.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        model: str,
        pack: str | None = None,
        contract: str | None = None,
        plugin: str | None = None,
        stage: str | None = None,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            model=model,
            transient=False,
            pack=pack,
            contract=contract,
            plugin=plugin,
            stage=stage,
        )


class LLMAuthenticationError(LLMPermanentError):
    """The credential itself is wrong, missing, or expired."""


class LLMPermissionDeniedError(LLMPermanentError):
    """The credential is real but is not allowed the model, endpoint or action requested.

    Caught by name rather than folded into `LLMAuthenticationError` at either of the two
    call sites `.phase2-design.md` §7 names for it: an account that can call one model and
    not another needs a different remedy from a key that is simply wrong, and the structured-
    output cascade re-raises this one specifically rather than stepping down a tier — a bad
    key surfacing as a low structured-output score is the failure mode that repair exists to
    prevent.
    """


class LLMBadRequestError(LLMPermanentError):
    """The vendor rejected the shape of the request itself — malformed, not merely refused."""


class LLMNotFoundError(LLMPermanentError):
    """The model, deployment or endpoint named in the request does not exist for this account."""


class LLMContentFilterError(LLMPermanentError):
    """The vendor's own moderation refused the request or the completion before it was returned."""


class LLMContextLengthError(LLMPermanentError):
    """The conversation, once tokenised, is longer than the model accepts."""


class LLMProviderFaultError(LLMPermanentError):
    """A provider let something out that is not an `LLMError` — a bug in the adapter, named.

    `.phase2-design.md` §7 enforces "a taxonomy nobody catches is documentation" two ways, and
    this class is the first: "the client wraps anything escaping a provider that is not an
    `LLMError` into `LLMProviderFaultError` naming the provider, and a test drives an injected
    failing transport and asserts **only** `LLMError` subclasses escape." Without it every
    consumer of an `LLM` would have to catch `Exception` to be safe, which is the same as
    catching nothing.

    Permanent, because a `KeyError` inside an adapter does not become a different `KeyError`
    on the second attempt — retrying a bug turns a stack trace into a timeout.
    """


class NativeStructuredUnsupportedError(LLMPermanentError):
    """`complete_structured` was called for a role whose provider is not `NativeStructured`.

    The cascade asks `native_structured_available` first and never sees this; it exists for
    the caller that does not ask. Refusing by name is the alternative to the silent step-down
    a `hasattr` guard produces, which is the reference defect `.phase2-design.md` §3 replaces
    `hasattr` to avoid in the first place.
    """


class LLMCompletionError(LLMError):
    """The call succeeded and the answer could not be used — not a fact about the transport.

    `transient` stays at its base default, `False`: nothing about resending the identical
    request makes a differently-shaped answer more likely. Constructed by the structured-
    output cascade `weft-prompts` ships, once its last tier exhausts every way it knows to
    parse a completion into the type it was asked for — never by a provider itself, which
    has no opinion on what its caller intended to do with the text it returned.

    **Constructed, and returned as the reason on a `Failed` rather than raised.** The cascade
    "returns `Failed` and never leaks an exception past the seam" (`.phase2-design.md` §7),
    because the reference's narrower tier-3 catch set let a malformed completion raise out of
    `execute()`. This class is still what phrases that `Failed`: the message carries the
    provider, the model and the truncated raw text, which is the only diagnostic that survives
    a total parse failure.
    """
