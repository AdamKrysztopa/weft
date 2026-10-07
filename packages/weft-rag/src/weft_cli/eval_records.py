"""Where an experiment's records live, and what is said when none are there — repairs R20.3, R20.5.

`weft eval experiment` writes to `<document>/runs` — the document's path without its suffix — and
`weft eval table`, `replay` and `pairwise` read from there, so a writer and its readers agree with
both defaulted. A weft before `R20.5` wrote to `DEFAULT_RUNS_DIR` relative to the directory it ran
from; a reader that quietly fell back to that directory could print a table from records nobody
meant, so the refusal says where it looked and, when that directory holds this experiment's
records, which `--runs` reads them.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from weft_cli.eval_commands import DEFAULT_RUNS_DIR
from weft_eval.evidence import IncompleteExperimentError
from weft_eval.experiment import Experiment
from weft_eval.run_record import RunRecord, load_run_record


def experiment_runs_dir(experiment_path: Path, runs: str | None) -> Path:
    """The `--runs` the operator gave, or `<document>/runs` beside the document."""
    return Path(runs) if runs is not None else experiment_path.with_suffix("") / "runs"


def records_of_experiment(
    experiment: Experiment, experiment_path: Path, runs: str | None
) -> list[RunRecord]:
    """The records in the chosen runs directory, refusing when none belong to `experiment`.

    Args:
        experiment: The loaded experiment document.
        experiment_path: Where it was read from; the default runs directory sits beside it.
        runs: The `--runs` the operator gave, or `None` for `<document>/runs`.

    Returns:
        Every record read from the directory, in file-name order.

    Raises:
        IncompleteExperimentError: no record read belongs to this experiment's digest, naming
            the directory searched.
    """
    runs_dir = experiment_runs_dir(experiment_path, runs)
    records = _read_records(runs_dir, strict=True)
    if any(_is_of(record, experiment) for record in records):
        return records
    message = (
        f"no records of experiment '{experiment.name}' ({experiment.digest[:12]}…) "
        f"were found under '{runs_dir}'"
    )
    if runs is None and runs_dir.resolve() != DEFAULT_RUNS_DIR.resolve():
        elsewhere = sum(
            _is_of(record, experiment) for record in _read_records(DEFAULT_RUNS_DIR, strict=False)
        )
        if elsewhere:
            message += (
                f"; '{DEFAULT_RUNS_DIR}' holds {elsewhere} record(s) of it, where an earlier "
                f"weft wrote them relative to the directory it ran from — pass "
                f"`--runs {DEFAULT_RUNS_DIR}`"
            )
    raise IncompleteExperimentError(message + ".")


def _is_of(record: RunRecord, experiment: Experiment) -> bool:
    return record.experiment is not None and record.experiment.digest == experiment.digest


def _read_records(directory: Path, *, strict: bool) -> list[RunRecord]:
    if not directory.is_dir():
        return []
    records: list[RunRecord] = []
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(load_run_record(path))
        except ValidationError:
            if strict:
                raise
    return records
