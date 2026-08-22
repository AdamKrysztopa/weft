"""Unit tests for `weft_retrieve.repack`.

Mirrors `packages/weft-retrieve/src/weft_retrieve/repack.py`. Task **2.19**: "context
ordering is a named, parameterised stage whose method does what the method is named
after." This module covers the happy path (`forward` keeps retrieval order and assigns
the final labels a `Generator` resolves citations against), the two other named
orderings — `reverse` (the default, `10` §1.1's `repack` row: Wang et al.'s Table 11
Avg-column winner) and `sides`, pinned to the exact n=7 sequence `.phase2-design.md`
names so the reference's best/worst zip-interleave defect cannot be laundered back in under
the same citation — the edge case (`top_n` truncates the *input* ranking before a method
ever sees it, and an empty `Ranking` comes back as empty `Passages` with no method
applied), the error case (an unregistered method name is refused at configuration, naming
what was asked and listing the pydantic-enforced valid set, per `RepackMethod` being a
closed vocabulary rather than a `str`), and a drive through `weft_kernel.seam.wrap`.

`out.origin == in.origin` is asserted here rather than assumed, the same obligation every
other query-path plugin in this pack carries in its own tests. `out.ext == in.ext` is
asserted too — `repack` rebuilds its output wholesale to reorder it, exactly where
`weft_retrieve.rerank`'s own test suite found the carrier extension needs a test of its
own rather than an assumption.
"""

import pytest
from pydantic import ValidationError

from weft_kernel.context import Context
from weft_kernel.payload import ExtMap, ExtModel, MediaType, Node, Produced
from weft_kernel.seam import wrap
from weft_retrieve.contract import ContextPacker
from weft_retrieve.payload import Passage, Query, Ranking
from weft_retrieve.repack import NAME, Repack, RepackConfig, RepackMethod
from weft_store.contract import Scored


class _Note(ExtModel):
    """A carrier extension, to prove `ext` survives a repack — G5's settled mechanism for
    "a strategy needs to pass something along", dropped nowhere this plugin can help it."""

    __namespace__ = "test-repack"
    __schema_version__ = "1.0.0"

    text: str


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _passage(content: str, rank: int) -> Passage:
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="fixture")
    return Passage(
        scored=Scored(value=node, score=1.0 - (rank / 100)), rank=rank, retrieved_by="vector-top-k"
    )


def _ranking(*contents: str, ext: ExtMap | None = None) -> Ranking:
    asked = Query(text="why is mRMR preferred to plain relevance ranking?")
    hits = tuple(_passage(content, rank) for rank, content in enumerate(contents))
    return Ranking(origin=asked, hits=hits, contributors=("vector-top-k:vector",), ext=ext or {})


async def test_forward_keeps_retrieval_order_and_labels_each_passage_by_final_position() -> None:
    # Arrange
    payload = _ranking("first", "second", "third")
    repack = Repack(RepackConfig(method=RepackMethod.FORWARD))

    # Act
    outcome = await repack.run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    passages = outcome.value
    assert passages.origin == payload.origin
    assert [p.node.content for p in passages.passages] == ["first", "second", "third"]
    assert [p.label for p in passages.passages] == ["1", "2", "3"]
    assert [p.rank for p in passages.passages] == [0, 1, 2]


async def test_reverse_is_the_default_and_puts_the_best_hit_last() -> None:
    # Arrange — the default (`10` §1.1's `repack` row: Wang et al.'s Table 11 Avg-column
    # winner at 0.483), so an operator who names no method gets this one.
    payload = _ranking("best", "middle", "worst")

    # Act
    outcome = await Repack().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["worst", "middle", "best"]
    assert Repack().config_model().method == RepackMethod.REVERSE


async def test_sides_places_the_best_and_second_best_at_the_two_ends_for_seven_hits() -> None:
    # Arrange — the exact n=7 sequence `.phase2-design.md`'s task-map row pins: best at the
    # head, second-best at the very tail, worst buried in the middle. Porting the reference's
    # best-at-head-worst-at-slot-1 zip-interleave over this citation is the defect this test
    # exists to refuse forever.
    payload = _ranking("d0", "d1", "d2", "d3", "d4", "d5", "d6")

    # Act
    outcome = await Repack(RepackConfig(method=RepackMethod.SIDES)).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == [
        "d0",
        "d2",
        "d4",
        "d6",
        "d5",
        "d3",
        "d1",
    ]


async def test_top_n_truncates_the_input_before_any_method_reorders_it() -> None:
    # Arrange — `top_n` bounds how much of the fused ranking survives into the prompt; the
    # method then arranges only what survived. Cutting after reordering would let a method
    # decide which hits are kept, which is a truncation policy `RepackConfig` does not have.
    payload = _ranking("best", "second", "third", "worst")

    # Act
    outcome = await Repack(RepackConfig(method=RepackMethod.FORWARD, top_n=2)).run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["best", "second"]


async def test_an_empty_ranking_comes_back_as_empty_passages_with_no_method_applied() -> None:
    # Arrange — the emptiness rule from `weft_retrieve.contract`: a stage that ran and found
    # nothing to pack returns `Produced` carrying an empty collection, never
    # `NothingToProduce`, which would stop the pipeline where V2 requires "not in this corpus".
    asked = Query(text="a question this corpus has no answer for")
    payload = Ranking(origin=asked, hits=(), contributors=())

    # Act
    outcome = await Repack().run(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.origin == asked
    assert outcome.value.passages == ()


def test_an_unregistered_method_name_is_refused_at_configuration() -> None:
    # Act / Assert — `RepackMethod` is a closed `StrEnum`, not a `str`, so a typo is a
    # pydantic `ValidationError` naming the valid set rather than a silent no-op at `run`.
    with pytest.raises(ValidationError, match="sides"):
        RepackConfig(method="zig-zag")  # type: ignore[arg-type]


async def test_driving_repack_through_the_seam_produces_passages() -> None:
    """Fitness function 7(b) against the one path a registered plugin is actually called
    through in production — `weft_kernel.seam.wrap`, not a direct method call a registered
    instance never receives."""
    # Arrange
    payload = _ranking("only candidate")
    repack = Repack()
    wrapped = wrap(repack.run, distribution="weft-retrieve", contract="ContextPacker", plugin=NAME)

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert [p.node.content for p in outcome.value.passages] == ["only candidate"]
    assert isinstance(repack, ContextPacker)


async def test_an_extension_attached_before_the_repack_survives_it() -> None:
    # Arrange
    note = _Note(text="carried")
    payload = _ranking("first", "second", ext={_Note.__namespace__: note})
    wrapped = wrap(
        Repack().run, distribution="weft-retrieve", contract="ContextPacker", plugin=NAME
    )

    # Act
    outcome = await wrapped(payload, _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value.ext == payload.ext


def test_the_declared_cost_bound_is_zero_zero() -> None:
    # Act / Assert — pure reordering over what already arrived; `run` resolves no service
    # and calls no model, the same honest shape `test_no_retrieval.py` uses for its own (0, 0).
    assert Repack.cost_bound == (0, 0)
