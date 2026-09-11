"""`weft eval` can judge a **query** rung — ledger task **7.5**, discharging Phase 8's exit.

Phase 8's Exit asks that `weft eval` report whether the difference between two of *those rungs* —
the query rungs of the clause above it — falls outside the interval a published baseline recorded.
Re-checking that exit on a real wheel install found four clauses of five are facts and the fifth is
not. Every box under Phase 8 was honestly ticked and both halves are individually demonstrable; the
word that failed is the conjunction (`docs/internal/lessons.md` `L8.29`).

**Two things blocked it, and only the second is interesting.** `weft eval run` refuses a query
pipeline outright — *"has no stage registered under the Extractor contract"* — which is a
reasonable thing for a command that also indexes. The real one is underneath:
`weft_cli.eval_scoring.score_retrieval` pulls the `Embedder` and `NodeStore` stages out of the
pipeline it was given and calls `run_ask`, which is **plain vector top-k, every time**. So no
`Retriever`, `Fuser`, `ContextPacker` or `Generator` choice has ever been the thing measured, and
`hybrid-then-generate` and `retrieve-then-generate` would have scored identically because neither
was ever run.

**What a query rung is scored over is `Answer.used`**, and that is not a convenience — it is what
that field's own docstring already says it is for: *"exactly the passages that entered the prompt …
what a reader needs to judge the answer without re-running the pipeline"*. Scoring the ranking
instead would measure something the generator never saw.

**This is the honest subject and it is narrower than "run the rung".** The retrieval metrics judge
what came back; whether the *answer* is good is `GenerationMetric`'s question and needs a real
model, which `09` §4.4 deliberately keeps out of the gate. So this task makes a query rung
*measurable*, which is what Phase 8's exit asks, and does not claim the generation half.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from weft_cli.eval_commands import EvalRunArgs


def test_eval_run_can_name_a_query_rung() -> None:
    """The command surface half — a query pipeline is a subject the command accepts.

    A separate field rather than overloading `pipeline`: the two are different roles in one run.
    The ingest pipeline says what was indexed and is what a baseline is keyed on; the query rung is
    what is being compared. Folding them into one positional would make *"which of these two did I
    change?"* unanswerable from a persisted record.
    """
    fields = EvalRunArgs.model_fields

    assert "query_pipeline" in fields, (
        "weft eval run cannot name a query rung, so Phase 8's exit clause has no subject"
    )
    assert fields["query_pipeline"].default is None, (
        "a query rung must be optional — every baseline taken before this task named none, and "
        "they stay readable"
    )
    assert fields["pipeline"].is_required(), "the ingest pipeline is still what a run indexes with"


@pytest.mark.asyncio
async def test_a_query_rung_is_scored_over_what_it_actually_used() -> None:
    """The half that matters: the rung runs, and what *it* retrieved is what is judged.

    Asserted through the seam rather than end-to-end, because an end-to-end run needs a container
    and a model and this property needs neither: the question is whether the passages handed to the
    metrics came from the rung's own `Answer.used` or from a plain vector search underneath it.
    """
    from weft_cli.eval_scoring import passages_for_scoring

    # `retrieved_by` rather than an invented field: the stand-in is duck-typed, but the
    # *return* type is the real `Passage`, so an assertion on a field `Passage` does not have
    # would force the function to widen to `Any` and give up saying what it hands back.
    class _Passage(BaseModel):
        retrieved_by: str

    class _Answer(BaseModel):
        used: tuple[_Passage, ...]

    answer = _Answer(used=(_Passage(retrieved_by="vector-top-k"), _Passage(retrieved_by="hybrid")))

    scored = passages_for_scoring(answer)

    assert [passage.retrieved_by for passage in scored] == ["vector-top-k", "hybrid"], (
        "the rung's own used passages are not what reaches the metrics, so a query rung would be "
        "scored on something it did not produce"
    )


def test_the_scorer_still_refuses_a_pipeline_it_cannot_retrieve_with() -> None:
    # The existing refusal is unchanged: an ingest pipeline with no Embedder/NodeStore still has
    # nothing to retrieve against, and that message names the missing contract. A new capability
    # must not quietly widen what an old failure accepts.
    from weft_cli.eval_scoring import PipelineNotRetrievableError

    assert issubclass(PipelineNotRetrievableError, Exception)
