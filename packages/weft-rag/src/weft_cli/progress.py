"""`weft index`'s per-batch progress, and `weft eval experiment`'s own — tasks **43.2**/**R43.58**.

`BatchProgress` is one batch's line; its `kind` joins the `--json` stream's `LineKind` vocabulary
additively. `ProgressReporter` is checked structurally at `IndexCommand.run`, never added to
`weft_llm.contract.TokenSink`, so a caller-supplied sink without it gets no progress and no
published contract moves.

**Carried repair R43.58.** 43.53's paid run wrote no line for 25 minutes and was watched
through open sockets (`docs/internal/lessons.md` `L28.66`) — `weft eval experiment` had nothing
that reported while it ran. `ScoringProgress` is one question-scoring stage's own counted
progress, `ExperimentProgress` is that same event labelled with which arm and repetition it
belongs to, and `ExperimentProgressReporter` is a **separate** Protocol from `ProgressReporter`
rather than a second method on it — adding a method to `ProgressReporter` would stop every
existing sink that implements only `batch_progress` from matching it, the identical reasoning
`ProgressReporter` itself gives for staying off `weft_llm.contract.TokenSink`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_cli.sinks import LineKind


class BatchProgress(BaseModel):
    """One batch's worth of `weft index` progress.

    What `ProgressReporter.batch_progress` receives, and what a `--json` reader sees as one
    `batch-progress` line.

    `queryable` is how many documents this run has recorded `ACTIVE` so far, cumulative
    across every batch this run has already finished; `documents` is the whole corpus this
    run works on, unchanged batch to batch, so a reader can compute a fraction from either
    field alone. `whole_corpus_for` is empty unless a stage in this run's own pipeline
    depends on which other nodes shared its batch (`weft_cli.ingest.
    batch_membership_dependent_stages`) — non-empty only when the default kept the whole
    corpus in one batch to protect that stage, naming it by plugin name.

    `bytes` — ledger task **43.1** — is this batch's files' combined size, read off the
    `SourceRef`s inventoried for it rather than the loaded bytes, so it is known before the
    batch is loaded at all. `0` for a batch this run never measured (`whole_corpus_for`'s own
    footing does not zero it; an empty `work` batch simply is never emitted at all — see
    `weft_cli.ingest._emit_batch_progress`), which is what lets a reader carrying a huge
    document see the batch it slowed down.

    `layer` — ledger task **43.8** — names the layer this event's batch belongs to, `None`
    for a base-run event exactly as every event was before layers existed. `batch`/`batches`
    then count that layer's own batches, `queryable` the sources whose record now carries
    this layer `ACTIVE` (cumulative), and `documents` the sources eligible for it — never the
    whole corpus, which `weft_cli.ingest._run_layers`'s own docstring states in full.
    """

    model_config = ConfigDict(frozen=True)

    kind: LineKind = LineKind.BATCH_PROGRESS
    batch: int
    batches: int
    queryable: int
    documents: int
    seconds: float
    whole_corpus_for: tuple[str, ...] = ()
    bytes: int = 0
    layer: str | None = None


@runtime_checkable
class ProgressReporter(Protocol):
    """A token sink that can also receive `weft index`'s per-batch progress.

    Checked structurally with `isinstance`, never declared: `weft_llm.contract.TokenSink`
    stays exactly as every third-party provider already implements it, and a sink that adds
    `batch_progress` opts into progress lines without the base contract ever naming this
    Protocol.
    """

    async def batch_progress(self, event: BatchProgress) -> None:
        """Receive the progress of one batch `weft index` just finished.

        Args:
            event: The batch's progress.
        """


class ScoringStage(StrEnum):
    """Which half of one question `weft_cli.eval_scoring.score_pipeline` is doing — R43.58."""

    ANSWERING = "answering"
    JUDGING = "judging"


class ScoringProgress(BaseModel):
    """One stage's own counted progress inside `score_pipeline` — carried repair **R43.58**.

    `done`/`total` count questions attempted while `stage` is `ANSWERING`, and generation
    samples judged while it is `JUDGING` — see `score_pipeline`'s own docstring for the exact
    emission rule. This is the event `on_progress` receives; `weft_cli.eval_experiment._run_arms`
    is what labels one of these with an arm and a repetition to build an `ExperimentProgress`.
    """

    model_config = ConfigDict(frozen=True)

    stage: ScoringStage
    done: int
    total: int


class ExperimentProgress(BaseModel):
    """One arm-repetition's `ScoringProgress`, labelled for `weft eval experiment` — R43.58.

    `arm_number`/`arms` are 1-based and in the experiment document's own arm order;
    `repetition`/`repetitions` are 1-based, `repetitions` being `Experiment.repeats_for(arm)`.
    `seconds` is monotonic seconds since this arm-repetition's own `index_and_score` call began,
    not since the whole experiment started — the figure a reader watching one arm stall actually
    wants.
    """

    model_config = ConfigDict(frozen=True)

    kind: LineKind = LineKind.EXPERIMENT_PROGRESS
    experiment: str
    arm: str
    arm_number: int
    arms: int
    repetition: int
    repetitions: int
    stage: ScoringStage
    done: int
    total: int
    seconds: float


@runtime_checkable
class ExperimentProgressReporter(Protocol):
    """A token sink that can also receive `weft eval experiment`'s own progress — R43.58.

    Checked structurally, on the identical footing `ProgressReporter` is — a **separate**
    Protocol, not a second method on `ProgressReporter`: see the module docstring's own
    paragraph for why folding the two would stop every sink implementing only one of them from
    matching either.
    """

    async def experiment_progress(self, event: ExperimentProgress) -> None:
        """Receive one arm-repetition's own labelled scoring progress.

        Args:
            event: The labelled progress.
        """


__all__ = [
    "BatchProgress",
    "ExperimentProgress",
    "ExperimentProgressReporter",
    "ProgressReporter",
    "ScoringProgress",
    "ScoringStage",
]
