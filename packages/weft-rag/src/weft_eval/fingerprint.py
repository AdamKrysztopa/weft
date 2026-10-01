"""An evidence fingerprint — what a claim's numbers depend on, and when they stop being evidence.

Task **44.62**. A claim says a rung beat a baseline *as it was run*. Executable evidence routes
real questions, so "as it was run" has to be checkable against the tree that is running now,
without making a change to a document, a version bump or a rename invalidate evidence it does not
touch. The fingerprint is the smallest set of things that decides:

- **`rung`, `baseline`** — the stages of the two query pipelines compared (`stage_identity`).
- **`index`, `baseline_index`** — the stages of the index pipeline each arm read. One pipeline for
  most experiments; two when the arms were indexed differently.
- **`judge`** — the digest of the judge prompt, when the metric is an LLM judge, because a changed
  prompt is a changed measurement.
- **`profiler`** — the profiler version, when the claim's regime or router reads a profile.

**What is deliberately not in it.** The package version, `vars` (a routing label such as
`route.summary` reaches no stage), a pipeline's name, a stage's provenance, comments, any
documentation, and anything about the machine that ran — its `[llm.roles]`, its account settings.
Each is a reason evidence could look stale that has no bearing on whether it is.

The fingerprint is pinned in the claim by `weft eval claims pin` and compared by `weft eval claims
check`, so the act of saying "the records still speak for this pipeline" is a diff a reviewer reads.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from enum import StrEnum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.resolution import ResolvedPipeline, pipeline_identity

#: Each component's name, in the order a reader should see a moved one reported.
_COMPONENTS: Final[tuple[str, ...]] = (
    "rung",
    "baseline",
    "index",
    "baseline_index",
    "judge",
    "profiler",
)


class Staleness(StrEnum):
    """Whether the tree that is running still matches what a claim was validated against."""

    VALID = "valid"
    POSSIBLY_STALE = "possibly-stale"
    DEFINITELY_STALE = "definitely-stale"


def stage_identity(pipeline: ResolvedPipeline) -> str:
    """The digest of what `pipeline`'s stages run, with every label stripped.

    `weft_kernel.resolution.pipeline_identity` over the stages alone: a `vars` entry reaches a stage
    only by being substituted into its config, which the stage's own config already shows, so
    leaving `vars` out moves nothing that executes and ignores a `route.summary` added later.
    """
    return pipeline_identity(ResolvedPipeline(name="", stages=pipeline.stages))


class ClaimFingerprint(BaseModel):
    """The material inputs to one claim — see the module docstring for what each is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rung: str = Field(min_length=1)
    baseline: str = Field(min_length=1)
    index: str = Field(min_length=1)
    baseline_index: str = Field(min_length=1)
    #: `None` when the metric is not an LLM judge: there is no prompt to have changed.
    judge: str | None = Field(default=None, min_length=1)
    #: `None` when nothing the claim rests on reads a profile.
    profiler: str | None = Field(default=None, min_length=1)

    def _by_name(self) -> Mapping[str, str | None]:
        return {name: getattr(self, name) for name in _COMPONENTS}

    def digest(self) -> str:
        """One string for the whole fingerprint, for a receipt or a log line to carry."""
        digest = hashlib.sha256()
        for name, value in self._by_name().items():
            for part in (name, "" if value is None else value):
                encoded = part.encode("utf-8")
                digest.update(len(encoded).to_bytes(4, "big") + encoded)
        return digest.hexdigest()[:32]

    def moved_to(self, live: ClaimFingerprint) -> tuple[str, ...]:
        """The components this pin holds that `live` no longer matches, in reporting order.

        A component this fingerprint never pinned (`None`) is not compared: it was not part of what
        the claim was validated against.
        """
        theirs = live._by_name()
        return tuple(
            name
            for name, value in self._by_name().items()
            if value is not None and theirs[name] != value
        )


class LiveEvidence(BaseModel):
    """What the running tree gives for one claim: its fingerprint, or why it cannot give one."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fingerprint: ClaimFingerprint | None
    unresolved: str | None

    @model_validator(mode="after")
    def _a_fingerprint_or_a_reason(self) -> Self:
        if (self.fingerprint is None) == (self.unresolved is None):
            raise ValueError(
                "LiveEvidence holds exactly one of a fingerprint or an unresolved reason."
            )
        return self


class StalenessReading(BaseModel):
    """A claim's staleness and every reason for it, so a reader sees what to look at."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    staleness: Staleness
    reasons: tuple[str, ...] = ()


def assess_staleness(
    pinned: ClaimFingerprint | None,
    live: LiveEvidence,
    *,
    recorded_major: str | None,
    current_major: str,
) -> StalenessReading:
    """Read a claim's pin against the live tree.

    A pinned component that moved is **definitely stale**, whatever else is true. Without a
    comparison there is no certainty either way, so **possibly stale**: the tree cannot be
    resolved here, or nothing was pinned — and an unpinned claim recorded under another package
    major says so, since that is all that is then known. A pin that matches is **valid** regardless
    of the package major: equal stages are equal stages.
    """
    if live.fingerprint is None:
        return StalenessReading(
            staleness=Staleness.POSSIBLY_STALE,
            reasons=(f"not compared with the live tree: {live.unresolved}",),
        )
    if pinned is not None:
        moved = pinned.moved_to(live.fingerprint)
        if moved:
            return StalenessReading(
                staleness=Staleness.DEFINITELY_STALE,
                reasons=tuple(f"{name} changed since the claim was pinned" for name in moved),
            )
        return StalenessReading(staleness=Staleness.VALID)
    reasons = ["no evidence fingerprint is pinned: run `weft eval claims pin`"]
    if recorded_major is not None and recorded_major.split(".")[0] != current_major.split(".")[0]:
        reasons.append(f"recorded under weft-rag {recorded_major}; this is {current_major}")
    return StalenessReading(staleness=Staleness.POSSIBLY_STALE, reasons=tuple(reasons))


__all__ = [
    "ClaimFingerprint",
    "LiveEvidence",
    "Staleness",
    "StalenessReading",
    "assess_staleness",
    "stage_identity",
]
