"""`[llm.roles]` as a model — which provider and model answer a call made under a role.

`.phase2-design.md` §7, decision 9: "a pipeline stage never names a provider or a model —
it names a **role**." A role is an open string key an operator invents in `weft.toml`;
nothing in the registry names one, and nothing here decides what a role is *for* — that is a
technique plugin's own `role: str` configuration field.

**Moved here from `weft_engine.llm_roles` by task 2.10, and the move is forced.** 2.30 built
these models in the CLI because nothing consumed them yet. The consumer built here is
`weft_llm.client.LLMClient`, and a service published by `weft-llm` cannot import the CLI that
assembles it — `.phase2-design.md` §2's one-way chain (`weft-kernel ← weft-store ← weft-llm ←
weft-prompts ← weft-retrieve ← weft-generate`) puts `weft-cli` downstream of everything. §7's
own sentence, "each pack builds its own service constructor so a library caller is not forced
through the CLI", says the same thing from the other side: a library caller needs a role table
without needing a `weft.toml` parser. `weft_engine.llm_roles` keeps the parse and re-exports these
names, so an operator's one file is still read exactly once.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_llm.scripted import NAME as _SCRIPTED


class RoleMapping(BaseModel):
    """One `[llm.roles]` entry: the `LLMProvider` name, the model, and that model's settings.

    **`settings` is a sub-table, and the nesting is what keeps a typo loud** — `R41.1`. This
    entry stays `extra="forbid"`, because task `7.4` found by running the binary that a mistyped
    key here — `nonsense = 1` — printed a pydantic traceback, and the repair made it a named
    refusal *while `weft.toml` is read*
    (`tests/unit/weft_cli/test_malformed_config_refuses.py`). Flat sampler keys would make that
    typo indistinguishable from a provider's own knob, so it could only be refused when the role
    was first called — and never for a role a run does not reach. One level of nesting buys the
    refusal back.

    What goes *inside* `settings` is the named provider's own configuration, validated by **its**
    `config_model` when the `LLM` service binds the role (`weft_llm.client._provider_config`) —
    the same route `entry.factory(spec.config)` gives a pipeline stage. This module cannot check
    those keys itself: it names no capability and holds no registry, which is why `provider` above
    is unchecked here too. A typo inside the sub-table is refused by the provider's own model,
    which is `extra="forbid"` for both `OpenAILLMConfig` and `OpenAIEmbedderConfig`.

    Before this, `[llm.roles]` took `provider` and `model` and nothing else while
    `OpenAILLMConfig`'s docstring described "a `generate` role and a `grade` role sharing one
    account at two different temperatures". Nothing could express it, and every local measurement
    in Phase 41 therefore ran at whatever the server's default sampler was.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: An `LLMProvider` plugin name — `"openai"`, `"scripted"`, or a stranger's pack.
    #: Resolved by the `LLM` service against the registry, never checked here: this module
    #: names no capability and holds no registry to check one against.
    provider: str = Field(min_length=1)
    #: `None` is legitimate — `scripted` reads nothing from it, and a provider with exactly
    #: one model available has nothing to disambiguate. May carry a `provider/model` prefix,
    #: which `weft_llm.models.model_ref` checks against `provider` above.
    model: str | None = None

    #: The named provider's own configuration. Empty when nothing was written, which is what lets
    #: `_bind` tell "no settings" from "settings that did not arrive": the first builds the
    #: provider with `None` exactly as before, and the second is now impossible rather than silent.
    settings: Mapping[str, object] = Field(default_factory=dict)


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

    def resolve(self, role: str, *, providers: Sequence[str] = ()) -> RoleMapping:
        """`role`'s mapping, or `UnmappedLLMRoleError` naming it and every role that is mapped.

        `providers` is every installed `LLMProvider` name; the refusal suggests one of them.
        """
        mapped = self.roles.get(role)
        if mapped is not None:
            return mapped
        options = tuple(sorted(self.roles))
        available = ", ".join(options) or "(none mapped)"
        raise UnmappedLLMRoleError(
            f"no [llm.roles] entry maps role '{role}'. Roles mapped in weft.toml: {available}. "
            + _remedy(role, providers=providers, has_table=bool(self.roles)),
            valid_options=options,
        )


def _remedy(role: str, *, providers: Sequence[str], has_table: bool) -> str:
    """The line to paste — never `scripted`, which cannot give a role a structured answer (R41.7).

    A literal newline, not `\\n`: the line is pasted into weft.toml, and the escape printed itself
    once (Phase 8's close review).
    """
    answering = sorted(name for name in providers if name != _SCRIPTED)
    if not answering:
        return (
            f"No provider that can answer '{role}' is installed: "
            'pip install "weft-rag[openai]", then map the role to it.'
        )
    entry = f'{role} = {{ provider = "{answering[0]}", model = "<model>" }}'
    if has_table:
        return f"Add this line under [llm.roles] in weft.toml:\n{entry}"
    return f"Add these two lines to weft.toml:\n[llm.roles]\n{entry}"
