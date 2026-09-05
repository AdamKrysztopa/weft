"""Unit tests for `weft_retrieve.iterative`.

Mirrors `packages/weft-rag/src/weft_retrieve/iterative.py`. Ledger **2.20**: "an
evidence-sufficiency loop is expressible, and its stopping rule is one named, testable thing
rather than four scattered breaks." The task line names what this module has to prove, and
this file is organised around it rather than around the plugin's method list:

1. `stop_reason` is tested **directly**, with hand-built `LoopState`s, never by running the
   loop — the whole point of "testable on its own" is that a reader (or a reviewer) does not
   have to drive `IterativeRetrieval.run` through two fake services to know what stops it.
   `test_stop_reason_*` covers all four named reasons plus the "keep going" case, one branch
   at a time, in the priority order the function's own docstring states.
2. The loop itself is covered separately: the happy path (insufficient, then sufficient, the
   next round's query built from what the critic said was missing), the edge case
   (`NO_NEW_EVIDENCE` stops the loop before `max_rounds` when a leaf keeps handing back the
   same passage), the error case (`on_critic_failure = FAIL` propagates a hard critic failure
   rather than silently treating any non-empty context as complete), and a drive through
   `weft_kernel.seam.wrap`.
3. `test_the_loop_never_exceeds_max_rounds` is the "cannot spin forever" property from the
   task's own framing, checked as a fact about call counts against a critic that always says
   "not yet" — not inferred from `stop_reason`'s own correctness, which the `for` loop's own
   `range(1, max_rounds + 1)` bound does not depend on.
4. `test_min_rounds_forces_a_further_round_even_once_the_critic_is_satisfied` checks the
   `.phase2-design.md` §10 row naming this failure mode — `min_loops=2` forcing a second round
   "even when the critic said stop" — checked with the fix's default (`min_rounds=1`, which
   forces nothing) and with an operator who explicitly asks for a floor.

`leaf` and `sufficiency` are both stubs reached through a `_StubLookup`, never a real
`vector-top-k` or `llm-sufficiency` — this task's own scope is `weft_retrieve/iterative.py`,
and `llm-sufficiency` is task 2.24's (`.phase2-design.md`'s task map, the `2.24` row: `weft_
generate/refine.py` + the `Sufficiency` contract + `llm-sufficiency` / `hedge-phrases`).
Exercising the real `vector-top-k` here would test that plugin a second time and this one not
at all — `IterativeRetrieval` never inspects what `leaf` or `sufficiency` are, only what they
answer.

`out.origin == in.origin` is asserted, never assumed — the same obligation every query-path
plugin in this pack's own test suite carries (`weft_retrieve.contract.QuerySet.origin`'s own
docstring, `weft_retrieve.transforms`'s and `weft_retrieve.rerank`'s own test modules).
"""

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.seam import wrap
from weft_llm.payload import OnFailure
from weft_retrieve.contract import Retriever, StageLookup, Sufficiency
from weft_retrieve.iterative import (
    NAME,
    IterativeRetrieval,
    IterativeRetrievalConfig,
    LoopState,
    StopReason,
    stop_reason,
)
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Passage,
    Passages,
    Query,
    QueryOrigin,
    QuerySet,
    RankedList,
)
from weft_store.contract import Scored


def _assessment(
    *, sufficient: bool, observed: bool = True, missing: tuple[str, ...] = ()
) -> Assessment:
    return Assessment(sufficient=sufficient, confidence=0.5, missing=missing, observed=observed)


def _state(
    *,
    round: int = 1,
    min_rounds: int = 1,
    max_rounds: int = 3,
    sufficient: bool = False,
    observed: bool = True,
    gained_new_evidence: bool = True,
) -> LoopState:
    return LoopState(
        round=round,
        min_rounds=min_rounds,
        max_rounds=max_rounds,
        assessment=_assessment(sufficient=sufficient, observed=observed),
        gained_new_evidence=gained_new_evidence,
    )


# --------------------------------------------------------------------------------------
# `stop_reason` — the stopping rule, tested directly.
# --------------------------------------------------------------------------------------


def test_stop_reason_reports_critic_unobserved_before_anything_else() -> None:
    # Arrange — a critic that could not look, even before the operator's own `min_rounds`
    # floor is satisfied. Forcing more rounds against a critic with nothing to say about
    # them would not make the signal more honest, only later.
    state = _state(round=1, min_rounds=3, observed=False)

    # Act
    reason = stop_reason(state)

    # Assert
    assert reason is StopReason.CRITIC_UNOBSERVED


def test_stop_reason_keeps_going_below_the_min_rounds_floor_even_when_sufficient() -> None:
    # Arrange — the `min_rounds` floor, checked the other way round: a floor an operator set
    # is honoured even past a critic that already said `sufficient=True`.
    state = _state(round=1, min_rounds=2, max_rounds=3, sufficient=True)

    # Act
    reason = stop_reason(state)

    # Assert — `None` means "keep going", not a fifth `StopReason` member.
    assert reason is None


def test_stop_reason_reports_sufficient_once_past_the_floor() -> None:
    state = _state(round=1, min_rounds=1, sufficient=True)

    reason = stop_reason(state)

    assert reason is StopReason.SUFFICIENT


def test_stop_reason_reports_max_rounds_at_the_ceiling() -> None:
    # Arrange — not sufficient, the ceiling reached. Named by the function rather than left
    # for the caller to infer from the `for` loop simply running out.
    state = _state(round=3, max_rounds=3, sufficient=False, gained_new_evidence=True)

    reason = stop_reason(state)

    assert reason is StopReason.MAX_ROUNDS


def test_stop_reason_reports_no_new_evidence_before_the_ceiling() -> None:
    # Arrange — under the ceiling, not sufficient, and this round added nothing the loop
    # had not already seen. Continuing would pay for another round the critic's opinion has
    # no new evidence to change.
    state = _state(round=2, max_rounds=5, sufficient=False, gained_new_evidence=False)

    reason = stop_reason(state)

    assert reason is StopReason.NO_NEW_EVIDENCE


def test_stop_reason_keeps_going_when_none_of_the_four_conditions_hold() -> None:
    state = _state(round=1, max_rounds=3, sufficient=False, gained_new_evidence=True)

    reason = stop_reason(state)

    assert reason is None


# --------------------------------------------------------------------------------------
# `IterativeRetrievalConfig` — every knob defaults, and the floor cannot exceed the ceiling.
# --------------------------------------------------------------------------------------


def test_config_is_constructible_with_no_fields_supplied() -> None:
    config = IterativeRetrievalConfig()

    assert config.max_rounds == 3
    assert config.min_rounds == 1
    assert config.sufficiency == "llm-sufficiency"
    assert config.sufficiency_config is None
    assert config.leaf == "vector-top-k"
    assert config.leaf_config is None
    assert config.on_critic_failure is OnFailure.FAIL
    assert config.accumulate is True


def test_config_refuses_a_floor_above_the_ceiling() -> None:
    with pytest.raises(ValidationError, match="min_rounds"):
        IterativeRetrievalConfig(min_rounds=4, max_rounds=3)


# --------------------------------------------------------------------------------------
# Fakes for the loop itself — a scripted `Retriever` and a scripted `Sufficiency`, reached
# through a `StageLookup` stub. Neither is the real `vector-top-k` or `llm-sufficiency` —
# see the module docstring for why.
# --------------------------------------------------------------------------------------


def _passage(content: str, retrieved_by: str = "leaf") -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(scored=Scored(value=node, score=1.0), rank=0, retrieved_by=retrieved_by)


def _candidates(origin: Query, query: Query, *contents: str) -> Candidates:
    hits = tuple(_passage(content) for content in contents)
    return Candidates(origin=origin, lists=(RankedList(query=query, retriever="leaf", hits=hits),))


class _FakeLeaf:
    """A `Retriever`-shaped callable, scripted one `Outcome[Candidates]` per call.

    The last entry repeats for any call beyond the script's length, so a test that only
    cares about the first two rounds does not have to script every round up to
    `max_rounds`.
    """

    def __init__(self, outcomes: list[Outcome[Candidates]]) -> None:
        self._outcomes = outcomes
        self.calls: list[QuerySet] = []

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        self.calls.append(payload)
        return self._outcomes[min(len(self.calls) - 1, len(self._outcomes) - 1)]


class _FakeSufficiency:
    """A `Sufficiency`, scripted one `Outcome[Assessment]` per call — same repeat-last shape
    as `_FakeLeaf`."""

    def __init__(self, outcomes: list[Outcome[Assessment]]) -> None:
        self._outcomes = outcomes
        self.calls: list[Passages] = []

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]:
        del question, draft, ctx
        self.calls.append(evidence)
        return self._outcomes[min(len(self.calls) - 1, len(self._outcomes) - 1)]


class _StubLookup:
    """A `StageLookup` handing back exactly one scripted leaf and one scripted critic.

    Asserts the *contract* it was asked to build, the same shape the real registry-backed
    implementation would refuse an unregistered name by — see `weft_retrieve.rerank`'s own
    `_StubLookup` docstring for why nothing in the pack under test needs to prove that
    refusal itself.
    """

    def __init__(self, leaf: _FakeLeaf, sufficiency: _FakeSufficiency) -> None:
        self._leaf = leaf
        self._sufficiency = sufficiency
        self.asked: list[tuple[str, str]] = []
        # What `config` each call actually carried — never discarded, since the whole point
        # of the finding this stub now proves is that a config a calling plugin passed must
        # reach here rather than defaulting to `None` regardless of what was configured.
        self.leaf_config: object = None
        self.sufficiency_config: object = None

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset()

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        assert contract is Retriever
        self.asked.append(("build", name))
        self.leaf_config = config
        return self._leaf.run

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        assert contract is Sufficiency
        self.asked.append(("build_capability", name))
        self.sufficiency_config = config
        return self._sufficiency


def _services(leaf: _FakeLeaf, sufficiency: _FakeSufficiency) -> ServiceRegistry:
    services = ServiceRegistry()
    services.add(StageLookup, _StubLookup(leaf, sufficiency))
    return services


def _ctx(services: ServiceRegistry) -> Context:
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _asked() -> Query:
    return Query(text="what caused the 2003 blackout?")


# --------------------------------------------------------------------------------------
# The loop.
# --------------------------------------------------------------------------------------


async def test_the_loop_stops_once_the_critic_says_sufficient() -> None:
    # Arrange — round 1 finds one passage and the critic says it is not enough, naming what
    # is missing; round 2's leaf call is asked with a query built from that, and the critic
    # is satisfied with what round 2 adds.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf(
        [
            Produced(value=_candidates(origin, origin, "the grid overloaded")),
            Produced(
                value=_candidates(
                    origin, Query(text="which utility operated the failed line?"), "FirstEnergy"
                )
            ),
        ]
    )
    sufficiency = _FakeSufficiency(
        [
            Produced(
                value=_assessment(
                    sufficient=False, missing=("which utility operated the failed line",)
                )
            ),
            Produced(value=_assessment(sufficient=True)),
        ]
    )

    # Act
    outcome = await IterativeRetrieval().run(q1, _ctx(_services(leaf, sufficiency)))

    # Assert
    assert isinstance(outcome, Produced)
    candidates = outcome.value
    assert candidates.origin == origin
    assert len(leaf.calls) == 2
    assert len(sufficiency.calls) == 2
    # round 2's leaf call carries a derived query built from what round 1 said was missing.
    second_round = leaf.calls[1]
    assert second_round.queries[0].origin is QueryOrigin.DERIVED
    assert "operated the failed line" in second_round.queries[0].text
    # both rounds' hits survive — `accumulate` defaults `True`.
    contents = [passage.node.content for ranked in candidates.lists for passage in ranked.hits]
    assert contents == ["the grid overloaded", "FirstEnergy"]


async def test_no_new_evidence_stops_the_loop_before_max_rounds() -> None:
    # Arrange — the leaf hands back the exact same passage every round, and the critic
    # never says sufficient. Nothing new is learned, so the loop stops itself rather than
    # spending every round `max_rounds` allows for.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "the same passage every time"))])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=False))])

    # Act
    outcome = await IterativeRetrieval(IterativeRetrievalConfig(max_rounds=5)).run(
        q1, _ctx(_services(leaf, sufficiency))
    )

    # Assert
    assert isinstance(outcome, Produced)
    # round 1 has nothing to compare against, so it gains evidence; round 2 repeats the same
    # passage and gains none — the loop stops there, not at the configured ceiling of 5.
    assert len(leaf.calls) == 2
    assert len(sufficiency.calls) == 2


async def test_a_hard_critic_failure_fails_the_whole_retrieval() -> None:
    # Arrange — `on_critic_failure` defaults `FAIL`: treating a failed critique call as "the
    # context is complete" and silently downgrading to single-shot would hide the failure
    # behind a plausible-looking result. This asserts the fix: the loop does not manufacture
    # a result at all.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "some evidence"))])
    sufficiency = _FakeSufficiency([Failed(reason="the critic's own model call raised")])

    # Act
    outcome = await IterativeRetrieval().run(q1, _ctx(_services(leaf, sufficiency)))

    # Assert
    assert isinstance(outcome, Failed)
    assert "critic" in outcome.reason


async def test_leaf_and_sufficiency_config_reach_stagelookup_build() -> None:
    # Arrange — the finding this proves: `vector-top-k` (the default `leaf`) is a richly
    # configured plugin (`top_k`, `per_query_top_k`, `channels`), and running the same leaf
    # twice with different settings is requirement 6's second clause applied to this loop.
    # `StageLookup.build`/`build_capability`'s own `config` parameter exists precisely so a
    # calling plugin can pass configuration through — a knob a pipeline author can reach only
    # if this config model has somewhere to hold it.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "hit"))])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=True))])
    lookup = _StubLookup(leaf, sufficiency)
    services = ServiceRegistry()
    services.add(StageLookup, lookup)
    config = IterativeRetrievalConfig(
        leaf_config={"top_k": 5}, sufficiency_config={"threshold": 0.9}
    )

    # Act
    outcome = await IterativeRetrieval(config).run(q1, _ctx(services))

    # Assert — the exact mapping supplied on the config model is what `StageLookup` saw,
    # not `None`.
    assert isinstance(outcome, Produced)
    assert lookup.leaf_config == {"top_k": 5}
    assert lookup.sufficiency_config == {"threshold": 0.9}


async def test_the_loop_never_exceeds_max_rounds() -> None:
    # Arrange — a critic that always says "not yet" and evidence that always changes, so
    # nothing but the configured ceiling can stop this loop. This is the "cannot spin
    # forever" property itself: bounded by the `for` loop's own range, not by `stop_reason`
    # happening to be correct.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf(
        [Produced(value=_candidates(origin, origin, f"passage {index}")) for index in range(10)]
    )
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=False))])

    # Act
    outcome = await IterativeRetrieval(IterativeRetrievalConfig(max_rounds=4)).run(
        q1, _ctx(_services(leaf, sufficiency))
    )

    # Assert — never more than the configured ceiling, and the ceiling is named.
    assert isinstance(outcome, Produced)
    assert len(leaf.calls) == 4
    assert len(sufficiency.calls) == 4


async def test_min_rounds_forces_a_further_round_even_once_the_critic_is_satisfied() -> None:
    # Arrange — the `min_rounds` floor, checked from the fixed side: an operator who wants
    # at least two rounds gets them, even though the critic is satisfied after the first.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf(
        [
            Produced(value=_candidates(origin, origin, "first")),
            Produced(value=_candidates(origin, origin, "second")),
        ]
    )
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=True))])

    # Act
    outcome = await IterativeRetrieval(IterativeRetrievalConfig(min_rounds=2)).run(
        q1, _ctx(_services(leaf, sufficiency))
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert len(leaf.calls) == 2


async def test_the_default_min_rounds_forces_nothing() -> None:
    # Arrange — the fix, not just the flag: `min_rounds=1` is the default, and it forces no
    # second round the way a hardcoded floor of two always did.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "enough on its own"))])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=True))])

    # Act
    outcome = await IterativeRetrieval().run(q1, _ctx(_services(leaf, sufficiency)))

    # Assert
    assert isinstance(outcome, Produced)
    assert len(leaf.calls) == 1


async def test_critic_unobserved_stops_the_loop_and_names_the_reason() -> None:
    # Arrange — the critic ran but had nothing it could judge (`observed=False`), which is
    # a different fact from `sufficient=False` — `Assessment`'s own docstring's distinction,
    # checked here rather than assumed.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "something"))])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=False, observed=False))])

    # Act
    outcome = await IterativeRetrieval().run(q1, _ctx(_services(leaf, sufficiency)))

    # Assert — stopped after one round, not run to the (default) ceiling of three.
    assert isinstance(outcome, Produced)
    assert len(leaf.calls) == 1


async def test_a_leaf_that_declines_to_act_is_relayed_exactly_as_it_answered() -> None:
    # Arrange — a leaf answering `NothingToProduce` mid-loop is not synthesised into an
    # empty round and continued past; it is relayed, exactly as every other query-path
    # plugin in this pack relays a sub-call's own refusal.
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([NothingToProduce(reason="the configured leaf declined this round")])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=True))])

    # Act
    outcome = await IterativeRetrieval().run(q1, _ctx(_services(leaf, sufficiency)))

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert sufficiency.calls == []


async def test_driving_iterative_retrieval_through_the_seam_produces_candidates() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives. Same structural shape as `test_vector_top_k.py`'s own seam
    test."""
    # Arrange
    origin = _asked()
    q1 = QuerySet(origin=origin, queries=(origin,))
    leaf = _FakeLeaf([Produced(value=_candidates(origin, origin, "hit"))])
    sufficiency = _FakeSufficiency([Produced(value=_assessment(sufficient=True))])
    retriever = IterativeRetrieval()
    wrapped = wrap(retriever.run, distribution="weft-retrieve", contract="Retriever", plugin=NAME)

    # Act
    outcome = await wrapped(q1, _ctx(_services(leaf, sufficiency)))

    # Assert
    assert isinstance(outcome, Produced)
    assert isinstance(retriever, Retriever)


def test_the_declared_cost_bound_is_one_and_unbounded() -> None:
    # Act / Assert — `(1, -1)`: a floor of one (the leaf's own floor plus the critic's one
    # call are not zero even in the best case), an unbounded ceiling because the leaf is
    # resolved by name and could be anything — bounded in practice by `max_rounds`, which is
    # what the config's own default states rather than what this tuple can.
    assert IterativeRetrieval.cost_bound == (1, -1)
