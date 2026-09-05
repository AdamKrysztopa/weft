"""`graded-retrieval` — grades each retrieved passage against the question, batched and
capped, and keeps only the ones that clear a configured floor. `Reranker`.

Task **2.21a**, `docs/build-ledger.md`'s 2.21 line: "per-document relevance grading is a
reusable post-retrieval filter." `docs/10-technique-catalogue.md` §1.1's own `corrective` row
states the naming condition this module exists to satisfy without violating: "`corrective` is
only honest if the plugin gains a *distinct knowledge action* ... If Weft ships that
behaviour unchanged, the name is `graded-retrieval` and the word `corrective` stays free for a
plugin that earns it." This module *is* that unchanged behaviour, corrected — grade every hit,
discard the failures — and it registers under `Reranker`, the same open position `llm-rerank`
already fills, so any pipeline with a `Ranking` can filter through it whether or not anything
downstream ever reaches a second retriever. `weft_retrieve.corrective` is the plugin that
earns the other name, by calling this one and then doing something a same-index retry cannot.

Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*,
arXiv:2401.15884, 2024 — §3.1's retrieval evaluator is the per-document grading step this
plugin implements, cited again here (beside `weft_retrieve.prompts.RelevanceGradePrompt`,
which cites it for the question it asks) for what this module does with the answer. **Cited
as the origin of the grading mechanism, not as a claim this module *is* CRAG**: the paper's
evaluator also drives a three-way action (Correct / Incorrect / Ambiguous) this plugin does
not decide at all — it grades and filters, full stop, and `corrective.py` is where a distinct
action is added on top.

**Batched, and capped — two costs fixed by construction.** `10` §1.1's row: grading whole
nodes with a prompted LLM means one call per chunk, up to ~30 per query, uncapped, absent
these two limits. `max_graded` (default 20) is the hard ceiling on how many of the ranking's
own hits are ever offered to a model at all, and `batch` (default 5) is how many are asked
about per call — `ceil(max_graded / batch)` calls at the ceiling, which is what makes
`cost_bound`'s `(1, 4)` a fact an operator can check against the two numbers next to it rather
than a claim. **A hit ranked at or beyond `max_graded` is not graded and does not survive this
stage** — grading fewer than arrived and keeping the ungraded tail anyway would mean this
filter vouches for passages it never looked at, the exact silent half-measure
`weft_retrieve.rerank`'s own "not one per offered passage is refused" rule exists to keep out
of the reranking position generally.

**`on_grader_failure` fabricates nothing.** `10` §1.1's row names a defect this avoids:
fabricating a grade from word overlap when the grader fails. `OnFailure.FAIL` (published by
`weft-llm`, not invented here — see that field's own docstring) relays a batch's own failure
outcome; a batch that could not be graded is never read as "keep everything in it" or "drop
everything in it", either of which would be a grade this module never actually asked for.

**The threshold is a named grade, not a float.** `Grade` and its order (`weft_retrieve.
prompts.GRADE_ORDER`) are what make `keep_at_or_above` a decision an operator reads rather
than a tuning constant `10` §2.1 rules out — see `Grade`'s own docstring for why a continuous
cut-off does not belong on this axis the way it does on `llm-rerank`'s.

**Filters, and does not reorder.** `10` §1.1's own words for this row are "grades ... discards
the failures" — a filter, not a second ranking. The surviving hits keep the relative order
`payload` handed them, with `rank` renumbered to stay contiguous over what actually survived
— the same renumbering `weft_retrieve.repack`'s own packer does for its own output, applied
here because a `rank` with gaps in it is a fact about this stage's internals leaking into a
type nothing downstream should have to parse holes out of.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_llm.payload import OnFailure
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Ranking
from weft_retrieve.prompts import (
    GRADE_ORDER,
    RELEVANCE_GRADE_NAME,
    Grade,
    GradedPassages,
    PassageGradeRequest,
)

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "graded-retrieval"


class GradedRetrievalConfig(BaseModel):
    """`GradedRetrieval`'s `with:` config. Every field has a default, per this pack's own
    rule. Every knob a hard-coded or absent version of this technique would fix in place is
    one of these: which
    wording grades (`prompt`), which model answers (`role`), where the line is drawn
    (`keep_at_or_above`), how many hits are ever offered (`max_graded`), how many per call
    (`batch`), and what a batch that could not be graded does (`on_grader_failure`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=RELEVANCE_GRADE_NAME, min_length=1)
    role: str = Field(default="grade", min_length=1)
    keep_at_or_above: Grade = Grade.RELEVANT
    #: Uncapped runs to ~30 calls per query (`10` §1.1's row). This is the hard
    #: ceiling on how many of `payload.hits` are ever graded at all — see the module
    #: docstring for what happens to a hit ranked beyond it.
    max_graded: int = Field(default=20, ge=1)
    batch: int = Field(default=5, ge=1)
    on_grader_failure: OnFailure = OnFailure.FAIL


class GradedRetrieval:
    """Grades every offered hit, batched, and keeps only the ones at or above a floor.
    Satisfies `weft_retrieve.contract.Reranker` structurally.

    `cost_bound = (1, 4)` at the defaults: `ceil(20 / 5) = 4` batches at the ceiling, one
    batch at the floor — matching `.phase2-design.md` §10's own arithmetic for this row.
    **Recorded here, because the design table does not address it**: an empty `Ranking`
    short-circuits below that declared floor, at zero calls, the same emptiness rule
    `weft_retrieve.rerank.LlmRerank` already established for the identical case — there is
    nothing to offer a model, and asking it to grade a batch of zero hits is not a request
    that means anything. The floor of one describes the case grading actually runs, the same
    reading `weft_retrieve.iterative`'s own `(1, -1)` gives "a round always costs at least
    the critic's own call" for a loop that, unlike this reranker, can never legitimately be
    handed nothing to do.
    """

    config_model: ClassVar[type[GradedRetrievalConfig]] = GradedRetrievalConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 4)

    def __init__(self, config: GradedRetrievalConfig | None = None) -> None:
        self._config = config if config is not None else GradedRetrievalConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Every hit up to `max_graded`, graded in batches of `batch`, filtered by grade.

        `out.origin == in.origin` holds by construction: the `Ranking` returned below is
        always built with `payload.origin`, never a derived query — the obligation every
        query-path plugin in this pack carries (`weft_retrieve.payload.QuerySet.origin`'s
        own docstring, restated on `Ranking` by inheritance of the same field).
        """
        if not payload.hits:
            return Produced(value=payload)

        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        floor = GRADE_ORDER.index(self._config.keep_at_or_above)

        offered = payload.hits[: self._config.max_graded]
        kept: list[Passage] = []
        for start in range(0, len(offered), self._config.batch):
            chunk = offered[start : start + self._config.batch]
            values = PassageGradeRequest(question=payload.origin.text, passages=_offer(chunk))
            judged = await execute(
                llm=llm,
                prompt=prompt,
                values=values,
                output=GradedPassages,
                role=self._config.role,
                ctx=ctx,
            )
            if not isinstance(judged, Produced):
                # `on_grader_failure` has one member today (FAIL): relaying the batch's own
                # outcome *is* failing loudly — a partially graded ranking would silently
                # decide what happens to the ungraded remainder, which is exactly the
                # fabricated-grade defect this plugin exists to refuse. See the module
                # docstring.
                return judged
            graded = _grades_by_index(judged.value.value, offered=len(chunk))
            if isinstance(graded, Failed):
                return graded
            kept.extend(
                passage
                for index, passage in enumerate(chunk)
                if GRADE_ORDER.index(graded[index]) >= floor
            )

        hits = tuple(_kept(passage, rank) for rank, passage in enumerate(kept))
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=hits,
                contributors=payload.contributors,
                ext=payload.ext,
            )
        )


def _offer(chunk: tuple[Passage, ...]) -> str:
    """One batch's candidates, one per line, numbered from `0` within *this* batch.

    Local to each call, the same numbering `weft_retrieve.rerank._offer` uses for its single
    unbatched call — `_grades_by_index` reads the identical numbers back per batch, so a
    later batch's index `0` never collides with an earlier one's.
    """
    return "\n".join(f"[{index}] {passage.node.content}" for index, passage in enumerate(chunk))


def _grades_by_index(judged: GradedPassages, *, offered: int) -> dict[int, Grade] | Failed:
    """One grade per offered index in this batch, or a `Failed` naming exactly how it was
    wrong. Mirrors `weft_retrieve.rerank._scores_by_index` — an index nobody offered, a
    missing index, and a repeated index are three different mistakes, each named rather than
    folded into one "the model answered badly".
    """
    grades: dict[int, Grade] = {}
    unknown: list[int] = []
    repeated: list[int] = []
    for grade in judged.grades:
        if grade.index >= offered:
            unknown.append(grade.index)
        elif grade.index in grades:
            repeated.append(grade.index)
        else:
            grades[grade.index] = grade.grade
    missing = [index for index in range(offered) if index not in grades]
    if unknown or repeated or missing:
        return Failed(
            reason=(
                f"'{NAME}' offered {offered} passage(s) in this batch and asked for one "
                f"grade each, and the model did not answer that: index/indices "
                f"{unknown or 'none'} were never offered, {repeated or 'none'} were graded "
                f"more than once, and {missing or 'none'} were not graded at all. Filtering "
                f"on a partial answer would keep or drop a passage nobody actually judged."
            )
        )
    return grades


def _kept(passage: Passage, rank: int) -> Passage:
    """`passage`, kept exactly as graded, at its new contiguous position among survivors.

    Nothing about the passage itself changes — this stage filters, it does not rescore, so
    the score a caller reads afterwards is still whichever retriever or reranker actually
    produced it. Only `rank` moves, for the reason the module docstring states.
    """
    return Passage(
        scored=passage.scored, rank=rank, retrieved_by=passage.retrieved_by, label=passage.label
    )
