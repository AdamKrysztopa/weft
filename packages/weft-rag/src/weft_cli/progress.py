"""`weft index`'s per-batch progress — ledger task **43.2**.

`BatchProgress` is one batch's line; its `kind` joins the `--json` stream's `LineKind` vocabulary
additively. `ProgressReporter` is checked structurally at `IndexCommand.run`, never added to
`weft_llm.contract.TokenSink`, so a caller-supplied sink without it gets no progress and no
published contract moves.
"""

from __future__ import annotations

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


__all__ = ["BatchProgress", "ProgressReporter"]
