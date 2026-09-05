"""`[llm.roles]` as a model — which provider and model answer a call made under a role.

`.phase2-design.md` §7, decision 9: "a pipeline stage never names a provider or a model —
it names a **role**." A role is an open string key an operator invents in `weft.toml`;
nothing in the registry names one, and nothing here decides what a role is *for* — that is a
technique plugin's own `role: str` configuration field.

**Moved here from `weft_cli.llm_roles` by task 2.10, and the move is forced.** 2.30 built
these models in the CLI because nothing consumed them yet. The consumer built here is
`weft_llm.client.LLMClient`, and a service published by `weft-llm` cannot import the CLI that
assembles it — `.phase2-design.md` §2's one-way chain (`weft-kernel ← weft-store ← weft-llm ←
weft-prompts ← weft-retrieve ← weft-generate`) puts `weft-cli` downstream of everything. §7's
own sentence, "each pack builds its own service constructor so a library caller is not forced
through the CLI", says the same thing from the other side: a library caller needs a role table
without needing a `weft.toml` parser. `weft_cli.llm_roles` keeps the parse and re-exports these
names, so an operator's one file is still read exactly once.
"""

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.errors import UnresolvedNameError, WeftError


class RoleMapping(BaseModel):
    """One `[llm.roles]` entry: the `LLMProvider` name, and the model to ask it for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: An `LLMProvider` plugin name — `"openai"`, `"scripted"`, or a stranger's pack.
    #: Resolved by the `LLM` service against the registry, never checked here: this module
    #: names no capability and holds no registry to check one against.
    provider: str = Field(min_length=1)
    #: `None` is legitimate — `scripted` reads nothing from it, and a provider with exactly
    #: one model available has nothing to disambiguate. May carry a `provider/model` prefix,
    #: which `weft_llm.models.model_ref` checks against `provider` above.
    model: str | None = None


class UnmappedLLMRoleError(WeftError, UnresolvedNameError):
    """A call was made under a role `[llm.roles]` never named.

    States the role asked for and every role that *is* mapped, so a typo in a technique
    plugin's `role: str` configuration reads as a typo rather than a mystery — the same
    standard `weft_kernel.registry.UnknownPluginError` sets for a plugin name.

    Fitness function 12's family: `valid_options` is every role `[llm.roles]` does map.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class LLMRoles(BaseModel):
    """Every mapped role, from `weft.toml`'s `[llm.roles]` block. Empty is legitimate.

    A `weft.toml` naming no `[llm]` table at all resolves to an `LLMRoles` with nothing
    mapped — a retrieval-only pipeline that never asks a model still runs, per
    `.phase2-design.md`'s "no silent default" clause: nothing here invents a mapping, and
    the refusal below is loud rather than a fallback to some default provider.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: Mapping[str, RoleMapping] = Field(default_factory=dict)

    def resolve(self, role: str) -> RoleMapping:
        """`role`'s mapping, or `UnmappedLLMRoleError` naming it and every role that is mapped."""
        mapped = self.roles.get(role)
        if mapped is not None:
            return mapped
        options = tuple(sorted(self.roles))
        available = ", ".join(options) or "(none mapped)"
        raise UnmappedLLMRoleError(
            f"no [llm.roles] entry maps role '{role}'. Roles mapped in weft.toml: {available}. "
            f'Add, e.g., `[llm.roles]\\n{role} = {{ provider = "scripted" }}` to weft.toml.',
            valid_options=options,
        )
