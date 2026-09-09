"""Unit tests for `weft_retrieve.multi_retriever` — ledger task **11.2**.

Mirrors `packages/weft-rag/src/weft_retrieve/multi_retriever.py`. Covers the happy path (two
arms resolved by name, every list relabelled by the arm that produced it), the edge case of an
arm whose plugin returns several lists of its own, and two error cases that are genuinely
different failures — a name nothing registered as a `Retriever`, refused before any arm runs,
and two arms sharing a label, refused at config time.

**What this plugin is for, and why it is not `multi-arm`.** `multi-arm` fans out over *filters*
on one store and `hybrid` over the two arms of one store; neither reaches a second retrieval
*strategy*, and `product-direction.md`'s "several bases at once" has had no plugin at all. Two
retrievers cannot sit in sequence in a pipeline because they do not compose by type —
`Retriever` is `Stage[QuerySet, Candidates]`, so the second would be handed the first's output
rather than the query — which is the same documented exception to `10` §2.1 rule 5 that
`multi-arm` and `hybrid` already carry. The arity has to live inside one plugin.

**`needs_store` is not declared, and `weft_retrieve.iterative` is the precedent that settles
it.** That module's own docstring: a sub-plugin "is resolved by name at `run` time, not at
registration, so there is no store capability this class itself could state ahead of time."
Measured rather than assumed — `weft_cli.run_services._chain_of` walks a `StageSpec`'s `use:`
and its `fallback:` names and nothing else, so a plugin named inside a `with:` block is
invisible to `check_store_capabilities`, exactly as fitness function 16's own docstring says it
is invisible to reachability. That is a pre-existing property of every looping technique in
this pack, not something this task introduces, and the tests below do not pretend otherwise.

**So "before any stage runs" is asserted at the strength it can honestly hold**: every arm's
name is resolved in one pass *before* any arm is dispatched, so a document with one bad name
does no retrieval at all rather than half of it and then a crash. That is a real property and
it is the one a naive implementation — resolve-and-run in a single loop — silently fails.
"""

from collections.abc import Mapping, Sequence

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import Failed, MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.registry import UnknownPluginError
from weft_retrieve.contract import Retriever, StageLookup
from weft_retrieve.fusion import contributor_label
from weft_retrieve.multi_retriever import (
    NAME,
    MultiRetriever,
    MultiRetrieverConfig,
    RetrieverArm,
)
from weft_retrieve.payload import Candidates, Passage, Query, QuerySet, RankedList
from weft_store.contract import Scored


class _StubRetriever:
    """A `Retriever` returning a fixed set of lists, and recording that it was asked."""

    def __init__(
        self,
        channels: Sequence[str] = ("",),
        *,
        fails: str | None = None,
        declines: str | None = None,
    ) -> None:
        self._channels = tuple(channels)
        self._fails = fails
        self._declines = declines
        self.calls = 0
        self.seen: list[QuerySet] = []

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]:
        del ctx
        self.calls += 1
        self.seen.append(payload)
        if self._fails is not None:
            return Failed(reason=self._fails)
        if self._declines is not None:
            return NothingToProduce(reason=self._declines)
        node = Node.synthetic(content="a passage", media_type=MediaType.TEXT, reason="test fixture")
        lists = tuple(
            RankedList(
                query=payload.queries[0],
                retriever="stub",
                channel=channel,
                hits=(Passage(scored=Scored(value=node, score=0.5), rank=0, retrieved_by="stub"),),
            )
            for channel in self._channels
        )
        return Produced(value=Candidates(origin=payload.origin, lists=lists))


class _StubLookup:
    """A `StageLookup` over a fixed table, raising the registry's own error for a miss.

    **`build` hands back the sub-plugin's `run`, not the sub-plugin.** That is what the real
    `weft_retrieve.engine.RegistryStageLookup.build` returns — `wrap(instance.run, ...)`, a
    plain callable with no `.run` attribute of its own — and it is what `test_iterative.py`
    and `test_corrective.py`'s own stubs already return. This docstring said "the stub
    itself" until the implementation came back blocked against it: a double written from the
    contract's docstring rather than from an existing double of the same seam is `L6.14`'s
    shape, and here it would have forced an implementation that could not run against the
    registry at all.
    """

    def __init__(self, retrievers: Mapping[str, _StubRetriever]) -> None:
        self._retrievers = retrievers
        self.asked: list[str] = []
        self.configs: list[object] = []

    def names(self, contract: type[object]) -> frozenset[str]:
        del contract
        return frozenset(self._retrievers)

    async def build(self, contract: type[object], name: str, config: object = None) -> object:
        assert contract is Retriever
        self.asked.append(name)
        self.configs.append(config)
        if name not in self._retrievers:
            raise UnknownPluginError(
                f"no distribution registered '{name}' for Retriever; "
                f"registered: {sorted(self._retrievers)}",
                valid_options=tuple(sorted(self._retrievers)),
            )
        return self._retrievers[name].run

    async def build_capability(
        self, contract: type[object], name: str, config: object = None
    ) -> object:
        raise AssertionError("this plugin resolves a stage by name, never a capability")


def _ctx(lookup: _StubLookup) -> Context:
    services = ServiceRegistry()
    services.add(StageLookup, lookup)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _queries() -> QuerySet:
    asked = Query(text="how does mRMR trade relevance against redundancy?")
    return QuerySet(origin=asked, queries=(asked,))


def _config(*arms: RetrieverArm) -> MultiRetrieverConfig:
    return MultiRetrieverConfig(arms=arms)


async def test_each_arm_is_resolved_by_name_and_its_lists_carry_the_arms_label() -> None:
    """The happy path: two retrievers, both run, every list addressable by arm."""
    # Arrange
    vector, graph = _StubRetriever(), _StubRetriever()
    lookup = _StubLookup({"vector-top-k": vector, "stub-graph": graph})
    payload = _queries()
    plugin = MultiRetriever(
        config=_config(
            RetrieverArm(name="vector", use="vector-top-k", config={"top_k": 5}),
            RetrieverArm(name="graph", use="stub-graph"),
        )
    )

    # Act
    outcome = await plugin.run(payload, _ctx(lookup))

    # Assert
    assert isinstance(outcome, Produced)
    candidates = outcome.value
    assert candidates.origin == payload.origin
    assert vector.calls == 1 and graph.calls == 1
    # Each arm is handed the queries, never another arm's output — the type is why this
    # plugin exists at all.
    assert vector.seen == [payload] and graph.seen == [payload]
    assert {contributor_label(ranked) for ranked in candidates.lists} == {
        f"{NAME}:vector",
        f"{NAME}:graph",
    }
    assert {ranked.retriever for ranked in candidates.lists} == {NAME}
    # An arm's `config` block has one job — travelling to `build`'s third argument — so the
    # call is captured rather than the field being read back off the model it was set on
    # (`L9.79`). `None` for the arm that stated none, which is what a real lookup then
    # validates into the sub-plugin's own defaults.
    assert lookup.asked == ["vector-top-k", "stub-graph"]
    assert lookup.configs == [{"top_k": 5}, None]


async def test_every_list_an_arm_returns_is_labelled_by_that_arm() -> None:
    """The edge case: an arm whose own plugin draws several channels.

    `hybrid` returns two lists per query and `multi-arm` returns one per arm, so an arm's
    contribution is not one list. All of them belong to that arm and take its label —
    weighting *within* an arm is the inner plugin's business, and an operator's `weights`
    mapping addresses arms.
    """
    # Arrange — one arm returning three lists, one returning one.
    wide, narrow = _StubRetriever(("a", "b", "c")), _StubRetriever()
    lookup = _StubLookup({"wide": wide, "narrow": narrow})
    plugin = MultiRetriever(
        config=_config(
            RetrieverArm(name="broad", use="wide"), RetrieverArm(name="exact", use="narrow")
        )
    )

    # Act
    outcome = await plugin.run(_queries(), _ctx(lookup))

    # Assert
    assert isinstance(outcome, Produced)
    labels = [contributor_label(ranked) for ranked in outcome.value.lists]
    assert labels.count(f"{NAME}:broad") == 3
    assert labels.count(f"{NAME}:exact") == 1


async def test_a_name_no_distribution_registered_is_refused_before_any_arm_runs() -> None:
    """The error case that carries this task's third clause.

    The first arm's name is good and the second's is not. A plugin resolving and running in
    one loop would have retrieved through the first before discovering the second, spending a
    search and returning nothing — so the assertion is on `calls`, not on the exception.
    """
    # Arrange
    good = _StubRetriever()
    lookup = _StubLookup({"vector-top-k": good})
    plugin = MultiRetriever(
        config=_config(
            RetrieverArm(name="vector", use="vector-top-k"),
            RetrieverArm(name="graph", use="graph-traverse"),
        )
    )

    # Act / Assert
    with pytest.raises(UnknownPluginError) as raised:
        await plugin.run(_queries(), _ctx(lookup))
    assert good.calls == 0
    assert "graph-traverse" in str(raised.value)
    assert raised.value.valid_options == ("vector-top-k",)


async def test_an_arm_that_fails_fails_the_retrieval_rather_than_returning_the_rest() -> None:
    """A partial fan-out is a plausible answer against incomplete evidence, which is the
    silent fallback `CLAUDE.md` refuses — so one arm's `Failed` is the whole outcome."""
    # Arrange
    healthy, broken = _StubRetriever(), _StubRetriever(fails="the graph store is unreachable")
    lookup = _StubLookup({"ok": healthy, "broken": broken})
    plugin = MultiRetriever(
        config=_config(RetrieverArm(name="a", use="ok"), RetrieverArm(name="b", use="broken"))
    )

    # Act
    outcome = await plugin.run(_queries(), _ctx(lookup))

    # Assert
    assert isinstance(outcome, Failed)
    assert "the graph store is unreachable" in outcome.reason
    assert "b" in outcome.reason


async def test_an_arm_that_declines_contributes_no_lists_and_the_others_still_run() -> None:
    """`NothingToProduce` is not `Failed`, and this plugin must not turn one into the other.

    `weft_kernel.payload.NothingToProduce` is "a legitimate result", and an arm reaching a
    base that holds nothing for this query has produced nothing rather than broken. Failing
    the whole fan-out on it would make one empty base silence every other one.
    """
    # Arrange
    empty = _StubRetriever(declines="this base holds nothing for that query")
    populated = _StubRetriever()
    lookup = _StubLookup({"empty": empty, "populated": populated})
    plugin = MultiRetriever(
        config=_config(
            RetrieverArm(name="graph", use="empty"), RetrieverArm(name="vector", use="populated")
        )
    )

    # Act
    outcome = await plugin.run(_queries(), _ctx(lookup))

    # Assert
    assert isinstance(outcome, Produced)
    assert empty.calls == 1 and populated.calls == 1
    assert [contributor_label(ranked) for ranked in outcome.value.lists] == [f"{NAME}:vector"]


async def test_every_arm_declining_still_produces_candidates_rather_than_stopping_the_run() -> None:
    """`Candidates`' own emptiness rule decides this, and it decides against `NothingToProduce`.

    That type's docstring: `Candidates(lists=())` says nothing was ever asked, and
    `NothingToProduce` "means the stage declined to act and stops the pipeline, which on a
    query path would mean no `Answer` at all, and `09` §4's V2 requires the engine to be able
    to answer 'not in this corpus.'" So a fan-out whose every arm found nothing produces an
    empty `Candidates` and lets `cited-answer` say so.
    """
    # Arrange
    first = _StubRetriever(declines="nothing here")
    second = _StubRetriever(declines="nothing here either")
    lookup = _StubLookup({"first": first, "second": second})
    plugin = MultiRetriever(
        config=_config(RetrieverArm(name="a", use="first"), RetrieverArm(name="b", use="second"))
    )

    # Act
    outcome = await plugin.run(_queries(), _ctx(lookup))

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.lists == ()


def test_two_arms_sharing_a_name_are_refused_at_config_time() -> None:
    """`multi-arm`'s own rule, for the same reason: a `Fuser` addresses an arm by its label,
    so two arms under one label leave an operator no key to weight them apart."""
    # Act / Assert
    with pytest.raises(ValidationError) as raised:
        _config(
            RetrieverArm(name="vector", use="vector-top-k"),
            RetrieverArm(name="vector", use="hybrid"),
        )
    assert "distinct names" in str(raised.value)


def test_one_arm_is_refused_because_it_is_the_retriever_spelled_the_long_way() -> None:
    """`multi-arm`'s rule again — a plugin whose whole purpose is arity, handed arity one, is
    a document mistake, and `02` §2 refuses those by name rather than tolerating them."""
    # Act / Assert
    with pytest.raises(ValidationError):
        _config(RetrieverArm(name="only", use="vector-top-k"))


def test_the_plugin_satisfies_the_retriever_contract_structurally() -> None:
    """Registered under `Retriever` like every other one — no privileged path (requirement 4)."""
    # Act / Assert
    assert isinstance(
        MultiRetriever(
            config=_config(
                RetrieverArm(name="a", use="vector-top-k"), RetrieverArm(name="b", use="hybrid")
            )
        ),
        Retriever,
    )
