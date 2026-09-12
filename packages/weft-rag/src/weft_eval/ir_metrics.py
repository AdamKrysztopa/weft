"""The four IR metrics — precision@k, recall@k, mean average precision, NDCG@k.

Task **4.2**, `docs/internal/build-ledger.md`: a metric suite with every recorded defect fixed at
the door. These four score a `RetrievalSample` — a ranked list of retrieved ids against a
ground-truth relevance set — and never read a passage's text, which is exactly why they are
`RetrievalMetric`s rather than `GenerationMetric`s under `weft_eval.contract`'s split.

**The `k`-in-the-name property, held where it is this task's to hold.** R5: `PrecisionAtK`/
`RecallAtK`/`NDCG` build `metric_name` from `self.k` correctly at the per-metric level — this
kind of property actually breaks one layer up, in a caller that hardcodes a literal
`'precision_at_k'` string as a report key while the real `k` is caller-supplied. That breakage is
a *report's* defect, not this plugin's — `metric_
name` below is built from `self._config.k` exactly once, at the point of construction, so nothing
downstream can restate it wrong without reading it wrong first. Task 4.3 is what checks that a run
record's own display honours what this field already says.

**Empty relevant-id set is `NothingToProduce`, not a computed zero.** `weft_eval.contract`'s own
module docstring states the rule this suite applies uniformly: nothing to compare against is
nothing to compare against, independent of what the retrieval side carries. `MeanAveragePrecision`
has no `k` and no configuration at all — its own name promises none, so unlike the other three it
declares `config_model` as an empty frozen model rather than inventing a knob nobody asked for.

**A metric named `@k` refuses rather than reports when fewer than `k` candidates came back.**
Task **16.7**, `12` §3: every shipped rung ends in `repack: {top_n: 8}`, so a named-rung run
asking for `recall@10` was silently scored over at most 8 — a number that answers a question
nobody asked. `PrecisionAtK`, `RecallAtK` and `NDCGAtK` (`MRRAtK` too, added by the same task) all
carry the identical guard, checked once here rather than three times per class: `len(payload.
retrieved) < k` returns `Failed`, not `NothingToProduce` — there was something to score and the
metric could not score what its own name claims, which is a fact about the run's configuration
rather than an honest absence of ground truth. `weft_eval.aggregate.aggregate` already excludes
failures and reports the exclusion count, so a run half of whose questions retrieved fewer than
`k` reports that instead of a quietly depressed mean.
"""

import math
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.contract import MetricScore, RetrievalSample
from weft_kernel.context import Context
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced


class TopKConfig(BaseModel):
    """Shared `with:` shape for `PrecisionAtK`, `RecallAtK` and `NDCGAtK` — one tunable, `k`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many top-ranked results this metric considers. Required, not defaulted — an operator
    #: who does not state `k` has not chosen one, the same argument `AtThresholdConfig.threshold`
    #: already makes for its own required field.
    k: int = Field(ge=1)


class NoConfig(BaseModel):
    """The empty `with:` shape for a metric with nothing to tune — `MeanAveragePrecision`."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def _top_k_ids(payload: RetrievalSample, k: int) -> tuple[str, ...]:
    return tuple(passage.id for passage in payload.retrieved[:k])


class PrecisionAtK:
    """Of the top `k` retrieved ids, the fraction that are relevant.

    Standard textbook definition: the denominator is `k` itself, not `min(k, len(retrieved))` —
    an empty slot among the top `k` counts as a miss rather than being excused from the count,
    which is what makes precision comparable across samples with different retrieval depths.
    That argument is about a retrieval that *returned* fewer relevant results within a `k` it
    was actually capable of filling; it says nothing about a pipeline that could never have
    returned `k` candidates at all, which is the module docstring's `@k` refusal, below.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    #: Task 4.7, Q6: pure arithmetic over ids already in the sample, no credential, no network,
    #: no model download — part of the deterministic gate subset.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        if len(payload.retrieved) < k:
            return Failed(
                reason=(
                    f"a metric named @{k} cannot be computed over {len(payload.retrieved)} "
                    f"candidates — the run retrieved fewer than it claims to score. Lower the "
                    f"metric's k, or raise the retrieval depth the rung packs."
                )
            )

        hits = sum(1 for doc_id in _top_k_ids(payload, k) if doc_id in payload.relevant_ids)
        return Produced(value=MetricScore(metric_name=f"precision@{k}", value=hits / k))


class RecallAtK:
    """Of every relevant id, the fraction found somewhere in the top `k` retrieved.

    Also refuses when fewer than `k` candidates came back — see the module docstring.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        if len(payload.retrieved) < k:
            return Failed(
                reason=(
                    f"a metric named @{k} cannot be computed over {len(payload.retrieved)} "
                    f"candidates — the run retrieved fewer than it claims to score. Lower the "
                    f"metric's k, or raise the retrieval depth the rung packs."
                )
            )

        found = sum(1 for doc_id in _top_k_ids(payload, k) if doc_id in payload.relevant_ids)
        return Produced(
            value=MetricScore(metric_name=f"recall@{k}", value=found / len(payload.relevant_ids))
        )


class MeanAveragePrecision:
    """The mean, over every relevant id found, of precision measured at its own rank.

    No `k` — the whole ranked list is considered, which is what the name promises and `PrecisionAt
    K`/`RecallAtK` deliberately do not: those two are windowed by construction, this one is not.
    """

    config_model: ClassVar[type[NoConfig]] = NoConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: NoConfig | None = None) -> None:
        del config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        hits = 0
        precision_sum = 0.0
        for rank, passage in enumerate(payload.retrieved, start=1):
            if passage.id in payload.relevant_ids:
                hits += 1
                precision_sum += hits / rank

        return Produced(
            value=MetricScore(
                metric_name="mean_average_precision",
                value=precision_sum / len(payload.relevant_ids),
            )
        )


class NDCGAtK:
    """Normalized discounted cumulative gain over the top `k`, binary relevance.

    `relevant_ids` carries no grade, so gain is 1.0 for a relevant id and 0.0 otherwise — the
    ideal ordering places every relevant id first, which is what `idcg` computes without needing
    to re-sort `payload.retrieved` itself.

    Also refuses when fewer than `k` candidates came back — see the module docstring.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        if len(payload.retrieved) < k:
            return Failed(
                reason=(
                    f"a metric named @{k} cannot be computed over {len(payload.retrieved)} "
                    f"candidates — the run retrieved fewer than it claims to score. Lower the "
                    f"metric's k, or raise the retrieval depth the rung packs."
                )
            )

        dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank, doc_id in enumerate(_top_k_ids(payload, k), start=1)
            if doc_id in payload.relevant_ids
        )
        ideal_hits = min(k, len(payload.relevant_ids))
        idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))

        return Produced(value=MetricScore(metric_name=f"ndcg@{k}", value=dcg / idcg))


class MRRAtK:
    """One over the rank of the first relevant result within the top `k`, or zero if none is.

    **A zero here is a measurement, not a failure** — nothing relevant came back — and the two
    are kept apart the way `eval/metrics.py`'s own `reciprocal_rank_at_k` docstring already
    states for the identical arithmetic. `NothingToProduce` is the absence: a sample with no
    relevant ids has nothing to be first.

    Also refuses when fewer than `k` candidates came back — see the module docstring.
    """

    config_model: ClassVar[type[TopKConfig]] = TopKConfig
    #: Pure arithmetic over ids already in the sample — no credential, no network, no model.
    runs_in_gate: ClassVar[bool] = True

    def __init__(self, config: TopKConfig) -> None:
        self._config = config

    async def evaluate(self, payload: RetrievalSample, ctx: Context) -> Outcome[MetricScore]:
        del ctx
        if not payload.relevant_ids:
            return NothingToProduce(reason="no relevant ids to score retrieval against")

        k = self._config.k
        if len(payload.retrieved) < k:
            return Failed(
                reason=(
                    f"a metric named @{k} cannot be computed over {len(payload.retrieved)} "
                    f"candidates — the run retrieved fewer than it claims to score. Lower the "
                    f"metric's k, or raise the retrieval depth the rung packs."
                )
            )

        reciprocal_rank = 0.0
        for rank, doc_id in enumerate(_top_k_ids(payload, k), start=1):
            if doc_id in payload.relevant_ids:
                reciprocal_rank = 1.0 / rank
                break

        return Produced(value=MetricScore(metric_name=f"mrr@{k}", value=reciprocal_rank))
