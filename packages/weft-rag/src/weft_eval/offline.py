"""The deterministic, gate-safe metric subset — task **4.7**, the reading half of Q6.

`weft_eval.contract`'s own module docstring settles the mechanism: `GenerationMetric`/
`RetrievalMetric` both set `required_declarations = ("runs_in_gate",)`, so `weft_kernel.
registry` itself refuses any metric — first-party or a stranger's alike — that never states
whether it runs in the gate. This module is the other half: given a `Registry`, which
registered names actually declared `True`. Derived from what is registered, never a second,
hand-maintained list — `Registry.names_for`'s own docstring gives the identical argument for
its own existence ("the list gets hand-maintained... exactly the drift it exists to prevent"),
applied here to a second question over the same registrations.

**"The deterministic subset must be identifiable as a subset" is what `gate_subset` answers.**
An operator asking `weft eval metrics` (task 4.7's CLI surface, `weft_cli.eval_commands.
EvalMetricsCommand`) gets this function's own output rendered — never a static paragraph in a
manual that can drift from what is actually installed.

**Asking about one metric by name is a different question from listing all of them, and gets a
different answer.** `resolve_metric` looks a name up across both contracts and returns its
unwrapped target, or refuses with `UnknownMetricNameError` — `01` requirement 5's rule, FF12's
family — naming every metric name actually registered, across both contracts, as
`valid_options`. A metric found but declared `runs_in_gate=False` is not this function's
concern: **a metric that cannot run must refuse loudly saying why and what would permit it,
not return a score and not be silently skipped** (CLAUDE.md) — `MetricNeedsCredentialsError`
below is that refusal, reading the metric's own optional `gate_unsafe_reason` when it states
one and falling back to a generic explanation when it does not, exactly as `intact`'s own
convention-not-seam status already works elsewhere in this tree.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from weft_eval.contract import GenerationMetric, RetrievalMetric
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.registry import Registry, unwrap_factory

#: Every contract `gate_subset`/`resolve_metric` walks — both halves of task 4.2's split.
_METRIC_CONTRACTS: Final[tuple[type[object], ...]] = (GenerationMetric, RetrievalMetric)

_GENERIC_UNSAFE_REASON: Final[str] = (
    "needs something a CI gate cannot supply — a credential, a network call, or a downloaded "
    "model — and declares no more specific reason of its own"
)


class UnknownMetricNameError(WeftError, UnresolvedNameError):
    """`name` is not registered under `GenerationMetric` or `RetrievalMetric`.

    FF12's family: `valid_options` is every metric name actually registered, across both
    contracts — the same "list what does exist" rule `weft_cli.eval_commands.UnknownRunIdError`
    already gives a run id.
    """

    def __init__(self, message: str, *, valid_options: tuple[str, ...], name: str) -> None:
        super().__init__(message)
        self.valid_options = valid_options
        self.name = name


class MetricNeedsCredentialsError(WeftError):
    """`name` is registered and real, but declared `runs_in_gate=False`.

    Not a name-resolution failure — the name is valid, and there is no alternative name to
    offer. `reason` is the metric's own `gate_unsafe_reason` when it states one, so the message
    a caller reads says why and what would permit it, never only that the metric refused.
    """

    def __init__(self, message: str, *, metric: str, reason: str) -> None:
        super().__init__(message)
        self.metric = metric
        self.reason = reason


class GateSubset(BaseModel):
    """Every metric name actually registered, partitioned by whether it runs in the gate.

    `gate_safe` is what a deterministic CI run may score with no credentials and no network;
    `gate_unsafe` is everything else, present here precisely so "what runs offline" is
    answerable in one call rather than by elimination.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate_safe: tuple[str, ...] = Field(default=())
    gate_unsafe: tuple[str, ...] = Field(default=())


def gate_subset(registry: Registry) -> GateSubset:
    """Every `GenerationMetric`/`RetrievalMetric` name `registry` holds, partitioned by
    `runs_in_gate`. Never touches a metric never registered under either contract — `names_for`
    on a contract nothing registered answers `frozenset()`, not an error, and this function
    inherits that.
    """
    safe: list[str] = []
    unsafe: list[str] = []
    for contract in _METRIC_CONTRACTS:
        for name in registry.names_for(contract):
            target = unwrap_factory(registry.lookup(contract, name))
            if getattr(target, "runs_in_gate", False):
                safe.append(name)
            else:
                unsafe.append(name)
    return GateSubset(gate_safe=tuple(sorted(safe)), gate_unsafe=tuple(sorted(unsafe)))


def resolve_metric(registry: Registry, name: str) -> object:
    """`name`'s unwrapped registered target, checked across both metric contracts.

    Raises `UnknownMetricNameError` — never `weft_kernel.registry.UnknownPluginError`, which
    would only ever list one contract's names and so understate what is actually registered —
    for a name neither contract holds.
    """
    for contract in _METRIC_CONTRACTS:
        if name in registry.names_for(contract):
            return unwrap_factory(registry.lookup(contract, name))

    valid_options = tuple(
        sorted({found for contract in _METRIC_CONTRACTS for found in registry.names_for(contract)})
    )
    available = ", ".join(f"'{option}'" for option in valid_options) if valid_options else "none"
    raise UnknownMetricNameError(
        f"'{name}' is not a registered metric. Registered metrics: {available}.",
        valid_options=valid_options,
        name=name,
    )


def require_gate_safe(registry: Registry, name: str) -> None:
    """Refuse loudly if `name` is registered but declared `runs_in_gate=False`.

    Raises `UnknownMetricNameError` for a name nothing registered (via `resolve_metric`), or
    `MetricNeedsCredentialsError` naming why and what would permit it. Returns `None`, never a
    value, for a metric that is gate-safe — the absence of a refusal *is* the answer.
    """
    target = resolve_metric(registry, name)
    if getattr(target, "runs_in_gate", False):
        return
    reason = getattr(target, "gate_unsafe_reason", "") or _GENERIC_UNSAFE_REASON
    raise MetricNeedsCredentialsError(
        f"'{name}' cannot run in the deterministic, gate-safe subset: {reason}",
        metric=name,
        reason=reason,
    )


__all__ = [
    "GateSubset",
    "MetricNeedsCredentialsError",
    "UnknownMetricNameError",
    "gate_subset",
    "require_gate_safe",
    "resolve_metric",
]
