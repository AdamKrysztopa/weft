"""The `Prompt` contract, and the `Prompts` service — published here, never by the kernel.

Task **2.10**: "the **prompt layer**, the cascade, model strings and the `LLMError` taxonomy
ship outside the kernel." A prompt names an LLM, so it belongs in `weft-prompts`, not the
kernel — and the shape earns that placement: a prompt is a Pydantic input model, an output
model and a locale key, translatable by construction, versioned, and already registry-based.

**`Prompt` is not a pipeline position.** Like `LLMProvider`, it declares no `Stage` base:
`.phase2-design.md` §3 groups the two under "named and registered, but not pipeline
positions". A pipeline names a technique; the technique names the prompt it asks. Prompts are
resolved by name through the `Prompts` service, never by `Runner.resolve`.

**`input_model` and `output_model` are declared in the Protocol body, deliberately.** They
therefore join `__protocol_attrs__` and become required for `isinstance` — which is the point:
a prompt whose inputs are untyped is the untyped-dict prompt this contract exists to replace.
The cost, stated so nobody rediscovers it: `issubclass` against a Protocol with non-method
members raises `TypeError`, so any future walk over registered contracts must use `isinstance`
against an instance, as `weft_prompts.registry` does.

**The blocker inherent in resolving prompt locales relative to a fixed loader path is avoided
here.** Resolving locales as `Path(__file__).parent.parent / 'locales'` means a pack cannot
ship its own prompts or translations. Here a prompt *is* a plugin in a pack, its translations
are class data, and nothing opens a file at all.

**No bespoke `PromptRegistry` is built** (`.phase2-design.md` decision 20): the one asset such
a thing would need is raise-on-collision with `override()` as a separate named operation, and
`weft_kernel.registry` already has exactly that — `DuplicateRegistrationError` printing the
`[plugins]` line, an operator pin as the override, and the loser kept in `Registry.displaced()`.
Prompts are ordinary plugins; A/B is a pin in `weft.toml`.
"""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_llm.payload import Rendered

#: Fitness function 6's subject for this contract.
PROMPT_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Prompt(Protocol):
    """One named, versioned, translatable question a model can be asked.

    `render` returns a decided `Outcome[Rendered]`, so a prompt that legitimately has nothing
    to ask (an evidence-free rerank, say) answers `NothingToProduce` rather than an empty
    conversation a provider would then be sent.
    """

    if TYPE_CHECKING:
        #: Declared only for a type checker, assigned for real after the class body, so it
        #: never joins `__protocol_attrs__` — the pattern every Phase 0/1/2 contract shares.
        version: ClassVar[str]

    #: The model `render` accepts. Required for `isinstance` — see the module docstring.
    input_model: ClassVar[type[BaseModel]]
    #: The model an answer to this prompt should validate as, or `None` when the answer is
    #: free text. What `weft_prompts.cascade.execute` is asked for, and what tier 1 hands a
    #: vendor as a JSON schema.
    output_model: ClassVar[type[BaseModel] | None]

    async def render(self, values: BaseModel, ctx: Context) -> Outcome[Rendered]: ...


Prompt.version = PROMPT_CONTRACT_VERSION


class Prompts(Protocol):
    """The run's prompt lookup — reached by `ctx.require(Prompts)`, never named in a pipeline.

    A service, so it carries no `version` and is not `@runtime_checkable`: `.phase2-design.md`
    §3's mechanical rule for keeping a service out of `manual/contract-reference.md` and out of
    fitness function 9(c)'s left side. Both omissions are load-bearing rather than oversights,
    and `tests/unit/weft_prompts/test_contract.py` asserts them.
    """

    async def render(self, name: str, values: BaseModel, ctx: Context) -> Outcome[Rendered]: ...
