"""Every committed evidence table regenerates from its committed records — ledger task **38.1**.

An experiment committed under `eval/experiments/<name>.toml` with a table at
`eval/experiments/<name>/table.md` commits the records that table was generated from under
`eval/experiments/<name>/runs/`. This check regenerates the table from those records and refuses one
byte of difference, so a cell edited by hand, a record dropped, or a renderer change that moves a
published number all fail here rather than going unnoticed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from weft_eval.evidence import regenerate

_EXPERIMENTS: Final[Path] = Path(__file__).resolve().parents[2] / "eval" / "experiments"


def committed_tables(root: Path) -> list[tuple[Path, Path, Path]]:
    """`(document, runs directory, table)` for each experiment under `root` committing a table."""
    return [
        (document, document.with_suffix("") / "runs", document.with_suffix("") / "table.md")
        for document in sorted(root.glob("*.toml"))
        if (document.with_suffix("") / "table.md").is_file()
    ]


def stale_tables(root: Path) -> list[str]:
    return [
        document.name
        for document, runs, table in committed_tables(root)
        if regenerate(document, runs) != table.read_text(encoding="utf-8")
    ]


_COMMITTED: Final[list[tuple[Path, Path, Path]]] = committed_tables(_EXPERIMENTS)


def test_committed_tables_are_found() -> None:
    """Without this, an empty glob would parametrize the check below into nothing."""
    assert _COMMITTED


# One case per table: as one test, fifteen took 38.5 s locally and over 60 s on CI (36549412501).
@pytest.mark.parametrize(
    ("document", "runs", "table"), _COMMITTED, ids=[document.name for document, _, _ in _COMMITTED]
)
def test_every_committed_table_regenerates_byte_identical_from_its_records(
    document: Path, runs: Path, table: Path
) -> None:
    # Act
    regenerated = regenerate(document, runs)

    # Assert
    assert regenerated == table.read_text(encoding="utf-8"), f"{document.name} is stale"


def test_the_check_can_actually_fail(tmp_path: Path) -> None:
    """A table with one cell edited by hand is reported, and the unedited one is not."""
    from tests.unit.weft_eval.test_evidence import complete_records, fixture_experiment
    from weft_eval.run_record import write_run_record

    # Arrange
    root = tmp_path / "experiments"
    root.mkdir()
    experiment = fixture_experiment(root)
    runs = root / "experiment" / "runs"
    for index, record in enumerate(complete_records(experiment)):
        write_run_record(record, runs / f"run-{index}.json")
    table = root / "experiment" / "table.md"
    table.write_text(regenerate(root / "experiment.toml", runs), encoding="utf-8")
    assert committed_tables(root)
    assert stale_tables(root) == []

    # Act
    table.write_text(
        table.read_text(encoding="utf-8").replace("+0.250", "+0.300"), encoding="utf-8"
    )

    # Assert
    assert stale_tables(root) == ["experiment.toml"]
