"""The running tree's side of an evidence fingerprint — task **44.62**.

`weft_eval.fingerprint` says what a claim's numbers depend on; this resolves those things for the
tree that is running now, the way a run would, so `weft eval claims check` and `pin` and fitness
function 38 all read one function. Nothing here reads the machine: no `weft.toml` role, no account
setting, no store. A claim must not look stale because of whose laptop checked it. The registry it
is handed is `registry_bootstrap.resolution_dependencies()`: installed packs only, no `weft.toml`,
no environment, no store connection.

An experiment's own pipelines live beside it (`eval/experiments/pipelines`), so the catalogue a
claim's arms are resolved against is the shipped pipelines plus those, never the current directory's
`pipelines/`, which is whatever project the command was run from.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from weft_cli.eval_scoring import judge_prompt_digests
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import named_pipeline, resolve_in_catalogue
from weft_engine.registry_bootstrap import Dependencies
from weft_eval.claims import Claim
from weft_eval.claims_check import claim_arms
from weft_eval.contract import GenerationMetric, RetrievalMetric
from weft_eval.experiment import ExperimentArm, load_experiment
from weft_eval.fingerprint import ClaimFingerprint, LiveEvidence, stage_identity
from weft_kernel.errors import WeftError
from weft_kernel.pipeline import Pipeline
from weft_retrieve.profile import PROFILER_VERSION


def _stage_identity_of(name: str, *, catalogue: Mapping[str, Pipeline], deps: Dependencies) -> str:
    resolved = resolve_in_catalogue(
        named_pipeline(name, catalogue=catalogue),
        registry=deps.registry,
        catalogue=catalogue,
        reports=deps.reports,
        contributions=deps.contributions,
    )
    return stage_identity(resolved)


def _metric_names(deps: Dependencies) -> tuple[str, ...]:
    return tuple(
        sorted(deps.registry.names_for(GenerationMetric) | deps.registry.names_for(RetrievalMetric))
    )


def _query_side(arm: ExperimentArm) -> str:
    """The pipeline an arm answered through: its router, its query rung, else the index itself."""
    return arm.router or arm.query_pipeline or arm.pipeline


def _resolved_components(
    claim: Claim, experiment_path: Path, deps: Dependencies
) -> tuple[Mapping[str, str], ExperimentArm, ExperimentArm]:
    """Each pipeline `claim` rests on, resolved; raises a `WeftError` if any cannot be."""
    experiment = load_experiment(experiment_path)
    rung_arm, base_arm = claim_arms(claim, experiment)
    catalogue = full_catalogue(directory=experiment_path.parent / "pipelines", reports=deps.reports)

    def identity(name: str) -> str:
        return _stage_identity_of(name, catalogue=catalogue, deps=deps)

    resolved = {
        "rung": identity(_query_side(rung_arm)),
        "baseline": identity(_query_side(base_arm)),
        "index": identity(rung_arm.pipeline),
        "baseline_index": identity(base_arm.pipeline),
    }
    return resolved, rung_arm, base_arm


def live_evidence(claim: Claim, *, root: Path, deps: Dependencies) -> LiveEvidence:
    """`claim`'s fingerprint under the running tree, or the reason it cannot be resolved.

    Every failure to resolve is a named `WeftError` from the catalogue or the resolver, reported as
    the reason rather than guessed past: a pipeline from a pack that is not installed is not
    evidence of anything either way.
    """
    if claim.source is None:
        return LiveEvidence(fingerprint=None, unresolved="a ledger claim names no experiment")
    try:
        resolved, rung_arm, base_arm = _resolved_components(
            claim, root / claim.source.experiment, deps
        )
    except WeftError as unresolved:
        return LiveEvidence(fingerprint=None, unresolved=" ".join(str(unresolved).split()))
    judge = judge_prompt_digests(deps.registry, _metric_names(deps)).get(claim.metric)
    reads_a_profile = bool(claim.regime) or rung_arm.router or base_arm.router
    return LiveEvidence(
        fingerprint=ClaimFingerprint(
            **resolved, judge=judge, profiler=PROFILER_VERSION if reads_a_profile else None
        ),
        unresolved=None,
    )


__all__ = ["live_evidence"]
