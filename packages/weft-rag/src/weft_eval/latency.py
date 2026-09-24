"""Query latency, summarised as nearest-rank percentiles — ledger task **33.8**.

Task 33.7 persisted each question's own retrieval seconds
(`weft_eval.run_record.PerQuestionSeconds`); this module turns those samples into the three
percentiles `weft eval run`/`weft eval compare` print.

**Nearest rank, and withheld when the rank is the last sample — the owner's Q4, 2026-09-15.**
The value at rank ⌈q·n⌉ of the sorted samples is a real observation, never an interpolation
between two of them. When that rank equals `n`, the "percentile" is the maximum under another
name, so it is reported as `NotAggregated`, carrying the sample count, rather than as a value
that looks like a measurement it is not. The rank is computed with exact rational arithmetic
(`fractions.Fraction`), never `math.ceil(quantile * n)` — a float product can land a hair past
an integer (e.g. `0.95 * 200 == 190.00000000000003`) and move a rank by one.

This is never a gate: `01` -> *Fitness functions* rejects duration thresholds as
machine-dependent, and nothing here raises or refuses on a slow rung.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from math import ceil

from pydantic import BaseModel, ConfigDict

from weft_eval.run_record import NotAggregated, PerQuestionSeconds
from weft_kernel.payload import Produced


def nearest_rank(samples: Sequence[float], quantile: float) -> Produced[float] | NotAggregated:
    """The `quantile` percentile of `samples`, at nearest rank.

    The `quantile` percentile of `samples`, at nearest rank ⌈quantile·n⌉ — see the module
    docstring for why that rank is computed over `Fraction`, and why a rank of `n` is withheld
    rather than reported as the maximum.
    """
    n = len(samples)
    if n == 0:
        return NotAggregated(reason="no question was timed")
    rank = ceil(Fraction(str(quantile)) * n)
    if rank >= n:
        return NotAggregated(
            reason=(
                f"rank {rank} of {n} samples would be the maximum, not a distinct "
                f"percentile observation"
            )
        )
    return Produced(value=sorted(samples)[rank - 1])


class LatencySummary(BaseModel):
    """p50/p95/p99 over one run's `PerQuestionSeconds` — see `latency_summary`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    samples: int
    p50: Produced[float] | NotAggregated
    p95: Produced[float] | NotAggregated
    p99: Produced[float] | NotAggregated


def latency_summary(seconds: PerQuestionSeconds | None) -> LatencySummary | None:
    """Summarise a record's per-question seconds, or `None` when none were measured.

    `seconds.seconds.values()` summarised as `LatencySummary`, or `None` for a record that
    measured nothing (`PerQuestionSeconds` itself absent — a record written before task 33.7, or
    a run given no `--questions` to time).
    """
    if seconds is None:
        return None
    values = list(seconds.seconds.values())
    return LatencySummary(
        samples=len(values),
        p50=nearest_rank(values, 0.5),
        p95=nearest_rank(values, 0.95),
        p99=nearest_rank(values, 0.99),
    )
