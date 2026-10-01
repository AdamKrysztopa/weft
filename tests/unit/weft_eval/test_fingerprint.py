"""Task 44.62 — an evidence fingerprint names what a claim's numbers depend on, and nothing else.

A claim is evidence for a pipeline as it was measured. What can make it stale is the pipelines
involved (the rung, the baseline, the index both read), the judge's prompt when the metric is a
judge, and the profiler when a rule's regime reads one. A comment, a routing label or the version
of the package is none of those, so none of them may move the fingerprint.
"""

from collections.abc import Mapping
from typing import Any

import pytest

from weft_eval.fingerprint import (
    ClaimFingerprint,
    LiveEvidence,
    Staleness,
    assess_staleness,
    stage_identity,
)
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage


def _stage(stage_id: str = "retrieve", **config: Any) -> ResolvedStage:
    return ResolvedStage(
        id=stage_id,
        contract="Retriever",
        contract_version="1.0.0",
        use="vector-top-k",
        config=config or {"top_k": 5},
        distribution="weft-rag",
        provenance="doc",
    )


def _pipeline(*stages: ResolvedStage, name: str = "rung", **vars_: str) -> ResolvedPipeline:
    return ResolvedPipeline(name=name, vars=vars_, stages=stages or (_stage(),))


def test_a_routing_label_a_name_and_the_provenance_do_not_move_a_pipelines_evidence_identity() -> (
    None
):
    # Arrange
    measured = _pipeline(name="whole")
    relabelled = _pipeline(name="whole-wide", **{"route.summary": "Reads every leaf."})
    reattributed = _pipeline(_stage().model_copy(update={"provenance": "elsewhere"}), name="whole")

    # Act / Assert
    assert stage_identity(relabelled) == stage_identity(measured)
    assert stage_identity(reattributed) == stage_identity(measured)


@pytest.mark.parametrize(
    "changed",
    [
        _stage(top_k=6),
        _stage().model_copy(update={"use": "bm25-top-k"}),
        _stage().model_copy(update={"id": "search"}),
        _stage().model_copy(update={"distribution": "someone-else"}),
    ],
    ids=["config", "plugin", "stage-id", "distribution"],
)
def test_a_material_change_to_a_stage_moves_the_evidence_identity(changed: ResolvedStage) -> None:
    # Arrange
    measured = _pipeline(_stage(top_k=5))

    # Act / Assert
    assert stage_identity(_pipeline(changed)) != stage_identity(measured)


def test_a_stage_added_to_a_pipeline_moves_the_evidence_identity() -> None:
    # Act / Assert
    assert stage_identity(_pipeline(_stage(), _stage("pack"))) != stage_identity(_pipeline())


def _fingerprint(**changes: str | None) -> ClaimFingerprint:
    fields: Mapping[str, str | None] = {
        "rung": "r" * 32,
        "baseline": "b" * 32,
        "index": "i" * 32,
        "baseline_index": "i" * 32,
        "judge": "j" * 16,
        "profiler": "1",
    }
    return ClaimFingerprint.model_validate({**fields, **changes})


def test_a_fingerprint_digest_is_stable_and_moves_with_every_component() -> None:
    # Arrange
    base = _fingerprint()

    # Act / Assert
    assert base.digest() == _fingerprint().digest()
    for component in ("rung", "baseline", "index", "baseline_index", "judge", "profiler"):
        assert _fingerprint(**{component: "changed"}).digest() != base.digest(), component


def test_a_fingerprint_names_the_components_that_moved_and_only_those() -> None:
    # Arrange
    pinned = _fingerprint()
    live = _fingerprint(rung="x" * 32, judge="y" * 16)

    # Act / Assert
    assert pinned.moved_to(live) == ("rung", "judge")
    assert pinned.moved_to(pinned) == ()


def test_a_component_the_claim_never_pinned_is_not_compared() -> None:
    # Arrange — a retrieval metric has no judge prompt, a claim with no regime reads no profiler.
    pinned = _fingerprint(judge=None, profiler=None)
    live = _fingerprint(judge="y" * 16, profiler="2")

    # Act / Assert
    assert pinned.moved_to(live) == ()


def _assess(
    pinned: ClaimFingerprint | None,
    live: LiveEvidence,
    *,
    recorded: str | None = "3.0.0",
    current: str = "3.1.0",
) -> tuple[Staleness, str]:
    reading = assess_staleness(pinned, live, recorded_major=recorded, current_major=current)
    return reading.staleness, " | ".join(reading.reasons)


def test_a_pinned_claim_matching_the_live_tree_is_valid_whatever_the_package_major() -> None:
    # Arrange
    live = LiveEvidence(fingerprint=_fingerprint(), unresolved=None)

    # Act / Assert
    assert _assess(_fingerprint(), live) == (Staleness.VALID, "")
    assert _assess(_fingerprint(), live, recorded="2.7.0", current="4.0.0") == (
        Staleness.VALID,
        "",
    )


@pytest.mark.parametrize(
    "component", ["rung", "baseline", "index", "baseline_index", "judge", "profiler"]
)
def test_a_pinned_component_that_moved_makes_the_claim_definitely_stale_naming_it(
    component: str,
) -> None:
    # Arrange
    live = LiveEvidence(fingerprint=_fingerprint(**{component: "moved"}), unresolved=None)

    # Act
    staleness, reasons = _assess(_fingerprint(), live)

    # Assert
    assert staleness is Staleness.DEFINITELY_STALE
    assert component in reasons


def test_an_unpinned_claim_is_possibly_stale_and_says_how_to_pin_it() -> None:
    # Arrange
    live = LiveEvidence(fingerprint=_fingerprint(), unresolved=None)

    # Act
    staleness, reasons = _assess(None, live, recorded="3.1.0", current="3.1.0")

    # Assert
    assert staleness is Staleness.POSSIBLY_STALE
    assert "weft eval claims pin" in reasons


def test_an_unpinned_claim_from_another_major_also_says_which_package_it_was_recorded_under() -> (
    None
):
    # Arrange
    live = LiveEvidence(fingerprint=_fingerprint(), unresolved=None)

    # Act
    staleness, reasons = _assess(None, live, recorded="2.7.0", current="3.1.0")

    # Assert
    assert staleness is Staleness.POSSIBLY_STALE
    assert "recorded under weft-rag 2.7.0; this is 3.1.0" in reasons


def test_a_claim_whose_pipelines_cannot_be_resolved_here_is_possibly_stale_with_the_reason() -> (
    None
):
    # Arrange
    live = LiveEvidence(fingerprint=None, unresolved="'hyde' is not a pipeline here")

    # Act
    staleness, reasons = _assess(_fingerprint(), live)

    # Assert
    assert staleness is Staleness.POSSIBLY_STALE
    assert "'hyde' is not a pipeline here" in reasons


def test_a_moved_component_outranks_an_unpinned_reading() -> None:
    # Arrange — pinned and moved is definite; there is nothing weaker to say about it.
    live = LiveEvidence(fingerprint=_fingerprint(rung="moved"), unresolved=None)

    # Act / Assert
    assert _assess(_fingerprint(), live, recorded="2.7.0")[0] is Staleness.DEFINITELY_STALE


def test_live_evidence_is_exactly_a_fingerprint_or_a_reason_never_both_or_neither() -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="exactly one"):
        LiveEvidence(fingerprint=None, unresolved=None)
    with pytest.raises(ValueError, match="exactly one"):
        LiveEvidence(fingerprint=_fingerprint(), unresolved="why")
