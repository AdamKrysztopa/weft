"""`check_claim` — recompute a claim from the committed records it names (task **44.31**).

A claim states a status; this reads the experiment document and run records the claim's `source`
names, pairs the rung's arm against the baseline's arm question by question over the repetitions
both ran, takes the paired interval `weft_eval.falsify` already computes, reads it against the
claim's margin with `weft_eval.verdict.verdict`, and refuses a stated status the interval does not
support. Nothing numeric is trusted from the claim file; the mean, interval and `n` it reports are
what the records say today.

`wrong-questions` and `never` cannot be derived from an interval — they say the comparison asked
the wrong thing, or was never run — so a claim stating one is reported as asserted rather than
checked. A `basis = "ledger"` claim has no records to recompute and is reported as such.

A rung or baseline is resolved against the experiment's own arms and never taken from a task
line (`L28.86`); a pipeline run by more than one arm is refused until the claim names one with
`arm`/`baseline_arm`, never resolved to the last (`L28.87`).

**Staleness** is a reading, never a refusal (`weft_eval.fingerprint` says what it compares): a claim
pinned to the stages of the tree that is running is `valid`; a pinned component that has moved is
`definitely-stale`; a claim with no pin, or whose tree cannot be resolved here, is `possibly-stale`.
The caller resolves the live tree and hands it in as `live`, because resolving a pipeline needs the
registry and this module reads records. `weft eval claims check` prints the reading and a rule that
cites the claim is held to it by fitness function 38.
"""

from collections.abc import Mapping
from importlib import metadata
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from weft_eval.claims import Claim, ClaimBasis, ClaimSource
from weft_eval.evidence import select_invocation
from weft_eval.experiment import Direction, Experiment, ExperimentArm, load_experiment
from weft_eval.falsify import pooled_paired_differences
from weft_eval.fingerprint import LiveEvidence, Staleness, assess_staleness
from weft_eval.run_record import RunRecord, load_run_record
from weft_eval.verdict import ClaimStatus, EffectVerdict, verdict
from weft_kernel.errors import UnresolvedNameError, WeftError


class ClaimMismatchError(WeftError):
    """A claim states a status its own records do not support, or cannot be recomputed."""


class UnresolvedClaimArmError(WeftError, UnresolvedNameError):
    """A claim names a rung or baseline no arm of its experiment runs."""

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class ClaimCheck(BaseModel):
    """What recomputing one claim found."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim_id: str
    stated: ClaimStatus
    stated_verdict: EffectVerdict | None
    #: `None` when the claim is not recomputable: a ledger claim, or a status no interval gives.
    derived: ClaimStatus | None
    verdict: EffectVerdict | None
    mean: float | None
    low: float | None
    high: float | None
    n: int | None
    margin: float | None
    reproducible: bool
    staleness: Staleness
    #: Every reason for a staleness other than `valid`, `None` when it is valid.
    stale: str | None


def claim_arms(claim: Claim, experiment: Experiment) -> tuple[ExperimentArm, ExperimentArm]:
    """The experiment arms that ran `claim`'s rung and its baseline."""
    return (
        _arm_for(claim.rung, claim.arm, experiment, claim=claim, what="rung"),
        _arm_for(claim.baseline, claim.baseline_arm, experiment, claim=claim, what="baseline"),
    )


def _arm_for(
    rung: str, arm_name: str | None, experiment: Experiment, *, claim: Claim, what: str
) -> ExperimentArm:
    where = claim.source.experiment if claim.source else "its experiment"
    if arm_name is not None:
        by_name = {arm.name: arm for arm in experiment.arms}
        if arm_name not in by_name:
            options = tuple(sorted(by_name))
            raise UnresolvedClaimArmError(
                f"claim '{claim.id}': its {what} arm '{arm_name}' is not an arm of {where}. "
                f"Arms: {', '.join(options)}.",
                valid_options=options,
            )
        return by_name[arm_name]
    named: dict[str, list[ExperimentArm]] = {}
    for arm in experiment.arms:
        run_name = arm.query_pipeline or arm.router
        if run_name:
            named.setdefault(run_name, []).append(arm)
    if rung not in named:
        options = tuple(sorted(named))
        raise UnresolvedClaimArmError(
            f"claim '{claim.id}': its {what} '{rung}' is run by no arm of {where}. Rungs run: "
            f"{', '.join(options)}.",
            valid_options=options,
        )
    arms = named[rung]
    if len(arms) > 1:
        options = tuple(sorted(arm.name for arm in arms))
        raise UnresolvedClaimArmError(
            f"claim '{claim.id}': its {what} '{rung}' is run by more than one arm of {where}: "
            f"{', '.join(options)}. Name the one it means with `arm`/`baseline_arm`.",
            valid_options=options,
        )
    return arms[0]


def _records_of(by_key: Mapping[tuple[str, int], RunRecord], arm: str) -> list[RunRecord]:
    return [by_key[key] for key in sorted(by_key, key=lambda k: k[1]) if key[0] == arm]


def _runs_dir(source: ClaimSource, experiment_path: Path, root: Path) -> Path:
    if source.runs is not None:
        return root / source.runs
    return experiment_path.with_suffix("") / "runs"


_NOT_COMPARED = LiveEvidence(fingerprint=None, unresolved="this check was given no live tree")


def _staleness(
    claim: Claim, records: list[RunRecord], live: LiveEvidence
) -> tuple[Staleness, str | None]:
    recorded = records[0].distribution_versions
    reading = assess_staleness(
        claim.fingerprint,
        live,
        recorded_major=recorded.get("weft-rag") if recorded else None,
        current_major=metadata.version("weft-rag"),
    )
    reasons = "; ".join(reading.reasons)
    return reading.staleness, reasons or None


def check_claim(claim: Claim, *, root: Path, live: LiveEvidence | None = None) -> ClaimCheck:
    """Recompute `claim` from the records beside its experiment, refusing an unsupported status.

    `live` is what the running tree gives for the claim; without it the claim is `possibly-stale`,
    never `valid`, because nothing was compared.
    """
    if claim.basis is ClaimBasis.LEDGER or claim.source is None:
        return ClaimCheck(
            claim_id=claim.id,
            stated=claim.status,
            stated_verdict=claim.verdict,
            derived=None,
            verdict=None,
            mean=None,
            low=None,
            high=None,
            n=None,
            margin=None,
            reproducible=False,
            staleness=Staleness.POSSIBLY_STALE,
            stale="a ledger claim has no records to recompute and no pipelines to pin",
        )
    experiment_path = root / claim.source.experiment
    experiment = load_experiment(experiment_path)
    runs = _runs_dir(claim.source, experiment_path, root)
    if not runs.is_dir():
        raise ClaimMismatchError(f"claim '{claim.id}': no run records at {runs}.")
    records = [load_run_record(path) for path in sorted(runs.glob("*.json"))]
    _, by_key = select_invocation(experiment, records, invocation=claim.source.invocation)
    rung_arm, base_arm = claim_arms(claim, experiment)
    rung_records = _records_of(by_key, rung_arm.name)
    base_records = _records_of(by_key, base_arm.name)
    repeats = min(len(rung_records), len(base_records))
    pairs = list(zip(base_records[:repeats], rung_records[:repeats], strict=True))
    differences = pooled_paired_differences(pairs)
    if claim.metric not in differences:
        raise ClaimMismatchError(
            f"claim '{claim.id}': no record scored '{claim.metric}'. "
            f"Scored: {', '.join(sorted(differences))}."
        )
    paired = differences[claim.metric]
    if paired.low is None or paired.high is None:
        raise ClaimMismatchError(f"claim '{claim.id}': too few paired questions for an interval.")
    margin = claim.margin if claim.margin is not None else experiment.minimum_detectable_effect
    decision = experiment.decision
    mean, low, high = paired.mean, paired.low, paired.high
    if (
        decision is not None
        and decision.metric == claim.metric
        and decision.direction is Direction.LOWER_IS_BETTER
    ):
        mean, low, high = -mean, -high, -low
    staleness, stale = _staleness(claim, rung_records, live or _NOT_COMPARED)
    if claim.status in {ClaimStatus.WRONG_QUESTIONS, ClaimStatus.NEVER}:
        derived, reading = None, None
    else:
        reading = verdict(low, high, mean, margin=margin)
        derived = reading.status
        if reading is not claim.verdict:
            raise ClaimMismatchError(
                f"claim '{claim.id}' states '{claim.status}' ({claim.verdict}), but its records "
                f"give a paired difference of {mean:+.3f} (95% interval {low:+.3f} to {high:+.3f}, "
                f"n {paired.n}) against a margin of {margin}, which reads as '{derived}' "
                f"({reading})."
            )
    return ClaimCheck(
        claim_id=claim.id,
        stated=claim.status,
        stated_verdict=claim.verdict,
        derived=derived,
        verdict=reading,
        mean=mean,
        low=low,
        high=high,
        n=paired.n,
        margin=margin,
        reproducible=True,
        staleness=staleness,
        stale=stale,
    )


__all__ = [
    "ClaimCheck",
    "ClaimMismatchError",
    "UnresolvedClaimArmError",
    "check_claim",
    "claim_arms",
]
