"""Unit tests for `weft_retrieve.no_retrieval`.

Mirrors `packages/weft-rag/src/weft_retrieve/no_retrieval.py`. Task **2.13**:
"the null case is a plugin like any other, and an empty source list is a stated property of
it rather than a retrieval failure a consumer has to guess at." Covers the happy path
(a `Candidates(lists=())` carrying the query's own origin), the edge case (the emptiness
holds regardless of how many queries were asked — the plugin never inspects `queries` at
all), the error case (a `with:` block is refused because this plugin declares no
`config_model` — there is nothing here to configure), and drives the plugin through
`weft_kernel.seam.wrap` — the group note against every task from 2.6 forward: a test calling
`NoRetrieval.run` directly never proves the plugin survives the one path a registered plugin
is actually called through.
"""

import pytest

from weft_kernel import resolution
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.seam import wrap
from weft_retrieve.contract import Retriever
from weft_retrieve.no_retrieval import NAME, NoRetrieval
from weft_retrieve.payload import Candidates, Query, QuerySet


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


async def test_run_produces_an_empty_candidates_carrying_the_askers_own_query() -> None:
    # Arrange
    retriever = NoRetrieval()
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    payload = QuerySet(origin=asked, queries=(asked,))

    # Act
    outcome: Outcome[Candidates] = await retriever.run(payload, _ctx())

    # Assert — never asked, which is a different fact from a search that came back empty
    # (`weft_retrieve.payload.Candidates`'s own module docstring draws that line).
    assert outcome == Produced(value=Candidates(origin=asked, lists=()))


async def test_the_empty_result_holds_regardless_of_how_many_queries_were_asked() -> None:
    # Arrange — a fan-out transform ahead of this stage would be a resolution error (two
    # retrievers cannot follow one another and no transform precedes the null case in
    # practice), but the plugin itself reads only `origin`, never `queries`, so the same
    # empty `Candidates` comes back whether one query arrived or several.
    retriever = NoRetrieval()
    asked = Query(text="what happened in 1066?")
    other = Query(text="a derived variant", produced_by="some-transform")
    payload = QuerySet(origin=asked, queries=(asked, other))

    # Act
    outcome = await retriever.run(payload, _ctx())

    # Assert
    assert outcome == Produced(value=Candidates(origin=asked, lists=()))


def test_a_with_block_is_refused_because_there_is_nothing_here_to_configure() -> None:
    # Arrange — the null case has no knob; `NoRetrieval` declares no `config_model` at all,
    # and `02` §1's rule is that a `with:` block against a decorative extension point is
    # refused rather than silently accepted and dropped.
    registry = Registry()
    registry.add(Retriever, NAME, NoRetrieval, distribution="weft-retrieve")
    pipeline = Pipeline(
        name="ask-nothing",
        stages=(StageDeclaration(id="retrieve", use=NAME, config={"top_k": 3}),),
    )

    # Act / Assert
    with pytest.raises(resolution.StageNotConfigurableError):
        resolution.resolve(pipeline, registry=registry, contracts={"retrieve": Retriever})


async def test_driving_no_retrieval_through_the_registration_seam_makes_no_blocking_call() -> None:
    """Fitness function 7(b) against the one path every registered plugin is called through.

    `NoRetrieval` opens no connection and calls no model, so nothing here is expected to
    fail — the value of this test is structural: it proves the plugin was actually exercised
    through `weft_kernel.seam.wrap`, not merely through a direct method call a registered
    instance never receives in production.
    """
    # Arrange
    retriever = NoRetrieval()
    wrapped = wrap(retriever.run, distribution="weft-retrieve", contract="Retriever", plugin=NAME)
    asked = Query(text="does this pass through the seam?")
    payload = QuerySet(origin=asked, queries=(asked,))

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.lists == ()
    assert isinstance(retriever, Retriever)


def test_sources_are_empty_by_design_is_the_stated_property_a_consumer_reads() -> None:
    # Act / Assert — `10` §1.1's own finding: the null case's emptiness was a consequence of
    # which helper it called, never a fact declared anywhere a caller could read. This class
    # attribute is the fix — readable with no instance, per `02` §3.
    assert NoRetrieval.sources_are_empty_by_design is True
    assert NoRetrieval.cost_bound == (0, 0)
    assert not hasattr(NoRetrieval, "config_model")
