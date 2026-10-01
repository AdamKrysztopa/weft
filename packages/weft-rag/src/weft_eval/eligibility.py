"""Whether an `evidence-policy` rule is supported by the claims it cites.

The checks fitness function 38 holds every shipped router to, lifted here so a router a project
derives is held to the same ones when it is loaded (`weft_cli.evidence_guard`) — one function
answering both, rather than two that agree today. A router cannot be handed a rule the evidence
does not reach by editing a document the gate never reads.

A rule is supported when each claim it cites exists, is *worthwhile* on committed records (a
positive effect below its pre-registered margin is not), is about the rule's own rung, and has its
regime contained in the rule's `when`, so the rule never fires where the evidence does not reach.
A rule under `defaults` cites claims from two populations (D9), because a rule keyed to one
benchmark wins there and nowhere else. A context-fit predicate is about the role the rung generates
under. None of this recomputes a claim: whether the records still say what a claim states is
`weft eval claims check`, and whether the tree still matches what they measured is the fingerprint
(`weft_eval.fingerprint`), which needs the pipelines resolved and so is the caller's to supply as
`not_valid`.
"""

import math
from collections.abc import Mapping, Sequence
from typing import Final

from weft_eval.claims import Claim
from weft_retrieve.policy import EvidencePolicyConfig, PolicyRule
from weft_retrieve.profile import fits_context_role, is_declared_feature
from weft_retrieve.routing import Comparison, Condition

type _Interval = tuple[float, bool, float, bool]

_NO_WAIVERS: Final[frozenset[tuple[str, str]]] = frozenset()


def _interval(op: Comparison, value: float) -> _Interval:
    """`(low, low_closed, high, high_closed)` of the numbers `x op value` admits."""
    match op:
        case Comparison.GTE:
            return (value, True, math.inf, True)
        case Comparison.GT:
            return (value, False, math.inf, True)
        case Comparison.LTE:
            return (-math.inf, True, value, True)
        case Comparison.LT:
            return (-math.inf, True, value, False)
        case Comparison.EQ:
            return (value, True, value, True)
        case Comparison.NE:
            raise ValueError("'ne' admits no single interval")


def _within(inner: _Interval, outer: _Interval) -> bool:
    low_ok = inner[0] > outer[0] or (inner[0] == outer[0] and (outer[1] or not inner[1]))
    high_ok = inner[2] < outer[2] or (inner[2] == outer[2] and (outer[3] or not inner[3]))
    return low_ok and high_ok


def _implies_discrete(rule: Condition, claim: Condition) -> bool:
    """`eq`/`ne` against any value, which is all a boolean feature supports."""
    equal = rule.value == claim.value
    match claim.op:
        case Comparison.EQ:
            return rule.op is Comparison.EQ and equal
        case Comparison.NE:
            return (rule.op is Comparison.NE and equal) or (rule.op is Comparison.EQ and not equal)
        case _:
            return False


def implies(rule: Condition, claim: Condition) -> bool:
    """Whether `rule` holds only where `claim` holds: the same feature, equal or tighter."""
    if rule.feature != claim.feature:
        return False
    discrete = (
        isinstance(rule.value, bool)
        or isinstance(claim.value, bool)
        or Comparison.NE in {rule.op, claim.op}
    )
    if discrete:
        return _implies_discrete(rule, claim)
    return _within(_interval(rule.op, rule.value), _interval(claim.op, claim.value))


def _fit_violations(
    where: str, rule: PolicyRule, generating_roles: Mapping[str, str | None]
) -> list[str]:
    """A context-fit predicate must be about the role the rung's answer is written under."""
    rung_role = generating_roles.get(rule.then)
    found: list[str] = []
    for condition in rule.when:
        tested = fits_context_role(condition.feature)
        if tested is None:
            continue
        if rung_role is None:
            found.append(
                f"{where} tests '{condition.feature}', but the generating role of its rung "
                f"'{rule.then}' cannot be read"
            )
        elif tested != rung_role:
            found.append(
                f"{where} tests '{condition.feature}', the fit under role '{tested}', but its "
                f"rung '{rule.then}' generates under '{rung_role}'"
            )
    return found


def _claim_violations(
    where: str, rule: PolicyRule, claim: Claim, not_valid: str | None
) -> list[str]:
    """What a rule's citation of one claim gets wrong: its standing, its rung, its regime."""
    cited = claim.id
    found: list[str] = []
    if not claim.adoptable_for_routing:
        found.append(
            f"{where} cites '{cited}', whose verdict is '{claim.verdict}' on '{claim.basis}', "
            f"not 'worthwhile' on records"
        )
    if not_valid is not None:
        found.append(f"{where} cites '{cited}', which is {not_valid}")
    if claim.rung != rule.then:
        found.append(
            f"{where} routes to '{rule.then}' but cites '{cited}', a claim about '{claim.rung}'"
        )
    found.extend(
        f"{where} does not carry the regime of '{cited}': {predicate.feature} {predicate.op} "
        f"{predicate.value}"
        for predicate in claim.regime
        if not any(implies(condition, predicate) for condition in rule.when)
    )
    return found


def _unknown_claim(where: str, cited: str, rule: PolicyRule, claims: Mapping[str, Claim]) -> str:
    """The refusal for a claim no loaded claim document states, naming the ones that would do."""
    usable = sorted(
        claim.id
        for claim in claims.values()
        if claim.rung == rule.then and claim.adoptable_for_routing
    )
    options = ", ".join(usable) if usable else f"(none about '{rule.then}')"
    return f"{where} cites '{cited}', which is not a known claim. Claims you could cite: {options}."


def _rule_violations(
    document: str,
    rule: PolicyRule,
    *,
    default: bool,
    claims: Mapping[str, Claim],
    generating_roles: Mapping[str, str | None] | None,
    not_valid: Mapping[str, str],
) -> list[str]:
    where = f"{document}: rule '{rule.name}'"
    found: list[str] = (
        [] if generating_roles is None else _fit_violations(where, rule, generating_roles)
    )
    for condition in rule.when:
        if not is_declared_feature(condition.feature):
            found.append(f"{where} tests '{condition.feature}', which no profiler declares")
    populations: set[frozenset[str]] = set()
    for cited in rule.cites:
        claim = claims.get(cited)
        if claim is None:
            found.append(_unknown_claim(where, cited, rule, claims))
            continue
        populations.add(frozenset(claim.population.question_sets))
        found.extend(_claim_violations(where, rule, claim, not_valid.get(cited)))
    if default and len(populations) < 2 and all(cited in claims for cited in rule.cites):
        found.append(
            f"{where} is a default and cites claims from {len(populations)} population(s); a "
            f"default needs two"
        )
    return found


def policy_violations(
    documents: Mapping[str, EvidencePolicyConfig],
    claims: Sequence[Claim],
    *,
    generating_roles: Mapping[str, str | None] | None,
    not_valid: Mapping[str, str],
    waived: frozenset[tuple[str, str]] = _NO_WAIVERS,
) -> list[str]:
    """Every way an evidence-policy document's rules fail to be supported by `claims`.

    `documents` is keyed by whatever names the document in a message. `not_valid` maps a claim id to
    why it is not `valid` against the running tree, and omits the ones that are. `generating_roles`
    is the role each rung writes its answer under; `None` skips the context-fit check, for a caller
    that has not resolved the rungs. `waived` is `(document, rule name)` pairs exempt from every
    check.
    """
    by_id = {claim.id: claim for claim in claims}
    found: list[str] = []
    for document, config in sorted(documents.items()):
        for rules, default in ((config.exceptions, False), (config.defaults, True)):
            for rule in rules:
                if (document, rule.name) in waived:
                    continue
                found.extend(
                    _rule_violations(
                        document,
                        rule,
                        default=default,
                        claims=by_id,
                        generating_roles=generating_roles,
                        not_valid=not_valid,
                    )
                )
    return found


__all__ = ["implies", "policy_violations"]
