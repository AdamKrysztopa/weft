"""A position-swapped pairwise judge for answers with no single gold — task **44.43a**.

**Provenance, and where this diverges.** The three criteria and the control are GraphRAG's own
head-to-head evaluation (Edge et al., "From Local to Global: A Graph RAG Approach to
Query-Focused Summarization", arXiv:2404.16130): `comprehensiveness`, `diversity` and
`empowerment` are the paper's own three targets, and `directness` is carried in as a control the
paper itself uses to check that a judge is not simply rewarding length. Everything past the
criteria **diverges**. The paper repeats each comparison five times and averages the votes; this
module asks its judge once in each order and treats a verdict that changes between the two
orders as a tie — the position-bias safeguard Zheng et al. describe ("Judging LLM-as-a-Judge
with MT-Bench and Chatbot Arena", NeurIPS 2023, §3.3), cheaper than five repeats and aimed at the
one failure mode five repeats does not target on its own: a judge that reliably prefers whichever
answer it reads first. And the paper reports significance with a Wilcoxon signed-rank test; this
module instead carries a paired bootstrap interval over questions, `weft_eval.falsify.
paired_interval`'s own basis, so a pairwise win rate reads against the identical interval
convention every other comparison in this pack already uses.

**Why a pairwise judge at all.** A corpus-wide question — "what themes recur across the
collection" — has no single reference answer two arms can be scored against, so there is nothing
for `weft_eval.contract.GenerationSample.reference` to hold and no `GenerationMetric` here can
compare them. A pairwise judge sidesteps that entirely: two arms' own answers, read head to
head, on one named criterion at a time, never against a reference neither arm was given.

**`Preference` is the caller's own frame (`A`/`B`/`TIE`); `Position` is the judge's own
(`weft_eval.prompts.Position`, `FIRST`/`SECOND`/`TIE`).** `judge_pair` shows the two answers once
in each order, so the judge itself never learns which caller-side arm it is reading — only which
position it preferred — and `reconcile` is what turns the two `Position` answers back into one
`Preference` the caller can act on.
"""

from collections.abc import Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from weft_eval.evidence import select_invocation
from weft_eval.experiment import Experiment
from weft_eval.falsify import UnpairableRecordsError, paired_interval, pairing_reasons
from weft_eval.prompts import (
    PAIRWISE_JUDGE_PROMPT_NAME,
    PairwiseChoice,
    PairwiseJudgePrompt,
    PairwiseJudgeRequest,
    Position,
)
from weft_eval.run_record import RunRecord
from weft_kernel.context import Context
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt


class UnknownArmError(WeftError, UnresolvedNameError):
    """`compare_arms` was asked to judge a baseline or arm the experiment does not declare.

    FF12's family: `valid_options` names every arm the experiment's own document declares, in
    document order — checked, and raised, before `compare_arms` reads a single record or makes a
    single model call (task **44.43b**).
    """

    def __init__(self, message: str, *, arm: str, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.arm = arm
        self.valid_options = valid_options


class UnrecordedAnswersError(WeftError):
    """`compare_arms` found a repetition-1 record with no `question_answers` at all.

    A record `44.43a` did not write — the judge only ever reads answer text an experiment run
    already recorded, and a record written before `RunRecord.question_answers` existed carries
    none to read. Not a name-resolution failure — there is no alternative to offer, only a rerun
    — so this stays plain `WeftError`, `OPERATION_FAILED` rather than FF12's family.
    """

    def __init__(self, message: str, *, arm: str) -> None:
        super().__init__(message)
        self.arm = arm


class PairwiseCriterion(StrEnum):
    """GraphRAG's own three head-to-head targets, plus `directness` as a control.

    See the module docstring for provenance and for what a pairwise judge diverges from the
    paper on.
    """

    COMPREHENSIVENESS = "comprehensiveness"
    DIVERSITY = "diversity"
    EMPOWERMENT = "empowerment"
    DIRECTNESS = "directness"


class Preference(StrEnum):
    """One question's own head-to-head verdict, in the caller's frame — never the judge's own.

    `A`/`B` name the two arms exactly as `judge_pair`'s own `answer_a`/`answer_b` named them;
    `TIE` is both "the judge found no difference" and "the judge's verdict changed with the
    order it read the answers in" — `reconcile` never distinguishes the two, because a caller
    acting on a win rate has no use for which kind of tie it was.
    """

    A = "a"
    B = "b"
    TIE = "tie"


#: Each criterion's own plain-language definition, put to the judge as the `criterion_definition`
#: value — written for Weft, not transcribed from GraphRAG's own prompt or criteria text.
CRITERION_DEFINITIONS: Mapping[PairwiseCriterion, str] = {
    PairwiseCriterion.COMPREHENSIVENESS: "how fully the answer covers what the question asks",
    PairwiseCriterion.DIVERSITY: "how many distinct angles or sources the answer brings",
    PairwiseCriterion.EMPOWERMENT: (
        "how well the answer equips the reader to judge the topic for themselves"
    ),
    PairwiseCriterion.DIRECTNESS: "how plainly and briefly the answer answers the question",
}


class PairwiseVerdict(BaseModel):
    """One question's own head-to-head verdict, on one criterion, in both orders and reconciled.

    `first`/`swapped` are `Preference` in the caller's own frame — already translated from the
    two `Position` answers the judge actually gave, through `judge_pair`'s own order-specific
    mapping — so a reader never has to re-derive which shown position was which arm. `outcome`
    is `reconcile(first, swapped)`, kept alongside the two raw readings rather than only the
    reconciled value, so an order-dependent tie is still distinguishable from a consistent one by
    a caller that wants to know.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    criterion: PairwiseCriterion
    first: Preference
    swapped: Preference
    outcome: Preference


class PairwiseSummary(BaseModel):
    """A win rate over every judged question, plus its paired bootstrap interval.

    `criterion` is the verdicts' own shared criterion, or `None` when `summarise` was handed
    verdicts scored under more than one — a summary that mixed criteria without saying so would
    read as a single measurement of nothing in particular. `low`/`high` are `None` for fewer than
    two questions, `weft_eval.falsify.paired_interval`'s own posture: a single question has no
    spread to report.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    criterion: PairwiseCriterion | None
    n: int
    wins_a: int
    wins_b: int
    ties: int
    win_rate_b: float | None
    low: float | None
    high: float | None


def reconcile(first: Preference, swapped: Preference) -> Preference:
    """`first` and `swapped` agree, or the verdict is a tie — never a win either order alone gave.

    A judge that prefers whichever answer it reads first would otherwise report a consistent
    winner every time; asking twice, in both orders, and requiring agreement is what makes that
    failure show up as a tie instead of a win (Zheng et al., NeurIPS 2023 — see the module
    docstring).
    """
    return first if first == swapped else Preference.TIE


#: `Position` read from the call that showed `answer_a` first, translated into the caller's own
#: `Preference` frame: the judge's `FIRST` is `answer_a`, `SECOND` is `answer_b`.
_FIRST_ORDER: Mapping[Position, Preference] = {
    Position.FIRST: Preference.A,
    Position.SECOND: Preference.B,
    Position.TIE: Preference.TIE,
}

#: The identical translation for the call that showed `answer_b` first — the judge's `FIRST` is
#: now `answer_b`, `SECOND` is `answer_a`, `Position`'s own meaning inverted by the swap.
_SWAPPED_ORDER: Mapping[Position, Preference] = {
    Position.FIRST: Preference.B,
    Position.SECOND: Preference.A,
    Position.TIE: Preference.TIE,
}


def _pairwise_request(
    *,
    question: str,
    first_answer: str,
    second_answer: str,
    criterion: PairwiseCriterion,
) -> PairwiseJudgeRequest:
    return PairwiseJudgeRequest(
        question=question,
        first_answer=first_answer,
        second_answer=second_answer,
        criterion_name=criterion.value,
        criterion_definition=CRITERION_DEFINITIONS[criterion],
    )


async def judge_pair(
    *,
    question_id: str,
    question: str,
    answer_a: str,
    answer_b: str,
    criterion: PairwiseCriterion,
    ctx: Context,
    role: str = "grade",
) -> Outcome[PairwiseVerdict]:
    """Judge `answer_a` against `answer_b` on `criterion`, once in each order.

    Calls `weft_prompts.cascade.execute` twice — first showing `answer_a` before `answer_b`,
    then the reverse — and maps each call's own `weft_eval.prompts.Position` answer back into
    the caller's `Preference` frame before reconciling the two (`reconcile`). Returns `Failed`,
    naming `question_id` and which order failed, when either call's own outcome is not
    `Produced` — never folded into a tie, because a tie is a measurement about the judge's
    consistency and a failed call measured nothing at all.
    """
    llm = ctx.require(LLM)
    first_outcome = await execute(
        llm=llm,
        prompt=cast("Prompt", PairwiseJudgePrompt()),
        values=_pairwise_request(
            question=question, first_answer=answer_a, second_answer=answer_b, criterion=criterion
        ),
        output=PairwiseChoice,
        role=role,
        ctx=ctx,
    )
    swapped_outcome = await execute(
        llm=llm,
        prompt=cast("Prompt", PairwiseJudgePrompt()),
        values=_pairwise_request(
            question=question, first_answer=answer_b, second_answer=answer_a, criterion=criterion
        ),
        output=PairwiseChoice,
        role=role,
        ctx=ctx,
    )
    if not isinstance(first_outcome, Produced):
        return Failed(
            reason=(
                f"question '{question_id}': the '{PAIRWISE_JUDGE_PROMPT_NAME}' call with "
                f"answer A shown first did not produce a judgement — {first_outcome.reason}"
            )
        )
    if not isinstance(swapped_outcome, Produced):
        return Failed(
            reason=(
                f"question '{question_id}': the '{PAIRWISE_JUDGE_PROMPT_NAME}' call with "
                f"answer B shown first did not produce a judgement — {swapped_outcome.reason}"
            )
        )
    first = _FIRST_ORDER[first_outcome.value.value.winner]
    swapped = _SWAPPED_ORDER[swapped_outcome.value.value.winner]
    return Produced(
        value=PairwiseVerdict(
            question_id=question_id,
            criterion=criterion,
            first=first,
            swapped=swapped,
            outcome=reconcile(first, swapped),
        )
    )


#: `Preference.outcome` as a score — win 1, tie 0.5, loss (for B) 0 — `summarise`'s own basis.
_SCORE_FOR_B: Mapping[Preference, float] = {
    Preference.A: 0.0,
    Preference.TIE: 0.5,
    Preference.B: 1.0,
}


def _shared_criterion(verdicts: Sequence[PairwiseVerdict]) -> PairwiseCriterion | None:
    criteria = {verdict.criterion for verdict in verdicts}
    return next(iter(criteria)) if len(criteria) == 1 else None


def summarise(
    verdicts: Sequence[PairwiseVerdict], *, criterion: PairwiseCriterion | None = None
) -> PairwiseSummary:
    """`verdicts`' own win rate for B, and its paired bootstrap interval over questions.

    Each question scores `1.0` for a B win, `0.5` for a tie, `0.0` for an A win; `win_rate_b` is
    their mean, or `None` when nothing was judged. The interval shifts
    `weft_eval.falsify.paired_interval`'s own `[-0.5, 0.5]`-scale difference back onto the
    `[0, 1]` win-rate scale `win_rate_b` reports on, since that function takes a *difference*
    from a neutral `0.5` rather than a win rate directly.
    """
    n = len(verdicts)
    scores = [_SCORE_FOR_B[verdict.outcome] for verdict in verdicts]
    win_rate_b = sum(scores) / n if n else None
    low, high = paired_interval(
        [
            (verdict.question_id, score - 0.5)
            for verdict, score in zip(verdicts, scores, strict=True)
        ]
    )
    return PairwiseSummary(
        criterion=criterion if criterion is not None else _shared_criterion(verdicts),
        n=n,
        wins_a=sum(1 for verdict in verdicts if verdict.outcome is Preference.A),
        wins_b=sum(1 for verdict in verdicts if verdict.outcome is Preference.B),
        ties=sum(1 for verdict in verdicts if verdict.outcome is Preference.TIE),
        win_rate_b=win_rate_b,
        low=low + 0.5 if low is not None else None,
        high=high + 0.5 if high is not None else None,
    )


class PairwiseFailure(BaseModel):
    """One question, one criterion, one judgement that did not produce a verdict.

    Never a tie — a `Failed` outcome measured the judge's *reliability*, not its preference, so
    it is kept apart from `PairwiseRecord.verdicts` rather than folded into one as a tie would be.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question_id: str
    criterion: PairwiseCriterion
    reason: str


class PairwiseRecord(BaseModel):
    """One `weft eval pairwise` run: every criterion asked for, judged and summarised — **44.43b**.

    `summaries`/`verdicts`/`failures` cover every criterion `compare_arms` was asked for, in
    request order for `summaries`. `unpaired` names every question exactly one of the two arms
    answered, in question order — never judged, since a pairwise judge needs both sides' answers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str
    invocation: str
    baseline: str
    arm: str
    prompt_version: str
    summaries: tuple[PairwiseSummary, ...]
    verdicts: tuple[PairwiseVerdict, ...]
    failures: tuple[PairwiseFailure, ...]
    unpaired: tuple[str, ...]


def _known_arm_names(experiment: Experiment) -> tuple[str, ...]:
    return tuple(arm.name for arm in experiment.arms)


def _check_known_arms(experiment: Experiment, *, baseline: str, arm: str) -> None:
    """Refuse a `baseline`/`arm` name the document does not declare — before anything else runs."""
    valid_options = _known_arm_names(experiment)
    for candidate in (baseline, arm):
        if candidate not in valid_options:
            named = ", ".join(f"'{name}'" for name in valid_options)
            raise UnknownArmError(
                f"experiment '{experiment.name}' declares no arm named '{candidate}'; its "
                f"arms: {named}.",
                arm=candidate,
                valid_options=valid_options,
            )


def _check_pairable(
    baseline_record: RunRecord, arm_record: RunRecord, *, baseline: str, arm: str
) -> None:
    """Refuse two repetition-1 records that did not answer the same questions of the same corpus."""
    reasons = pairing_reasons(baseline_record, arm_record)
    if reasons:
        raise UnpairableRecordsError(
            f"'{baseline}' and '{arm}' do not pair: {'; '.join(reasons)} — a pairwise "
            "judgement compares two arms that answered the same questions.",
            reasons=tuple(reasons),
        )


def _check_answers_recorded(
    record: RunRecord, *, arm: str, experiment: str, invocation: str
) -> None:
    """Refuse a repetition-1 record that kept no answer text at all — `UnrecordedAnswersError`."""
    if record.question_answers is not None:
        return
    raise UnrecordedAnswersError(
        f"arm '{arm}' of experiment '{experiment}' recorded no answer text in invocation "
        f"'{invocation[:8]}…' — a record written before answers were kept cannot be judged "
        "pairwise; run the arm again with `weft eval experiment`.",
        arm=arm,
    )


def _paired_and_unpaired(
    questions: Mapping[str, str],
    baseline_answers: Mapping[str, str],
    arm_answers: Mapping[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    paired: list[str] = []
    unpaired: list[str] = []
    for question_id in questions:
        in_baseline = question_id in baseline_answers
        in_arm = question_id in arm_answers
        if in_baseline and in_arm:
            paired.append(question_id)
        elif in_baseline or in_arm:
            unpaired.append(question_id)
    return tuple(paired), tuple(unpaired)


async def _judge_paired_questions(
    paired: Sequence[str],
    *,
    questions: Mapping[str, str],
    baseline_answers: Mapping[str, str],
    arm_answers: Mapping[str, str],
    criteria: Sequence[PairwiseCriterion],
    ctx: Context,
) -> tuple[tuple[PairwiseVerdict, ...], tuple[PairwiseFailure, ...]]:
    verdicts: list[PairwiseVerdict] = []
    failures: list[PairwiseFailure] = []
    for question_id in paired:
        for criterion in criteria:
            outcome = await judge_pair(
                question_id=question_id,
                question=questions[question_id],
                answer_a=baseline_answers[question_id],
                answer_b=arm_answers[question_id],
                criterion=criterion,
                ctx=ctx,
            )
            if isinstance(outcome, Produced):
                verdicts.append(outcome.value)
            else:
                failures.append(
                    PairwiseFailure(
                        question_id=question_id, criterion=criterion, reason=outcome.reason
                    )
                )
    return tuple(verdicts), tuple(failures)


async def compare_arms(
    experiment: Experiment,
    records: Sequence[RunRecord],
    *,
    questions: Mapping[str, str],
    baseline: str,
    arm: str,
    criteria: Sequence[PairwiseCriterion],
    ctx: Context,
    invocation: str | None = None,
    limit: int | None = None,
) -> PairwiseRecord:
    """Judge `baseline` against `arm` over `questions`, on every criterion in `criteria`.

    See the module docstring's task-**44.43b** paragraphs for the full order of refusals — every
    one of `UnknownArmError`/`UnpairableRecordsError`/`UnrecordedAnswersError` is raised before a
    single model call, and only `UnknownArmError` joins FF12's family.
    """
    _check_known_arms(experiment, baseline=baseline, arm=arm)
    chosen_invocation, by_key = select_invocation(experiment, records, invocation=invocation)
    baseline_record = by_key[(baseline, 1)]
    arm_record = by_key[(arm, 1)]
    _check_pairable(baseline_record, arm_record, baseline=baseline, arm=arm)
    _check_answers_recorded(
        baseline_record, arm=baseline, experiment=experiment.name, invocation=chosen_invocation
    )
    _check_answers_recorded(
        arm_record, arm=arm, experiment=experiment.name, invocation=chosen_invocation
    )
    baseline_answers = cast(Mapping[str, str], baseline_record.question_answers)
    arm_answers = cast(Mapping[str, str], arm_record.question_answers)

    paired, unpaired = _paired_and_unpaired(questions, baseline_answers, arm_answers)
    if limit is not None:
        paired = paired[:limit]

    verdicts, failures = await _judge_paired_questions(
        paired,
        questions=questions,
        baseline_answers=baseline_answers,
        arm_answers=arm_answers,
        criteria=criteria,
        ctx=ctx,
    )
    summaries = tuple(
        summarise(
            [verdict for verdict in verdicts if verdict.criterion == criterion],
            criterion=criterion,
        )
        for criterion in criteria
    )
    return PairwiseRecord(
        experiment=experiment.name,
        invocation=chosen_invocation,
        baseline=baseline,
        arm=arm,
        prompt_version=PairwiseJudgePrompt.version,
        summaries=summaries,
        verdicts=verdicts,
        failures=failures,
        unpaired=unpaired,
    )


def write_pairwise_record(record: PairwiseRecord, path: Path) -> None:
    """Write `record` as JSON to `path`, creating parent directories as needed.

    `weft_eval.run_record.write_run_record`'s own shape — plain `Path.write_text`, no store.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")


def load_pairwise_record(path: Path) -> PairwiseRecord:
    """Read a `PairwiseRecord` back from `path` — `write_pairwise_record`'s other half."""
    return PairwiseRecord.model_validate_json(path.read_text(encoding="utf-8"))


def _win_rate_cell(summary: PairwiseSummary) -> str:
    if summary.win_rate_b is None:
        return "—"
    return f"{summary.win_rate_b:.3f}"


def _interval_cell(summary: PairwiseSummary) -> str:
    if summary.low is None or summary.high is None:
        return "—"
    return f"{summary.low:.3f} to {summary.high:.3f}"


def _render_summary_row(summary: PairwiseSummary) -> str:
    return (
        f"| {summary.criterion} | {summary.n} | {summary.wins_a} | {summary.wins_b} | "
        f"{summary.ties} | {_win_rate_cell(summary)} | {_interval_cell(summary)} |"
    )


def render_pairwise_table(record: PairwiseRecord) -> str:
    r"""Render `record` as deterministic markdown. Ends in exactly one `\n`."""
    lines = [
        f"# Pairwise — {record.experiment}",
        "",
        f"invocation: {record.invocation} · baseline: {record.baseline} · arm: {record.arm}",
        "",
        f"| criterion | n | {record.baseline} wins | {record.arm} wins | ties | "
        f"{record.arm} win rate | 95% interval |",
        "|---|---|---|---|---|---|---|",
    ]
    lines.extend(_render_summary_row(summary) for summary in record.summaries)
    if record.failures or record.unpaired:
        lines.append(
            f"failures: {len(record.failures)} · unpaired questions: {len(record.unpaired)}"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "CRITERION_DEFINITIONS",
    "PairwiseChoice",
    "PairwiseCriterion",
    "PairwiseFailure",
    "PairwiseRecord",
    "PairwiseSummary",
    "PairwiseVerdict",
    "Position",
    "Preference",
    "UnknownArmError",
    "UnrecordedAnswersError",
    "compare_arms",
    "judge_pair",
    "load_pairwise_record",
    "reconcile",
    "render_pairwise_table",
    "summarise",
    "write_pairwise_record",
]
