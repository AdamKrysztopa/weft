"""The `Prompts` service — resolve a prompt by name, render it through the seam.

`.phase2-design.md` §7: "each pack builds its own service constructor
(`weft_llm.client.llm_service`, `weft_prompts.registry_service`,
`weft_retrieve.engine.stage_lookup`) so a library caller is not forced through the CLI." This is
that constructor for prompts. (The design record calls the module `registry_service`; it is
`registry.py` here, so the file name mirrors what it holds and
`tests/unit/weft_prompts/test_registry.py` mirrors it back — the convention every pack follows.)

**No prompt registry of our own** — `.phase2-design.md` decision 20. The one asset a bespoke
registry would need is raise-on-collision with `override()` as a separate named operation, and
`weft_kernel.registry` already has it: `DuplicateRegistrationError` printing the `[plugins]`
TOML line an operator would write, the pin itself as the override, and the displaced registration
kept in `Registry.displaced()` rather than dropped. So this module holds a `Registry`, a small
instance cache and nothing else. An unknown name is refused by `UnknownPluginError`, which already
names the contract, the name and every registered option — requirement 5, for free.

**Rendering goes through `weft_kernel.seam.wrap`.** A prompt is a plugin running outside `Runner`,
which is the case `weft_cli.ask` set the precedent for: the span, the error attribution and the
blocking-call guard are the seam's, and a prompt that reads a file it should not is caught by the
same detector every other plugin faces.
"""

from collections.abc import Awaitable, Callable
from typing import cast

from pydantic import BaseModel

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_llm.payload import Rendered
from weft_prompts.contract import Prompt

#: The contract name the seam stamps on every prompt span and attributed error.
_CONTRACT = "Prompt"


class PromptRegistry:
    """This run's answer to "render the prompt called `name`".

    Satisfies `weft_prompts.contract.Prompts` structurally — never by inheriting it.

    **One instance per prompt name, for the run.** A prompt holds no per-call state and its
    templates are class data, so rebuilding one per render would buy nothing and cost the
    `__init_subclass__` work every time.
    """

    def __init__(self, registry: Registry) -> None:
        self._registry = registry
        self._instances: dict[str, Prompt] = {}

    async def render(self, name: str, values: BaseModel, ctx: Context) -> Outcome[Rendered]:
        """`name`'s prompt, rendered from `values`, or the registry's own refusal by name."""
        entry = self._registry.entry(Prompt, name)
        instance = self._instances.get(name)
        if instance is None:
            instance = cast("Prompt", entry.factory(None))
            self._instances[name] = instance
        sealed: Callable[[BaseModel, Context], Awaitable[Outcome[Rendered]]] = wrap(
            instance.render,
            distribution=entry.distribution,
            contract=_CONTRACT,
            plugin=name,
            stage=f"prompt:{name}",
        )
        return await sealed(values, ctx)


def prompts_service(registry: Registry) -> PromptRegistry:
    """Build the run's `Prompts`. The pack's own constructor — see the module docstring."""
    return PromptRegistry(registry)
