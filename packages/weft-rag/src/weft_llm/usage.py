"""What a run's model calls cost — one `UsageEntry` per completed call, tallied in a scope.

Task **33.6**: a run knows the tokens each role and each pipeline position used, for every
provider that reports usage. `weft_llm.client.LLMClient.complete` calls `record_usage` once
per call that finished streaming; nothing is recorded outside an open `recording_usage()`
scope, the same nesting-`ContextVar` shape `weft_kernel.blocking.guard` already uses to scope a
detector to one call's lifetime without threading a token through every signature on the path.

**A provider that cannot report is named, never counted as zero.** `UsageEntry.usage` is
`None` for exactly that case (`weft_llm.contract.UsageReporting`'s own docstring) — a `0` would
read as a call measured and found free, which is never what happened.
"""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar

from pydantic import BaseModel, ConfigDict

from weft_llm.payload import TokenUsage


class UsageEntry(BaseModel):
    """One call's tally: who asked, from where, through which provider and model, at what cost."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `[llm.roles]` role the call was bound to (`weft_llm.roles.LLMRoles`), for an `LLM`
    #: call — or, for an embedder, which is bound to no role, the fixed string `"embed"` naming
    #: the `[services]` key that selected it instead.
    role: str
    #: The pipeline position that asked, read off `weft_kernel.seam.current_stage()` at the
    #: call site rather than inferred from `role` — two roles can share a position and one
    #: role can serve two positions (`weft_llm.payload.TokenChunk.stage`'s own note, R10.1).
    position: str
    #: The registered provider name, e.g. `"openai"` — never the vendor model string alone.
    provider: str
    model: str
    #: `None` names a provider that does not report usage on a stream. Never `0`.
    usage: TokenUsage | None


class UsageTally:
    """What one `recording_usage()` scope collects — entries in the order calls completed."""

    def __init__(self) -> None:
        self._entries: list[UsageEntry] = []

    @property
    def entries(self) -> tuple[UsageEntry, ...]:
        return tuple(self._entries)

    def record(self, entry: UsageEntry) -> None:
        """Append `entry`.

        Public so `record_usage`, in this module but outside the class, can call it without a
        private cross-object access — `entries` stays the read side.
        """
        self._entries.append(entry)


_current_tally: ContextVar[UsageTally | None] = ContextVar("weft_llm_usage_tally", default=None)


@contextmanager
def recording_usage() -> Generator[UsageTally]:
    """Open a scope that tallies every `record_usage` call made while it is open.

    Scopes nest: a call inside two nested scopes is recorded into the innermost only, the
    same `ContextVar.set`/`reset` shape `weft_kernel.blocking.guard` uses to scope one
    detector to one call's lifetime. Outside any scope, `record_usage` is a no-op — a run
    nobody is tallying genuinely has nowhere to put an entry.
    """
    tally = UsageTally()
    token = _current_tally.set(tally)
    try:
        yield tally
    finally:
        _current_tally.reset(token)


def record_usage(entry: UsageEntry) -> None:
    """Append `entry` to the innermost open `recording_usage()` scope, if one is open."""
    tally = _current_tally.get()
    if tally is not None:
        tally.record(entry)
