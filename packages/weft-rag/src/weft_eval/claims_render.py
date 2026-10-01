"""`render_claims_table` — the rung table of `manual/evidence.md` §3, generated from claims.

Task **44.32**. One row per rung that has a claim, in rung order, then one row naming every shipped
rung that has none as *never*, which is true by construction: a rung with no claim is a rung nobody
has measured, and the page cannot say otherwise without writing a claim first. The numbers in a
`records` claim's row are the ones `weft_eval.claims_check.check_claim` recomputed from the
committed records, never typed. A `ledger` claim is rendered as not reproducible from committed
records, with the ledger entry it rests on; an asserted status says it is asserted.
"""

from collections.abc import Sequence

from weft_eval.claims import Claim, ClaimBasis
from weft_eval.claims_check import ClaimCheck

HEADER = "| rung | status | evidence |\n|---|---|---|"


def _regime(claim: Claim) -> str:
    if not claim.regime:
        return ""
    return " when " + " and ".join(
        f"{condition.feature} {condition.op} {condition.value}" for condition in claim.regime
    )


def _sentence(claim: Claim, check: ClaimCheck) -> str:
    on = f"`{claim.metric}` ({claim.population.language}, {claim.population.benchmark})"
    standing = f"{claim.status} ({claim.verdict})" if claim.verdict else str(claim.status)
    lead = f"**{standing}** against `{claim.baseline}` on {on}"
    if claim.basis is ClaimBasis.LEDGER or not check.reproducible:
        return f"{lead}: not reproducible from committed records ({claim.ledger})"
    if check.mean is None or check.low is None or check.high is None:
        return f"{lead}: asserted, not derivable from an interval"
    stale = f" — {check.staleness}: {check.stale}" if check.stale else ""
    asserted = "; asserted, not derivable from an interval" if check.derived is None else ""
    return (
        f"{lead}{_regime(claim)}: {check.mean:+.3f} (95% interval {check.low:+.3f} to "
        f"{check.high:+.3f}), n {check.n}{asserted}{stale}"
    )


def _evidence(claim: Claim) -> str:
    if claim.source is None:
        return f"{claim.ledger}"
    experiment = claim.source.experiment.removesuffix(".toml")
    return f"`{claim.source.runs or experiment}`"


def render_claims_table(
    entries: Sequence[tuple[Claim, ClaimCheck]], *, shipped_rungs: Sequence[str]
) -> str:
    """The generated rung table: a row per claimed rung, then a *never* row for the rest."""
    by_rung: dict[str, list[tuple[Claim, ClaimCheck]]] = {}
    for claim, check in sorted(entries, key=lambda entry: entry[0].id):
        by_rung.setdefault(claim.rung, []).append((claim, check))
    rows = [HEADER]
    for rung in sorted(by_rung):
        group = by_rung[rung]
        status = "; ".join(_sentence(claim, check) for claim, check in group)
        evidence = ", ".join(dict.fromkeys(_evidence(claim) for claim, _ in group))
        rows.append(f"| `{rung}` | {status} | {evidence} |")
    unclaimed = sorted(set(shipped_rungs) - set(by_rung))
    if unclaimed:
        rows.append(f"| {', '.join(f'`{rung}`' for rung in unclaimed)} | never | none |")
    return "\n".join(rows)


__all__ = ["HEADER", "render_claims_table"]
