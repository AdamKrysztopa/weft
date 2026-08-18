"""First-party generation-support pack. Publishes `LLMProvider` and registers no vendor.

Task **2.30**: "the generation pack names no vendor, because a provider adapter is its own
pack and the offline default is a deterministic scripted provider." This pack is the "own
pack" a vendor's adapter registers *under* — `weft-openai` (a separate distribution)
registers `openai` here the same way any stranger's `weft-anthropic` could, through the same
public `weft.packs` entry point, with nothing extra for being first-party.

Registers exactly one plugin itself: `scripted`, the deterministic offline default that
keeps `poe ci-checks` and every fresh checkout running with no credential and no network —
see `weft_llm.scripted`'s module docstring.

**Task 2.10 completed the pack**: the `LLM` service (`weft_llm.client`), the retry wrapper
(`weft_llm.retry`), the model-string vocabulary (`weft_llm.models`) and the role table the
service resolves against (`weft_llm.roles`). `LLM` and `TokenSink` are exported here for a
library caller, but neither carries a `version` and neither is registered under a name — the
mechanical rule `.phase2-design.md` §3 states for a *service*, which is what keeps both out of
`manual/contract-reference.md` and out of fitness function 9(c)'s left side. `NativeStructured`
is exported for the opposite reason: it *is* a capability, derived by `isinstance` from what a
provider implements, and the reference should say so.
"""

from pydantic import BaseModel, ConfigDict

from weft_kernel.discovery import PackRegistrar
from weft_llm.client import LLMClient, NullSink, llm_service
from weft_llm.contract import LLM, LLM_CONTRACT_VERSION, LLMProvider, NativeStructured, TokenSink
from weft_llm.models import ModelRef, find_runtime_match, model_ref
from weft_llm.payload import (
    Completion,
    Conversation,
    Message,
    MessageRole,
    OnFailure,
    Rendered,
    TokenChunk,
)
from weft_llm.retry import RetryPolicy, with_retry
from weft_llm.roles import LLMRoles, RoleMapping, UnmappedLLMRoleError
from weft_llm.scripted import NAME, ScriptedConfig, ScriptedProvider


class Settings(BaseModel):
    """`weft-llm` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `ScriptedProvider` as `"scripted"` for `LLMProvider`.

    The only plugin this pack ships.
    """
    del settings
    registrar.add(LLMProvider, NAME, ScriptedProvider)


__all__ = [
    "LLM",
    "LLM_CONTRACT_VERSION",
    "Completion",
    "Conversation",
    "LLMClient",
    "LLMProvider",
    "LLMRoles",
    "Message",
    "MessageRole",
    "ModelRef",
    "NativeStructured",
    "NullSink",
    "OnFailure",
    "Rendered",
    "RetryPolicy",
    "RoleMapping",
    "ScriptedConfig",
    "ScriptedProvider",
    "Settings",
    "TokenChunk",
    "TokenSink",
    "UnmappedLLMRoleError",
    "find_runtime_match",
    "llm_service",
    "model_ref",
    "register",
    "with_retry",
]
