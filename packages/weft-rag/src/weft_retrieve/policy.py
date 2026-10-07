"""`evidence-policy` — a routing policy whose every rule cites the claim that justifies it.

A rule is a `weft_retrieve.routing.Condition` list, a rung, the evidence claims behind it and what
the rung costs a prompt. Rules are tried first-match, `exceptions` before `defaults`; one that holds
but cannot be used — its rung is not offered, or its cost breaks a `constraints` ceiling — is
skipped and the reason is recorded in `Route.reasons`, so a decision is auditable from the route
alone. When nothing is usable the `fallback` is taken, and a fallback that is not offered is
refused naming the rungs that are: there is no silent third answer.

The policy stays a pure function of a `Scorecard` and the route catalogue — no model call, no
embedder — so it satisfies `cost_bound = (0, 0)` exactly as `threshold-ladder` does.
"""

import hashlib
import json
from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_retrieve.contract import RouteCatalogue
from weft_retrieve.payload import Route, RouteCandidate, RuleOutcome, Scorecard
from weft_retrieve.routing import (
    Condition,
    condition_holds,
    unknown_condition_name,
    unknown_name_reason,
)

EVIDENCE_POLICY_NAME = "evidence-policy"

CORPUS_LEAF_TOKENS = "corpus.leaf_tokens"


def _unmet(condition: Condition, card: Scorecard) -> str:
    name = condition.feature
    observed = card.scores.get(name, card.features.get(name))
    seen = "unknown" if observed is None else str(observed)
    return f"{name} is {seen}, the rule needs {condition.op} {condition.value}"


class PromptCost(StrEnum):
    """A rung's prompt cost that is not a fixed number."""

    CORPUS = "corpus"


class PolicyRule(BaseModel):
    """One rule: when every condition holds, route to `then`, on the strength of `cites`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    when: tuple[Condition, ...] = Field(min_length=1)
    then: str = Field(min_length=1)
    cites: tuple[str, ...] = Field(min_length=1)
    prompt_tokens: Annotated[int, Field(ge=0)] | PromptCost | None = None
    model_calls: int | None = Field(default=None, ge=0)


class PolicyConstraints(BaseModel):
    """Ceilings a rule's cost must stay under for the rule to be usable; `None` is no ceiling."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_prompt_tokens: int | None = Field(default=None, ge=0)
    max_model_calls: int | None = Field(default=None, ge=0)


class EvidencePolicyConfig(BaseModel):
    """The rule lists, the fallback rung and the cost ceilings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exceptions: tuple[PolicyRule, ...] = ()
    defaults: tuple[PolicyRule, ...] = ()
    fallback: str = Field(min_length=1)
    constraints: PolicyConstraints = PolicyConstraints()

    @model_validator(mode="after")
    def _rule_names_are_distinct(self) -> "EvidencePolicyConfig":
        names = [rule.name for rule in (*self.exceptions, *self.defaults)]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(
                f"EvidencePolicyConfig rule names must be distinct across exceptions and "
                f"defaults; {', '.join(repeated)} repeats."
            )
        return self


class EvidencePolicy:
    """First-match routing over rules that each cite evidence. Satisfies `RoutingPolicy`."""

    config_model: ClassVar[type[EvidencePolicyConfig]] = EvidencePolicyConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: EvidencePolicyConfig) -> None:
        self._config = config
        canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True)
        self.digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def _rules(self) -> tuple[PolicyRule, ...]:
        return (*self._config.exceptions, *self._config.defaults)

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]:
        """The first usable rule's rung, else the fallback, else a refusal naming the offered."""
        unknown = unknown_condition_name(
            (condition for rule in self._rules for condition in rule.when), payload
        )
        if unknown is not None:
            return Failed(reason=unknown_name_reason(EVIDENCE_POLICY_NAME, unknown, payload))
        catalogue = ctx.require(RouteCatalogue)
        offered = catalogue.names()
        receipt = self._receipt(payload)
        skipped: list[str] = []
        for rule in self._rules:
            failed = next((c for c in rule.when if not condition_holds(c, payload)), None)
            if failed is not None:
                skipped.append(f"rule '{rule.name}' did not hold: {_unmet(failed, payload)}")
                continue
            problem = self._problem_with(rule, payload, offered, catalogue)
            if problem is not None:
                skipped.append(f"rule '{rule.name}' held but was skipped: {problem}")
                continue
            return Produced(
                value=Route(
                    pipeline=rule.then,
                    outcome=RuleOutcome.MATCHED,
                    rule=rule.name,
                    scorecard=payload,
                    reasons=(*skipped, f"rule '{rule.name}' held, routing to '{rule.then}'"),
                    claims=rule.cites,
                    fallback=self._fallback_for(rule.then, offered),
                    **receipt,
                )
            )
        fallback = self._config.fallback
        if fallback not in offered:
            return Failed(
                reason=(
                    f"'{EVIDENCE_POLICY_NAME}' found no usable rule and its fallback "
                    f"'{fallback}' is not offered. "
                    f"Offered: {', '.join(sorted(offered)) or '(none)'}."
                    + "".join(f" {reason}." for reason in skipped)
                )
            )
        return Produced(
            value=Route(
                pipeline=fallback,
                outcome=RuleOutcome.FELL_THROUGH,
                scorecard=payload,
                reasons=(*skipped, f"no rule was usable, so the fallback '{fallback}' answers"),
                **receipt,
            )
        )

    def _receipt(self, card: Scorecard) -> dict[str, Any]:
        """What a reader needs to say why: facts judged, unknowns, ceilings and the policy."""
        tested = dict.fromkeys(condition.feature for rule in self._rules for condition in rule.when)
        return {
            "facts": {name: card.features[name] for name in tested if name in card.features},
            "unstated": tuple(name for name in tested if name not in card.features),
            "constraints": self._config.constraints.model_dump(exclude_none=True),
            "policy": self.digest,
        }

    def _fallback_for(self, chosen: str, offered: frozenset[str]) -> str | None:
        fallback = self._config.fallback
        return fallback if fallback != chosen and fallback in offered else None

    def _problem_with(
        self, rule: PolicyRule, card: Scorecard, offered: frozenset[str], catalogue: RouteCatalogue
    ) -> str | None:
        if rule.then not in offered:
            return (
                f"rung '{rule.then}' is not offered{self._withheld_because(catalogue, rule.then)}"
            )
        ceiling = self._config.constraints.max_prompt_tokens
        if ceiling is not None and rule.prompt_tokens is not None:
            cost = self._prompt_cost(rule.prompt_tokens, card)
            if cost is None:
                return f"its prompt cost, the corpus size, is unknown (max_prompt_tokens {ceiling})"
            if cost > ceiling:
                return f"its prompt cost {cost} exceeds max_prompt_tokens {ceiling}"
        calls = self._config.constraints.max_model_calls
        if calls is not None and rule.model_calls is not None and rule.model_calls > calls:
            return f"its {rule.model_calls} model calls exceed max_model_calls {calls}"
        return None

    @staticmethod
    def _withheld_because(catalogue: RouteCatalogue, rung: str) -> str:
        """`: <reason>` when the catalogue kept one for leaving `rung` out, else nothing.

        `withheld_reason` is an optional capability of a catalogue, read the way a policy reads any
        optional one, so the `RouteCatalogue` contract and its version do not move.
        """
        why = getattr(catalogue, "withheld_reason", None)
        reason = why(rung) if callable(why) else None
        return f", because {reason}" if isinstance(reason, str) else ""

    @staticmethod
    def _prompt_cost(cost: int | PromptCost, card: Scorecard) -> int | None:
        if cost is PromptCost.CORPUS:
            tokens = card.features.get(CORPUS_LEAF_TOKENS)
            return int(tokens) if tokens is not None else None
        return cost

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]:
        """Every rung a rule or the fallback names, whether or not it is installed."""
        del candidates
        return frozenset(rule.then for rule in self._rules) | {self._config.fallback}
