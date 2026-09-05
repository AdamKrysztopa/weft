"""Unit tests for `weft_eval.offline`.

Mirrors `packages/weft-rag/src/weft_eval/offline.py`. Covers the happy path (`gate_subset`
partitions the real, registered suite into the expected gate-safe/gate-unsafe counts —
task 4.2's 15 traditional/IR metrics plus the demonstration metric, and the 6 LLM judges plus
`bertscore`), the edge case (a metric that is registered but declares `runs_in_gate=False`
refuses with a reason rather than a score), and the error case (a name nothing registered
refuses naming every metric that does exist, across both contracts).
"""

import pytest

from weft_eval import (
    BERTSCORE_NAME,
    FAITHFULNESS_NAME,
    OVERLAP_AT_THRESHOLD_NAME,
    Settings,
    register,
)
from weft_eval.offline import (
    MetricNeedsCredentialsError,
    UnknownMetricNameError,
    gate_subset,
    require_gate_safe,
)
from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry


def _registry() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-eval")
    register(registrar, Settings())
    registrar.commit()
    return registry


def test_gate_subset_partitions_the_real_suite_into_the_expected_counts() -> None:
    # Arrange
    registry = _registry()

    # Act
    subset = gate_subset(registry)

    # Assert — 22 registered (21 reference metrics + the demonstration), 15 gate-safe (4 IR + 11
    # traditional, `bertscore` excluded) and 7 gate-unsafe (the 6 LLM judges plus `bertscore`).
    assert len(subset.gate_safe) == 15
    assert len(subset.gate_unsafe) == 7
    assert OVERLAP_AT_THRESHOLD_NAME in subset.gate_safe
    assert FAITHFULNESS_NAME in subset.gate_unsafe
    assert BERTSCORE_NAME in subset.gate_unsafe
    # Sorted, and disjoint — every name accounted for exactly once.
    assert subset.gate_safe == tuple(sorted(subset.gate_safe))
    assert set(subset.gate_safe).isdisjoint(subset.gate_unsafe)


def test_require_gate_safe_refuses_a_judge_naming_why_and_what_would_permit_it() -> None:
    # Arrange
    registry = _registry()

    # Act / Assert
    with pytest.raises(MetricNeedsCredentialsError) as excinfo:
        require_gate_safe(registry, FAITHFULNESS_NAME)
    assert "faithfulness" in str(excinfo.value)
    assert "llm.roles" in excinfo.value.reason


def test_require_gate_safe_is_silent_for_a_gate_safe_metric() -> None:
    # Arrange
    registry = _registry()

    # Act / Assert — no exception is the whole answer.
    assert require_gate_safe(registry, OVERLAP_AT_THRESHOLD_NAME) is None


def test_resolve_an_unknown_metric_name_names_every_metric_that_does_exist() -> None:
    # Arrange
    registry = _registry()

    # Act / Assert
    with pytest.raises(UnknownMetricNameError) as excinfo:
        require_gate_safe(registry, "does-not-exist")
    assert FAITHFULNESS_NAME in excinfo.value.valid_options
    assert OVERLAP_AT_THRESHOLD_NAME in excinfo.value.valid_options
