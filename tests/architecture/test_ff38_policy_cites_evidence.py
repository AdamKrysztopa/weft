"""Fitness function 38 — every rule of a shipped `evidence-policy` router cites evidence that holds.

`fix-plans/23` MUST-3: a routing rule is only as good as the measurement behind it, and a rule that
names a claim in prose is a rule nobody can tell is still supported. For every tracked first-party
pipeline document with a stage using `evidence-policy`, each rule must satisfy all of:

- it cites at least one claim, and every cited claim exists in `eval/claims/`;
- each cited claim's `status` is `helps`;
- each cited claim's `rung` is the rule's `then`;
- the rule's `when` contains every regime predicate of each cited claim, equal or tighter, so the
  rule never fires where the evidence does not reach;
- the rule tests only declared profiler features — what a claim was measured on (`population`) is
  never something a rule can name;
- a rule under `defaults` cites claims from at least two distinct populations (D9), because a rule
  keyed to one benchmark wins there and nowhere else; an `exceptions` rule needs one.

The waiver constant is pinned empty: a waiver is a visible act in a diff.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

import yaml

from weft_eval.claims import Claim, load_claims
from weft_retrieve.policy import EvidencePolicyConfig, PolicyRule
from weft_retrieve.profile import is_declared_feature
from weft_retrieve.routing import Comparison, Condition

from .conftest import REPO_ROOT, tracked_files

#: `(document stem, rule name)` pairs exempt from the check. Empty, and pinned empty below.
RULES_WAIVED: Final[frozenset[tuple[str, str]]] = frozenset()

type _Interval = tuple[float, bool, float, bool]


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


def _rule_violations(
    document: str, rule: PolicyRule, *, default: bool, claims: Mapping[str, Claim]
) -> list[str]:
    where = f"{document}: rule '{rule.name}'"
    found: list[str] = []
    for condition in rule.when:
        if not is_declared_feature(condition.feature):
            found.append(f"{where} tests '{condition.feature}', which no profiler declares")
    populations: set[frozenset[str]] = set()
    for cited in rule.cites:
        claim = claims.get(cited)
        if claim is None:
            found.append(f"{where} cites '{cited}', which is not in eval/claims/")
            continue
        populations.add(frozenset(claim.population.question_sets))
        if claim.status.value != "helps":
            found.append(f"{where} cites '{cited}', whose status is '{claim.status}', not 'helps'")
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
    if default and len(populations) < 2 and all(cited in claims for cited in rule.cites):
        found.append(
            f"{where} is a default and cites claims from {len(populations)} population(s); a "
            f"default needs two"
        )
    return found


def policy_violations(
    documents: Mapping[str, EvidencePolicyConfig], claims: Sequence[Claim]
) -> list[str]:
    """Every way a shipped evidence-policy document's rules fail to be supported."""
    by_id = {claim.id: claim for claim in claims}
    found: list[str] = []
    for document, config in sorted(documents.items()):
        for rules, default in ((config.exceptions, False), (config.defaults, True)):
            for rule in rules:
                if (document, rule.name) in RULES_WAIVED:
                    continue
                found.extend(_rule_violations(document, rule, default=default, claims=by_id))
    return found


def shipped_policy_documents() -> dict[str, EvidencePolicyConfig]:
    """Every tracked first-party document with an `evidence-policy` stage, by stem."""
    documents: dict[str, EvidencePolicyConfig] = {}
    for tracked in sorted(tracked_files()):
        path = Path(tracked)
        if not (
            path.suffix == ".yaml"
            and path.parent.name == "pipelines"
            and path.parts[:2] == ("packages", "weft-rag")
        ):
            continue
        loaded: Any = yaml.safe_load((REPO_ROOT / tracked).read_text(encoding="utf-8"))
        stages = cast("list[dict[str, Any]]", loaded.get("stages") or [])
        for stage in stages:
            if stage.get("use") == "evidence-policy":
                documents[path.stem] = EvidencePolicyConfig.model_validate(stage.get("with") or {})
    return documents


def test_the_waiver_is_pinned_empty() -> None:
    assert frozenset() == RULES_WAIVED


def test_at_least_one_shipped_router_uses_evidence_policy_with_a_rule() -> None:
    # Floor — with no such document the check below passes by asking nothing.
    documents = shipped_policy_documents()
    assert any(config.defaults or config.exceptions for config in documents.values()), (
        "no tracked pipeline document has an evidence-policy stage with a rule, so FF38 would "
        "pass vacuously"
    )


def test_every_shipped_evidence_rule_cites_evidence_that_holds() -> None:
    # Act
    found = policy_violations(
        shipped_policy_documents(), load_claims(REPO_ROOT / "eval" / "claims")
    )

    # Assert
    assert not found, "\n".join(found)


def _claim(
    claim_id: str = "c.one",
    *,
    rung: str = "whole",
    status: str = "helps",
    sets: tuple[str, ...] = ("a.toml",),
) -> Claim:
    return Claim.model_validate(
        {
            "id": claim_id,
            "rung": rung,
            "baseline": "dense",
            "metric": "answer_correctness",
            "status": status,
            "basis": "records",
            "margin": 0.05,
            "population": {"benchmark": "b", "language": "en", "question_sets": list(sets)},
            "source": {"experiment": "e.toml", "invocation": "i"},
            "regime": [
                {"feature": "corpus.fits_context", "op": "eq", "value": True},
                {"feature": "corpus.leaf_tokens", "op": "lte", "value": 260000},
            ],
        }
    )


def _config(
    *,
    then: str = "whole",
    cites: tuple[str, ...] = ("c.one", "c.two"),
    tokens: int = 260000,
    fits: bool = True,
    default: bool = True,
    feature: str = "corpus.fits_context",
) -> dict[str, EvidencePolicyConfig]:
    rule = {
        "name": "r",
        "when": [
            {"feature": feature, "op": "eq", "value": fits},
            {"feature": "corpus.leaf_tokens", "op": "lte", "value": tokens},
        ],
        "then": then,
        "cites": list(cites),
    }
    key = "defaults" if default else "exceptions"
    return {"planted": EvidencePolicyConfig.model_validate({"fallback": "dense", key: [rule]})}


def _found(config: dict[str, EvidencePolicyConfig], claims: list[Claim]) -> str:
    return "\n".join(policy_violations(config, claims))


def test_the_check_can_actually_fail() -> None:
    # Arrange
    one = _claim("c.one", sets=("a.toml",))
    two = _claim("c.two", sets=("b.toml",))

    # Act / Assert — the supported rule is clean, and each way of not being one is named.
    assert policy_violations(_config(), [one, two]) == []
    assert policy_violations(_config(default=False, cites=("c.one",)), [one]) == []
    assert "not in eval/claims" in _found(_config(cites=("c.nope",)), [one, two])
    assert "not 'helps'" in _found(
        _config(), [one, _claim("c.two", status="no-gain", sets=("b.toml",))]
    )
    assert "a claim about 'other'" in _found(
        _config(), [one, _claim("c.two", rung="other", sets=("b.toml",))]
    )
    assert "does not carry the regime" in _found(_config(tokens=300000), [one, two])
    assert "does not carry the regime" in _found(_config(fits=False), [one, two])
    assert "a default needs two" in _found(_config(), [one, _claim("c.two", sets=("a.toml",))])
    assert "no profiler declares" in _found(_config(feature="benchmark.x"), [one, two])
