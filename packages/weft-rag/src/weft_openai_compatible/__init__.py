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

**It re-exports `weft_openai`'s classes rather than subclassing them, and shares its `Settings`
class outright.** Nothing about a second account differs in *shape* — the same credential, the same
endpoint, the same patience knobs — so a subclass adding no field would be a knob that does
nothing, which is the objection `weft-rag`'s own `pyproject.toml` raises against an empty extra.
What differs is the *instance*: `weft_kernel.discovery` validates `[packs.openai-compatible]`
against this model and hands the result here, and `register()` binds that instance rather than the
one `[packs.openai]` produced.

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

from functools import partial

from weft_embed.contract import Embedder
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_llm.contract import LLMProvider
from weft_openai.embedder import OpenAIEmbedder
from weft_openai.llm import OpenAILLMProvider
from weft_openai.settings import Settings
from weft_openai.vision import OpenAIVisionDescriber
from weft_vision import Describer

#: Each is the `openai` pack's own name with this account's prefix, so a reader of
#: `weft plugins list` can see at a glance which block configures which row. Three constants
#: rather than one, for the reason `weft_openai.__init__`'s docstring gives at length: one
#: constant serving two `registrar.add` calls is ledger task 8.15's defect exactly.
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


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register the three `weft_openai` adapters against this account's own settings.

    `settings` is `[packs.openai-compatible]`, validated by `weft_kernel.discovery` against the
    model `weft_openai` shares with this pack — a different instance of the same class, which is
    the whole mechanism: one class describes what an account *is*, and each pack's block says what
    one account *holds*.

    `partial`, never a closure, for the reason `weft_openai.register` states and ledger task 9.4
    paid for: `weft_kernel.registry.unwrap_factory` peels a `partial` and nothing else, so a
    closure makes the class invisible to every reader that inspects a factory rather than an
    instance — which once cost a pack a silent absence from `weft delete`'s fan-out (`L9.55`).
    """
    registrar.add(Embedder, EMBEDDER_NAME, partial(OpenAIEmbedder, settings))
    registrar.add(LLMProvider, PROVIDER_NAME, partial(OpenAILLMProvider, settings))
    registrar.add(Describer, VISION_NAME, partial(OpenAIVisionDescriber, settings))


__all__ = [
    "DISCLOSURE",
    "EMBEDDER_NAME",
    "PROVIDER_NAME",
    "VISION_NAME",
    "Settings",
    "register",
]
