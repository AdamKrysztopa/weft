"""`[llm]` — the one file's answer to which model answers a role, and how hard to try.

`.phase2-design.md` §7, decision 9: "a pipeline stage never names a provider or a model —
it names a **role**." A single `[services] llm = "..."` — the shape `[services] embed` and
`[services] store` already take — would force a grader and a generator onto one model, or
push a `model:` string into every technique plugin's own `with:` block, the same closed
key space `.phase2-findings.md` finding 9 rules out for a store or an embedder. A role is an
open string key an operator invents in this file; nothing in the registry names one, and
nothing here decides what a role is *for* — that is a technique plugin's own `role: str`
configuration field.

```toml
[llm.roles]
generate = { provider = "openai",   model = "gpt-4o-mini" }
grade    = { provider = "openai",   model = "gpt-4o-mini" }
route    = { provider = "scripted" }

[llm.retry]
attempts = 3
base_delay_ms = 250

[llm.loop_guard]
min_period = 50
```

**Task 3.10 added `[llm.loop_guard]`** alongside `[llm.retry]`, on the identical footing: a
table an operator may omit entirely (every `weft_llm.loop_guard.LoopGuardConfig` field
defaults to a measured value, per that module's own docstring) or override one key of,
never a second parser for the same idea.

**Not `[services]`, deliberately.** `weft_cli.services`'s own module docstring already
refuses an `llm` key under `[services]` — a role picks a *configuration entry*, not a single
plugin name, so it earns its own top-level table rather than growing `ServiceSelection` a
field that means something different from its two siblings.

**The models live in `weft-llm`; this module is the parse, and only the parse.** Task 2.30
declared `RoleMapping`/`LLMRoles`/`UnmappedLLMRoleError` here because nothing consumed them
yet. Task 2.10 built the consumer — `weft_llm.client.LLMClient` — and a service published by
`weft-llm` cannot import the CLI that assembles it without turning `.phase2-design.md` §2's
one-way dependency chain into a cycle. They moved to `weft_llm.roles` and are re-exported
here, so every existing importer is unaffected and an operator's one file is still read
exactly once, in the same pass that reads the allow-list, the pack settings and `[services]`.

**Nothing here builds the `LLM` service.** `weft_cli.run_services.build_services` does, from
what this module returns, and that assembler lands with task 2.8.

**Repair, 2026-08-20** (`docs/01-high-level-plan.md` item 12's own dated paragraph carries the
argument in full): the unknown-`[llm]`-key refusal below used to be a bare `WeftError`
computing `_KNOWN_LLM_KEYS` and interpolating them into the message only — invisible to fitness
function 12's family walk, which looks for a typed `valid_options` field, never message text.
`UnknownLLMKeyError` now carries it, the identical shape `weft_cli.config_surface.
UnknownConfigKeyError` already gives `config get`/`config set`'s own vocabulary. The three
malformed-shape checks below it (`[llm.roles]`/`[llm.retry]`/`[llm.loop_guard]` each not being a
table) stay bare `WeftError` — a type mismatch, not a name failing to resolve against a set of
alternatives.
"""

from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_llm.loop_guard import LoopGuardConfig
from weft_llm.retry import RetryPolicy
from weft_llm.roles import LLMRoles, RoleMapping, UnmappedLLMRoleError

#: Every key `[llm]` accepts. A key nothing reads is refused rather than ignored, the same
#: posture `weft_cli.services.service_selection_from_config` takes for `[services]`.
_KNOWN_LLM_KEYS = ("loop_guard", "retry", "roles")


class UnknownLLMKeyError(WeftError, UnresolvedNameError):
    """`[llm]` names a key this module does not read.

    Repair, 2026-08-20: the identical rule `weft_cli.config_surface.UnknownConfigKeyError`
    already gives `config get`/`config set`'s own sibling refusal, applied here — `01`
    requirement 5 and fitness function 12 require the valid keys as a typed field a caller can
    read, not only text inside the message a reviewer has to notice.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class LLMSection(BaseModel):
    """`weft.toml`'s whole `[llm]` block: who answers each role, the retry policy, and the
    degenerate-loop guard's thresholds.

    Every field defaults, so a `weft.toml` with no `[llm]` table at all still produces a usable
    section — a retrieval-only pipeline that never asks a model runs, and the assembler never
    has to decide what a missing block means.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    roles: LLMRoles = Field(default_factory=LLMRoles)
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    #: Task 3.10: `[llm.loop_guard]`, the operator-facing side of `weft_llm.loop_guard.
    #: LoopGuardConfig` — every measured constant `LLMClient.complete` stops a stream for is
    #: parameterisable from `weft.toml`, the same way `retry` above already is, rather than
    #: fixed in code.
    loop_guard: LoopGuardConfig = Field(default_factory=LoopGuardConfig)


def llm_section_from_config(document: dict[str, object] | None) -> LLMSection:
    """`[llm]` from a parsed `weft.toml`, refusing an unknown key under it by name."""
    if document is None or "llm" not in document:
        return LLMSection()
    llm = document["llm"]
    if not isinstance(llm, dict):
        raise WeftError(
            f"weft.toml's [llm] must be a table, not {type(llm).__name__} — found "
            f'`llm = {llm!r}`. Did you mean `[llm.roles]\\ngenerate = {{ provider = "openai" }}`?'
        )
    llm_table = cast("dict[str, object]", llm)
    unknown = sorted(key for key in llm_table if key not in _KNOWN_LLM_KEYS)
    if unknown:
        raise UnknownLLMKeyError(
            f"unknown [llm] key(s) in weft.toml: {', '.join(repr(key) for key in unknown)}. "
            f"[llm] accepts {', '.join(repr(key) for key in _KNOWN_LLM_KEYS)}. A key nothing "
            f"reads is refused rather than ignored.",
            valid_options=_KNOWN_LLM_KEYS,
        )
    return LLMSection(
        roles=_roles(llm_table), retry=_retry(llm_table), loop_guard=_loop_guard(llm_table)
    )


def llm_roles_from_config(document: dict[str, object] | None) -> LLMRoles:
    """`[llm.roles]` alone. Kept as the narrow reader every caller before task 2.10 used."""
    return llm_section_from_config(document).roles


def _roles(llm_table: dict[str, object]) -> LLMRoles:
    if "roles" not in llm_table:
        return LLMRoles()
    roles = llm_table["roles"]
    if not isinstance(roles, dict):
        raise WeftError(
            f"weft.toml's [llm.roles] must be a table, not {type(roles).__name__} — found "
            f'`roles = {roles!r}`. Did you mean `generate = {{ provider = "openai" }}`?'
        )
    parsed = {
        str(role): RoleMapping.model_validate(mapping)
        for role, mapping in cast("dict[str, object]", roles).items()
    }
    return LLMRoles(roles=parsed)


def _retry(llm_table: dict[str, object]) -> RetryPolicy:
    if "retry" not in llm_table:
        return RetryPolicy()
    retry = llm_table["retry"]
    if not isinstance(retry, dict):
        raise WeftError(
            f"weft.toml's [llm.retry] must be a table, not {type(retry).__name__} — found "
            f"`retry = {retry!r}`. Did you mean `[llm.retry]\\nattempts = 3`?"
        )
    return RetryPolicy.model_validate(retry)


def _loop_guard(llm_table: dict[str, object]) -> LoopGuardConfig:
    if "loop_guard" not in llm_table:
        return LoopGuardConfig()
    loop_guard = llm_table["loop_guard"]
    if not isinstance(loop_guard, dict):
        raise WeftError(
            f"weft.toml's [llm.loop_guard] must be a table, not {type(loop_guard).__name__} — "
            f"found `loop_guard = {loop_guard!r}`. Did you mean `[llm.loop_guard]\\n"
            f"min_period = 50`?"
        )
    return LoopGuardConfig.model_validate(loop_guard)


__all__ = [
    "LLMRoles",
    "LLMSection",
    "LoopGuardConfig",
    "RetryPolicy",
    "RoleMapping",
    "UnknownLLMKeyError",
    "UnmappedLLMRoleError",
    "llm_roles_from_config",
    "llm_section_from_config",
]
