"""`eval/pool-promotion/*-ceilings.json` are held to the records they claim — ledger **40.4**.

The ceilings are computed off a pool manifest kept outside version control (sixteen megabytes each,
under the ignored `corpus/pools/`), so this cannot recompute them. What it holds is the half that
rots: each file names the capture record it read, that record is committed beside it, and the dense
reciprocal rank every gain is measured from is the record's own, over the same questions. And the
number Phase 41 turns on — ESCI's oracle ceiling against `05` → G26's 0.05 — is asserted where it
is stated, so a regenerated file that crossed it cannot pass quietly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

import pytest

_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "eval" / "pool-promotion"
_TOLERANCE: Final[float] = 5e-4
_PHASE_41_OPENS_AT: Final[float] = 0.05


def _read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize(("corpus", "questions"), [("esci", 830), ("techqa", 610)])
def test_each_ceiling_file_is_over_the_record_it_names_and_every_question_in_it(
    corpus: str, questions: int
) -> None:
    # Arrange
    ceilings = _read(_ROOT / f"{corpus}-ceilings.json")
    record = _read(_ROOT / "runs" / f"{ceilings['record']}.json")

    # Act
    recorded = record["metrics"]["mrr@5"]["value"]
    stated = ceilings["slices"]["all"]

    # Assert
    assert record["experiment"]["arm"] == ceilings["arm"] == "dense"
    assert stated["n"] == recorded["n"] == questions
    assert abs(stated["mrr5"] - recorded["mean"]) <= _TOLERANCE
    assert len(ceilings["questions"]) == questions
    assert ceilings["excluded"] == []


def test_the_esci_oracle_ceiling_is_the_one_phase_41_opens_on() -> None:
    # Act
    oracle = _read(_ROOT / "esci-ceilings.json")["slices"]["all"]["oracle_ceiling"]

    # Assert
    assert oracle >= _PHASE_41_OPENS_AT
