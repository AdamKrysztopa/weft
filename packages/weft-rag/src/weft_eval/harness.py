"""Score the gate-safe `RetrievalMetric` subset over real samples — task **4.9**.

`.phase4-design.md` §7's gap: `RunRecord` carried no metric scores, so `weft eval compare`
could only report that two runs' resolved pipelines *differ*, never what they *produced*. This
module is the evaluation-domain half of closing it — the orchestration half (retrieving real
passages through a resolved pipeline's own embed/store stages, for a caller-supplied set of
queries) is `weft_cli.eval_scoring`'s job, deliberately kept out of this pack: this module never
imports `weft_cli`, `weft_embed` or `weft_store`, and takes `RetrievalSample`s already built,
the same "business logic in the pack, orchestration in the driving adapter" split every other
Phase 4 module already holds.

**Every registered `RetrievalMetric`, never a fixed list of four.** `score_retrieval_gate_subset`
derives which names to score from `registry.names_for(RetrievalMetric)` intersected with
`weft_eval.offline.gate_subset`'s own `gate_safe` partition — the identical "capability is
derived, never declared" rule `weft_eval.offline`'s own module docstring already argues, applied
here to "which metrics get scored" rather than "which metrics may run in the gate." A stranger's
own gate-safe `RetrievalMetric` is scored on the same footing as any of the four this pack ships.

**Configuration is constructed generically, not by name.** A metric's `config_model` is either
built with no arguments (`weft_eval.ir_metrics.NoConfig`, `MeanAveragePrecision`'s own shape) or
needs `k` (`weft_eval.ir_metrics.TopKConfig`, three of the four) — `_metric_config` tries the
former and falls back to the latter on `pydantic.ValidationError`, so a stranger's own
zero-config or `k`-shaped `RetrievalMetric` is constructible here with no per-plugin branch.

**The report is keyed by what a metric computed, not by its registered name — R5, again.**
`weft_eval.aggregate.aggregate`'s own `MetricAggregate.reported_name` is read off the
observations themselves; this module uses it as the report key whenever a metric actually
produced one, falling back to the registered name only when every sample failed and nothing was
ever computed to report a name for — the identical fallback `weft_cli.eval_commands.
EvalMetricsCommand` gives no equivalent to, because this is the one place in the tree a metric's
own name can be genuinely unknown before it runs.

**Every score also carries which modality it came from — ledger task 9.12.** `RetrievalMetric`
scores `RetrievalSample`s, so `kind=MetricKind.RETRIEVAL` is a fact this module already knows
from *which contract it fetched the metric off of* (`registry.names_for(RetrievalMetric)`), not
a guess from the metric's own name. `_modality_slices` partitions each metric's own `samples` by
`sample.modality`, folds each partition with `aggregate()` again, and keeps only the partitions
that actually produced a mean — see `weft_eval.aggregate`'s own module docstring for why the
partitioning happens here rather than inside `aggregate()` itself: only the caller that paired
samples to outcomes can make that link.

**And which question `kind` it came from — ledger task 11.12, `_modality_slices`'s twin.**
`_question_kind_slices` partitions the identical `samples`/`outcomes` pairing by `sample.kind`
instead of `sample.modality`, folds each partition with `aggregate()` and keeps only the
partitions that produced a mean, on the identical footing. A sample whose `kind` is `""` —
unclassified — contributes no slice: an unclassified question is not a kind, and a `""` key in
`by_question_kind` would be a partition nobody could ask for by name.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from pydantic import BaseModel, ValidationError

from weft_eval.aggregate import MetricAggregate, PartitionSlice, aggregate
from weft_eval.contract import (
    MetricKind,
    MetricScore,
    QueryModality,
    RetrievalMetric,
    RetrievalSample,
)
from weft_eval.offline import gate_subset
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.registry import Registry, unwrap_factory


def _metric_config(config_model: type[BaseModel] | None, *, top_k: int) -> BaseModel | None:
    """`config_model`, built generically — no arguments if that validates, `k=top_k` otherwise.

    Every gate-safe `RetrievalMetric` this pack ships needs one of exactly these two shapes
    (`weft_eval.ir_metrics.NoConfig`/`TopKConfig`); a stranger's own metric needing a third shape
    is not this function's to guess at, and none of the four registered here does. `config_model`
    is read off the unwrapped factory the same defensive way `weft_kernel.resolution._validated_
    config` already reads it — `None` for a plugin that declares none, on the same footing an
    unconfigured plugin already has everywhere else in this tree (`entry.factory(None)`).
    """
    if config_model is None:
        return None
    try:
        return config_model()
    except ValidationError:
        return config_model(k=top_k)


def _modality_slices(
    samples: Sequence[RetrievalSample], outcomes: Sequence[Outcome[MetricScore]]
) -> Mapping[QueryModality, PartitionSlice]:
    """Partition `outcomes` by the `modality` of the `RetrievalSample` that produced each, fold
    each partition with `aggregate()`, and keep only the partitions that produced a mean.

    A partition whose observations all failed or had nothing to score contributes no slice — an
    absence and an error are not the same claim, the identical distinction `MetricAggregate.
    excluded` vs `nothing_to_produce` already keeps one level up.
    """
    by_modality: dict[QueryModality, list[Outcome[MetricScore]]] = {}
    for sample, outcome in zip(samples, outcomes, strict=True):
        by_modality.setdefault(sample.modality, []).append(outcome)

    slices: dict[QueryModality, PartitionSlice] = {}
    for modality, modality_outcomes in by_modality.items():
        partition = aggregate(modality_outcomes)
        if isinstance(partition, Produced):
            slices[modality] = PartitionSlice(
                mean=partition.value.mean,
                n=partition.value.n,
                stdev=partition.value.stdev,
            )
    return slices


def _question_kind_slices(
    samples: Sequence[RetrievalSample], outcomes: Sequence[Outcome[MetricScore]]
) -> Mapping[str, PartitionSlice]:
    """Partition `outcomes` by the `kind` of the `RetrievalSample` that produced each, fold each
    partition with `aggregate()`, and keep only the partitions that produced a mean.

    `_modality_slices`'s twin, sliced by `kind` instead — see the module docstring's own
    paragraph. A sample whose `kind` is `""` — unclassified — contributes no slice: an
    unclassified question is not a kind, and a `""` key in `by_question_kind` would be a
    partition nobody could ask for by name.
    """
    by_kind: dict[str, list[Outcome[MetricScore]]] = {}
    for sample, outcome in zip(samples, outcomes, strict=True):
        if sample.kind == "":
            continue
        by_kind.setdefault(sample.kind, []).append(outcome)

    slices: dict[str, PartitionSlice] = {}
    for kind, kind_outcomes in by_kind.items():
        partition = aggregate(kind_outcomes)
        if isinstance(partition, Produced):
            slices[kind] = PartitionSlice(
                mean=partition.value.mean,
                n=partition.value.n,
                stdev=partition.value.stdev,
            )
    return slices


async def score_retrieval_gate_subset(
    registry: Registry,
    samples: Sequence[RetrievalSample],
    *,
    top_k: int,
    ctx: Context,
) -> Mapping[str, Outcome[MetricAggregate]]:
    """Every gate-safe `RetrievalMetric` registered in `registry`, scored over `samples`.

    Returns one `Outcome[MetricAggregate]` per metric, keyed by what the metric computed — see
    the module docstring. An empty `samples` scores every metric against zero observations,
    which `weft_eval.aggregate.aggregate` already answers honestly (`Failed`, "no observations
    to aggregate"); this function invents no special case for it.
    """
    gate_safe_retrieval = registry.names_for(RetrievalMetric) & set(gate_subset(registry).gate_safe)

    report: dict[str, Outcome[MetricAggregate]] = {}
    for name in sorted(gate_safe_retrieval):
        factory = registry.lookup(RetrievalMetric, name)
        target = unwrap_factory(factory)
        config_model = cast("type[BaseModel] | None", getattr(target, "config_model", None))
        config = _metric_config(config_model, top_k=top_k)
        metric = cast(RetrievalMetric, factory(config))

        outcomes = [await metric.evaluate(sample, ctx) for sample in samples]
        outcome = aggregate(
            outcomes,
            kind=MetricKind.RETRIEVAL,
            by_modality=_modality_slices(samples, outcomes),
            by_question_kind=_question_kind_slices(samples, outcomes),
        )
        key = outcome.value.reported_name if isinstance(outcome, Produced) else name
        report[key] = outcome
    return report


__all__ = ["score_retrieval_gate_subset"]
