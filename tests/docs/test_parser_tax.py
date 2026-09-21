"""`eval/parser-tax/` regenerates from what the tree commits — ledger **38.8**.

The paired differences are recomputed from the two experiments' committed records, and the table
from the measurement JSON, and neither may move by a byte. The quote counts are read from the two
databases the experiments indexed, which the tree does not carry, so they are checked only through
the table.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest
from parser_tax import Measurement, pairs, table

_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_EXPERIMENTS: Final[Path] = _ROOT / "eval" / "experiments"
_MEASURED: Final[Path] = _ROOT / "eval" / "parser-tax"


def _measurement() -> Measurement:
    return Measurement.model_validate_json(
        (_MEASURED / "measurement.json").read_text(encoding="utf-8")
    )


def test_the_table_regenerates_byte_identical_from_the_measurement() -> None:
    # Act / Assert
    assert table(_measurement()) == (_MEASURED / "table.md").read_text(encoding="utf-8")


# The bootstrap runs 2,000 resamples per metric over 1,548 questions, twelve times.
@pytest.mark.timeout(180)
def test_every_paired_difference_regenerates_from_the_committed_records() -> None:
    # Act
    regenerated = pairs(
        _EXPERIMENTS / "orb-parser-tax-markdown" / "runs",
        _EXPERIMENTS / "orb-parser-tax-pdf" / "runs",
    )

    # Assert
    assert regenerated == _measurement().pairs
