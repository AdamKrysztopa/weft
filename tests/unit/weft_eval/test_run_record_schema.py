"""A run record says which record schema wrote it — carried repair **R20.4**.

Found at `20.12`'s control by running the binary: `RunRecord` is `extra="forbid"`, a field added
without a version move made every record a newer weft wrote unreadable to an older one, and the
first such record ended the whole directory read with pydantic's `extra_forbidden` while both wheels
said `weft 3.1.0`. The owner settled the rule on 2026-10-07: an integer record `schema`, moved by
every field addition and independent of the distribution version, checked before anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.unit.weft_eval.test_evidence import complete_records, fixture_experiment
from weft_eval.run_record import (
    RUN_RECORD_SCHEMA_VERSION,
    NewerRunRecordError,
    load_run_record,
    read_run_records,
    write_run_record,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def _committed_record() -> Path:
    return sorted(REPO_ROOT.glob("eval/experiments/*/runs/*.json"))[0]


def _newer(tmp_path: Path, name: str) -> Path:
    record = complete_records(fixture_experiment(tmp_path))[0]
    body = json.loads(record.model_dump_json())
    body["schema_version"] = RUN_RECORD_SCHEMA_VERSION + 1
    body["distribution_versions"] = {"weft-rag": "9.0.0"}
    body["from_the_future"] = True
    path = tmp_path / "runs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_a_written_record_states_the_current_schema(tmp_path: Path) -> None:
    # Arrange
    record = complete_records(fixture_experiment(tmp_path))[0]

    # Act
    path = write_run_record(record, tmp_path / "runs" / "one.json")

    # Assert
    assert (
        json.loads(path.read_text(encoding="utf-8"))["schema_version"] == RUN_RECORD_SCHEMA_VERSION
    )
    assert RUN_RECORD_SCHEMA_VERSION >= 2


def test_a_record_written_before_the_schema_existed_reads_as_the_first() -> None:
    # Arrange
    path = _committed_record()
    assert "schema_version" not in json.loads(path.read_text(encoding="utf-8"))

    # Act
    record = load_run_record(path)

    # Assert
    assert record.schema_version == 1


def test_a_newer_record_is_refused_naming_its_schema_its_writer_and_what_it_does_not_know(
    tmp_path: Path,
) -> None:
    # Arrange
    path = _newer(tmp_path, "newer.json")

    # Act
    with pytest.raises(NewerRunRecordError) as refusal:
        load_run_record(path)

    # Assert
    message = str(refusal.value)
    assert str(path) in message
    assert f"record schema {RUN_RECORD_SCHEMA_VERSION + 1}" in message
    assert "weft-rag 9.0.0" in message
    assert "from_the_future" in message


def test_a_directory_read_keeps_the_records_beside_a_newer_one(tmp_path: Path) -> None:
    # Arrange
    records = complete_records(fixture_experiment(tmp_path))
    for index, record in enumerate(records):
        write_run_record(record, tmp_path / "runs" / f"run-{index}.json")
    newer = _newer(tmp_path, "run-newer.json")

    # Act
    read = read_run_records(tmp_path / "runs")

    # Assert
    assert len(read.records) == len(records)
    assert len(read.unread) == 1
    assert str(newer) in read.unread[0]
