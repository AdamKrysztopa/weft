"""Hold a router that cites evidence to the evidence it cites, when it is loaded.

Fitness function 38 holds every *shipped* `evidence-policy` router to its claims, but a router a
project derives (`extends: route-by-evidence`) never reaches that gate, so a derived document could
cite a positive effect below its pre-registered margin and be routed on. This runs
`weft_eval.eligibility`, the same rules FF38 uses, over the router once it is resolved — at load,
never per question, so the ask stays as cheap as it was.

It does not recompute a claim or compare a fingerprint: the first is `weft eval claims check`,
which needs the run records a wheel does not carry, and the second needs the rungs resolved. What it
refuses is what a document alone shows: an unknown claim, one that is not *worthwhile* on committed
records, one about another rung, or a rule whose `when` does not contain the claim's regime.
"""

from collections.abc import Sequence
from pathlib import Path

from weft_eval.claims import Claim, load_claims, shipped_claims_dir
from weft_eval.eligibility import policy_violations
from weft_kernel.errors import WeftError
from weft_kernel.resolution import ResolvedPipeline
from weft_retrieve.policy import EVIDENCE_POLICY_NAME, EvidencePolicyConfig

#: Where a project keeps claims of its own, relative to the directory `weft` runs in.
PROJECT_CLAIMS_DIRECTORY = Path("eval") / "claims"


class UnsupportedEvidenceError(WeftError):
    """A router's rule cites evidence that does not support it; the message names every rule."""


def guard_claims(root: Path) -> tuple[Claim, ...]:
    """The shipped claims, then any in `root`'s own `eval/claims/`; a project's id wins no clash.

    A project claim whose id a shipped one already holds is dropped rather than allowed to replace
    it, so a project cannot restate what the wheel measured and then cite its own version.
    """
    shipped = load_claims(shipped_claims_dir())
    held = {claim.id for claim in shipped}
    project_directory = root / PROJECT_CLAIMS_DIRECTORY
    project = (
        tuple(claim for claim in load_claims(project_directory) if claim.id not in held)
        if project_directory.is_dir()
        else ()
    )
    return (*shipped, *project)


def _policies(router: ResolvedPipeline) -> dict[str, EvidencePolicyConfig]:
    """Each `evidence-policy` stage's configuration, keyed by the router and stage that hold it."""
    return {
        f"router '{router.name}' stage '{stage.id}'": EvidencePolicyConfig.model_validate(
            stage.config
        )
        for stage in router.stages
        if stage.use == EVIDENCE_POLICY_NAME
    }


def refuse_unsupported_evidence(router: ResolvedPipeline, claims: Sequence[Claim]) -> None:
    """Raise `UnsupportedEvidenceError` naming every rule of `router` its claims do not support.

    A router with no `evidence-policy` stage cites nothing and is not asked anything.
    """
    policies = _policies(router)
    if not policies:
        return
    problems = policy_violations(policies, claims, generating_roles=None, not_valid={})
    if problems:
        raise UnsupportedEvidenceError(
            "the router cites evidence that does not support its rules:\n  "
            + "\n  ".join(problems)
            + "\nCite a claim that is 'worthwhile' on committed records, about the rule's own "
            "rung, whose regime the rule's `when` contains; `weft eval claims check` lists them."
        )


def guard_router(router: ResolvedPipeline, *, root: Path) -> None:
    """`refuse_unsupported_evidence` over the claims `root` can see, loading them only if needed."""
    if _policies(router):
        refuse_unsupported_evidence(router, guard_claims(root))


__all__ = [
    "PROJECT_CLAIMS_DIRECTORY",
    "UnsupportedEvidenceError",
    "guard_claims",
    "guard_router",
    "refuse_unsupported_evidence",
]
