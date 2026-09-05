"""First-party OpenAI adapter pack — a vendor in its own distribution, publishing nothing.

`weft-embed` publishes the `Embedder` contract and this pack registers under
it; nothing here publishes a contract of its own, because nothing about one
vendor's API needs one. It is a separate distribution for two reasons, and
neither is taxonomy. **A vendor SDK is a dependency**: putting it in the pack
that publishes a contract would make every install of that contract pay for
an HTTP client it may never call. **And a vendor must be removable**: a
generation pack that names no vendor is only checkable if the vendor lives
somewhere else, which is the whole shape of ledger task 2.30.

**The deterministic embedder stays, and stays the default.** `weft-embed`'s
`hash` plugin is what `poe ci-checks` runs against — no credential, no
network, no model download — and `openai` is what an operator selects when a
vector needs to mean something. Two registrations under one contract, chosen
by name in a pipeline document (or by `[services] embed` in `weft.toml`
until a document reaches `weft index`), never by a branch inside one class.

**Registered through the same public `weft.packs` entry point a third party
uses**, with nothing extra for being first-party — fitness function 2.

**Task 2.30 adds a second contract under the same account.** `register`
below now also registers `OpenAILLMProvider` as `"openai"` for
`weft_llm.contract.LLMProvider` — the vendor adapter growing a second
capability rather than a second pack, because both plugins share the one
thing a vendor pack actually owns: an authenticated account. See
`weft_openai.llm`'s own module docstring for the mapping table that keeps
OpenAI's exception hierarchy out of every pack downstream of `weft-llm`.
"""

from functools import partial

from weft_embed.contract import Embedder
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_llm.contract import LLMProvider
from weft_openai.embedder import (
    DEFAULT_MODEL,
    NAME,
    EmbeddingRequestFailedError,
    MissingApiKeyError,
    OpenAIEmbedder,
    OpenAIEmbedderConfig,
    UnembeddableNodeError,
)
from weft_openai.llm import DEFAULT_MODEL as DEFAULT_LLM_MODEL
from weft_openai.llm import OpenAILLMConfig, OpenAILLMProvider
from weft_openai.settings import Settings

#: What this pack touches — ledger task **6.31**, `02` §2 → *The trust model*.
#:
#: **The address is configuration, so the disclosure names the setting rather than a host.** The
#: OpenAI SDK reads `OPENAI_BASE_URL` for itself when `base_url` is unset, so what an operator can
#: actually check is *which knob decides where this goes*, and `network` says that. `02` §2's own
#: rule is why this is prose and concrete strings rather than a boolean: "a hostname is
#: information, `network: true` is noise."
#:
#: **And it is informational, never a claim weft checks** — nothing here is verified, enforced or
#: granted. It exists because the alternative an operator reads is `not disclosed`, which is what
#: this pack said before task 6.31 despite being the one distribution in the set that cannot work
#: without an account.
DISCLOSURE = Disclosure(
    network=("api.openai.com, or whatever [packs.openai] base_url / OPENAI_BASE_URL names",),
    filesystem=(),
    subprocess=(),
    note=(
        "Sends prompts and text to be embedded to an OpenAI-compatible API, using the credential "
        "in [packs.openai] api_key or OPENAI_API_KEY. Every completion and every embedding "
        "leaves this process. Registers an Embedder and an LLMProvider; nothing else in Weft "
        "calls out unless a pipeline names one of them."
    ),
)


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `OpenAIEmbedder` and `OpenAILLMProvider`, both as `"openai"`, one account.

    `settings` is bound in through `functools.partial`, exactly as
    `weft_store` binds its connection string, so `Runner.resolve`'s
    `entry.factory(spec.config)` call becomes `OpenAIEmbedder(settings,
    spec.config)` — the account from the pack's settings block, the model and
    its width from the stage's own `with:`. `OpenAILLMProvider` takes no
    stage `with:` of its own — see `weft_llm.contract.LLMProvider`'s module
    docstring on why `model` is a per-call argument rather than constructor
    state — so its factory ignores the second positional argument entirely.
    """
    registrar.add(Embedder, NAME, partial(OpenAIEmbedder, settings))
    registrar.add(LLMProvider, NAME, partial(OpenAILLMProvider, settings))


__all__ = [
    "DEFAULT_LLM_MODEL",
    "DEFAULT_MODEL",
    "NAME",
    "EmbeddingRequestFailedError",
    "MissingApiKeyError",
    "OpenAIEmbedder",
    "OpenAIEmbedderConfig",
    "OpenAILLMConfig",
    "OpenAILLMProvider",
    "Settings",
    "UnembeddableNodeError",
    "register",
]
