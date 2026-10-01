"""Fitness function 38 — every rule of a shipped `evidence-policy` router cites evidence that holds.

`fix-plans/23` MUST-3: a routing rule is only as good as the measurement behind it, and a rule that
names a claim in prose is a rule nobody can tell is still supported. For every tracked first-party
pipeline document with a stage using `evidence-policy`, each rule must satisfy all of:

- it cites at least one claim, and every cited claim exists in `eval/claims/`;
- each cited claim's verdict is one routing adopts (`worthwhile`, on records), so a positive
  effect below its pre-registered margin never becomes a routing rule;
- each cited claim's `rung` is the rule's `then`;
- the rule's `when` contains every regime predicate of each cited claim, equal or tighter, so the
  rule never fires where the evidence does not reach;
- each cited claim is `valid` against the running tree (`weft_eval.fingerprint`): pinned, and no
  pipeline, judge prompt or profiler it was validated against has changed since — so a change to
  a rung's stages turns this red until the evidence is re-measured or consciously re-pinned;
- the rule tests only declared profiler features — what a claim was measured on (`population`) is
  never something a rule can name;
- a rule testing a context-fit feature tests the one for the role its rung's answer is generated
  under — `corpus.fits_context` for `generate`, `corpus.fits_context.<role>` otherwise — because
  a corpus that fits one role's window says nothing about another's (R44.20b);
- a rule under `defaults` cites claims from at least two distinct populations (D9), because a rule
  keyed to one benchmark wins there and nowhere else; an `exceptions` rule needs one.

The waiver constant is pinned empty: a waiver is a visible act in a diff.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast
from unittest import mock

import yaml

from weft_cli.claims_live import live_evidence
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.route_ask import resolve_in_catalogue
from weft_engine import registry_bootstrap
from weft_eval import eligibility
from weft_eval.claims import Claim, load_claims
from weft_eval.claims_check import check_claim
from weft_eval.fingerprint import Staleness
from weft_generate.generating_role import generating_role
from weft_retrieve.policy import EvidencePolicyConfig
from weft_retrieve.profile import fits_context_role

from .conftest import REPO_ROOT, tracked_files

_RESOLUTION_ONLY_DSN: Final[str] = "postgresql://nobody@localhost:1/none"

#: `(document stem, rule name)` pairs exempt from the check. Empty, and pinned empty below.
RULES_WAIVED: Final[frozenset[tuple[str, str]]] = frozenset()


def policy_violations(
    documents: Mapping[str, EvidencePolicyConfig],
    claims: Sequence[Claim],
    *,
    generating_roles: Mapping[str, str | None],
    not_valid: Mapping[str, str],
) -> list[str]:
    """`eligibility.policy_violations` with this gate's waivers, which are pinned empty."""
    return eligibility.policy_violations(
        documents,
        claims,
        generating_roles=generating_roles,
        not_valid=not_valid,
        waived=RULES_WAIVED,
    )


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


def shipped_generating_roles(
    documents: Mapping[str, EvidencePolicyConfig],
) -> dict[str, str | None]:
    """The role each rung a shipped policy routes to writes its answer under, resolved for real."""
    rungs = {
        rule.then
        for config in documents.values()
        for rule in (*config.exceptions, *config.defaults)
    }
    with tempfile.TemporaryDirectory() as scratch:
        config_path = Path(scratch) / "weft.toml"
        config_path.write_text("", encoding="utf-8")
        previous = Path.cwd()
        os.chdir(scratch)
        try:
            deps = registry_bootstrap.build_dependencies(config_path=config_path)
            catalogue = full_catalogue(reports=deps.reports)
            return {
                rung: generating_role(
                    resolve_in_catalogue(
                        catalogue[rung],
                        registry=deps.registry,
                        catalogue=catalogue,
                        reports=deps.reports,
                        contributions=deps.contributions,
                    )
                )
                for rung in sorted(rungs)
            }
        finally:
            os.chdir(previous)


def shipped_staleness(
    documents: Mapping[str, EvidencePolicyConfig], claims: Sequence[Claim]
) -> dict[str, str]:
    """Why each claim a shipped rule cites is not `valid`, recomputed against the running tree."""
    cited = {
        name
        for config in documents.values()
        for rule in (*config.exceptions, *config.defaults)
        for name in rule.cites
    }
    by_id = {claim.id: claim for claim in claims}
    not_valid: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as scratch:
        config_path = Path(scratch) / "weft.toml"
        config_path.write_text("", encoding="utf-8")
        previous = Path.cwd()
        os.chdir(scratch)
        patcher = mock.patch.dict(os.environ, {"WEFT_DATABASE_URL": _RESOLUTION_ONLY_DSN})
        patcher.start()
        try:
            deps = registry_bootstrap.build_dependencies(config_path=config_path)
            for name in sorted(cited & set(by_id)):
                live = live_evidence(by_id[name], root=REPO_ROOT, deps=deps)
                check = check_claim(by_id[name], root=REPO_ROOT, live=live)
                if check.staleness is not Staleness.VALID:
                    not_valid[name] = f"{check.staleness}: {check.stale}"
        finally:
            patcher.stop()
            os.chdir(previous)
    return not_valid


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
    documents = shipped_policy_documents()
    claims = load_claims(REPO_ROOT / "eval" / "claims")
    found = policy_violations(
        documents,
        claims,
        generating_roles=shipped_generating_roles(documents),
        not_valid=shipped_staleness(documents, claims),
    )

    # Assert
    assert not found, "\n".join(found)


def _claim(
    claim_id: str = "c.one",
    *,
    rung: str = "whole",
    status: str = "helps",
    verdict: str = "worthwhile",
    sets: tuple[str, ...] = ("a.toml",),
) -> Claim:
    return Claim.model_validate(
        {
            "id": claim_id,
            "rung": rung,
            "baseline": "dense",
            "metric": "answer_correctness",
            "status": status,
            "verdict": verdict,
            "basis": "records",
            "margin": 0.05,
            "population": {"benchmark": "b", "language": "en", "question_sets": list(sets)},
            "source": {"experiment": "e.toml", "invocation": "i"},
            "regime": [
                {"feature": "corpus.base_complete", "op": "eq", "value": True},
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
    base_complete: bool = True,
) -> dict[str, EvidencePolicyConfig]:
    rule = {
        "name": "r",
        "when": [
            {"feature": "corpus.base_complete", "op": "eq", "value": base_complete},
            {"feature": feature, "op": "eq", "value": fits},
            {"feature": "corpus.leaf_tokens", "op": "lte", "value": tokens},
        ],
        "then": then,
        "cites": list(cites),
    }
    key = "defaults" if default else "exceptions"
    return {"planted": EvidencePolicyConfig.model_validate({"fallback": "dense", key: [rule]})}


def _found(
    config: dict[str, EvidencePolicyConfig],
    claims: list[Claim],
    roles: Mapping[str, str | None] | None = None,
    not_valid: Mapping[str, str] | None = None,
) -> str:
    return "\n".join(
        policy_violations(
            config,
            claims,
            generating_roles={"whole": "generate"} if roles is None else roles,
            not_valid={} if not_valid is None else not_valid,
        )
    )


def test_the_check_can_actually_fail() -> None:
    # Arrange
    one = _claim("c.one", sets=("a.toml",))
    two = _claim("c.two", sets=("b.toml",))

    # Act / Assert — the supported rule is clean, and each way of not being one is named.
    roles = {"whole": "generate"}
    assert policy_violations(_config(), [one, two], generating_roles=roles, not_valid={}) == []
    assert (
        policy_violations(
            _config(default=False, cites=("c.one",)), [one], generating_roles=roles, not_valid={}
        )
        == []
    )
    assert "which is definitely-stale: rung changed" in _found(
        _config(), [one, two], not_valid={"c.two": "definitely-stale: rung changed"}
    )
    assert "not a known claim" in _found(_config(cites=("c.nope",)), [one, two])
    assert "not 'worthwhile'" in _found(
        _config(),
        [one, _claim("c.two", status="no-gain", verdict="benefit-ruled-out", sets=("b.toml",))],
    )
    assert "'positive-below-margin'" in _found(
        _config(), [one, _claim("c.two", verdict="positive-below-margin", sets=("b.toml",))]
    )
    assert "does not carry the regime" in _found(_config(base_complete=False), [one, two])
    assert "a claim about 'other'" in _found(
        _config(), [one, _claim("c.two", rung="other", sets=("b.toml",))]
    )
    assert "does not carry the regime" in _found(_config(tokens=300000), [one, two])
    assert "does not carry the regime" in _found(_config(fits=False), [one, two])
    assert "a default needs two" in _found(_config(), [one, _claim("c.two", sets=("a.toml",))])
    assert "no profiler declares" in _found(_config(feature="benchmark.x"), [one, two])


def test_a_fit_feature_must_name_the_role_its_rung_generates_under() -> None:
    # Arrange
    one = _claim("c.one", sets=("a.toml",))
    two = _claim("c.two", sets=("b.toml",))
    small = _config(feature="corpus.fits_context.small")

    # Act / Assert — plain `corpus.fits_context` is `generate`'s; a rung under another role
    # states that role's feature, and a rung whose role cannot be read states neither.
    assert _found(_config(), [one, two], {"whole": "generate"}) == ""
    assert "generates under 'small'" in _found(_config(), [one, two], {"whole": "small"})
    assert "the fit under role 'small'" in _found(small, [one, two], {"whole": "generate"})
    assert "cannot be read" in _found(_config(), [one, two], {"whole": None})
    assert "cannot be read" in _found(_config(), [one, two], {})
    assert fits_context_role("corpus.fits_context") == "generate"


def test_the_shipped_policy_rung_generates_under_the_role_its_fit_names() -> None:
    # Arrange — the control that must hit: the real shipped rung resolves to a real role.
    documents = shipped_policy_documents()

    # Act
    roles = shipped_generating_roles(documents)

    # Assert
    assert roles["whole-corpus-wide-then-generate"] == "generate"
