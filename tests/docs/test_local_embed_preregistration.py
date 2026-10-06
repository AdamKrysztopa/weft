"""Phase 20b's measurement is fixed in writing before any run — ledger task **20.8b**.

`local-embed-{techqa,esci,orb}.toml` pre-register a `[decision]` whose margin was set from a blinded
pilot (`fix-plans/29` O8, O11) before any record of them existed, and `local-embed-servers.toml`
states its two-sided gap rule. A record carries its document's digest, so a margin moved after the
run would orphan the records; this pins the digests and the decisions so that moving one before the
run is also a visible edit here, never a quiet one. The committed tables are held to the records by
`test_evidence_tables.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from weft_eval.experiment import load_experiment

_EXPERIMENTS: Final[Path] = Path(__file__).resolve().parents[2] / "eval" / "experiments"

#: Digest, arm names in order, and `(metric, margin, direction)` or `None`, as fixed at 20.8b.
_FIXED: Final[dict[str, tuple[str, tuple[str, ...], tuple[str, float, str] | None]]] = {
    "local-embed-techqa": (
        "5f368d30124bab04cb8ff0217d9d7d6f935e3b6f0e1ba86b95d6c38ec0778704",
        ("bge-m3", "openai-large"),
        ("mrr@5", 0.04, "higher-is-better"),
    ),
    "local-embed-esci": (
        "abe5c8a720260b55d55a41f1d94cb0d0dced36c74ae47d46e149347009fa985e",
        ("bge-m3", "openai-large"),
        ("mrr@5", 0.04, "higher-is-better"),
    ),
    "local-embed-orb": (
        "8a0eb3dfdcb220c84310ca1a29c38533be15c7113bf71c13f023148acfee06fc",
        ("bge-m3", "openai-large"),
        ("mrr@5", 0.04, "higher-is-better"),
    ),
    "local-embed-servers": (
        "7edb4f2bf5f1d3abb6ead008a38e74000aae5d289257d23e88c05daecb3057cf",
        ("ollama", "tei"),
        None,
    ),
}


@pytest.mark.parametrize("name", sorted(_FIXED))
def test_the_pre_registered_document_is_unchanged(name: str) -> None:
    # Arrange
    digest, arms, decision = _FIXED[name]

    # Act
    experiment = load_experiment(_EXPERIMENTS / f"{name}.toml")

    # Assert
    assert experiment.digest == digest, f"{name}.toml changed after 20.8b fixed it"
    assert tuple(arm.name for arm in experiment.arms) == arms
    if decision is None:
        assert experiment.decision is None
    else:
        assert experiment.decision is not None
        metric, margin, direction = decision
        assert experiment.decision.metric == metric
        assert experiment.decision.margin == margin
        assert experiment.decision.direction.value == direction
