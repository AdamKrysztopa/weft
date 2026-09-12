"""`weft_kernel.payload.carry_forward` — one home for a rule three packs need.

**G17, settled 2026-09-12.** The function was `weft_chunk.carry.carry_forward`, with a
byte-identical private copy in `weft_vision.describe_figure` whose own docstring cited
`weft_chunk.fixed_size._carry_forward` — a function that has not existed since task `9.14` lifted
it. G17's settlement adds a third consumer: every `weft_clean` cleaner rebuilds its node with
`Node.derive`, which drops `ext`, and `R9.1` is the property that a `TEXT` node's extraction-time
facts survive that.

Those three packs import none of each other — `weft_clean` imports only `weft_kernel` — so the
only module all three already depend on is the kernel, and the function belongs there on `01`'s
own test: it names no capability. It is an operation on `Node.ext` and `SyntheticOrigin`, and both
are kernel types.
"""

from weft_kernel.payload import (
    ExtModel,
    MediaType,
    Node,
    SourceId,
    SyntheticOrigin,
    carry_forward,
)


class _Locator(ExtModel):
    """Stands in for a pack's own fact about a node — `weft_extract.payload.PageSpan` in
    production. Declared here rather than imported so the kernel's test names no pack."""

    __namespace__ = "test-locator"
    __schema_version__ = "1.0.0"

    page: int


class _Language(ExtModel):
    """A second namespace, so the test can tell *every* fact from *the first one found*."""

    __namespace__ = "test-language"
    __schema_version__ = "1.0.0"

    code: str


def _parent() -> Node:
    return (
        Node.synthetic(
            content="page one",
            media_type=MediaType.TEXT,
            reason="extracted for a test",
            sources=frozenset({SourceId("paper")}),
        )
        .with_ext(_Locator(page=4))
        .with_ext(_Language(code="en"))
    )


def test_every_namespace_the_parent_carried_reaches_the_child() -> None:
    # Arrange — two namespaces, because one cannot distinguish "all of them" from "one of them".
    parent = _parent()
    child = parent.derive(content="PAGE ONE")

    # Act
    carried = carry_forward(child, parent=parent)

    # Assert
    assert carried.ext_as(_Locator) == _Locator(page=4)
    assert carried.ext_as(_Language) == _Language(code="en")


def test_the_parents_synthetic_origin_is_the_one_fact_that_does_not_travel() -> None:
    # Arrange — `derive` has just given the child a real lineage, so a carried
    # `SyntheticOrigin` would be a claim about the child that is false when read.
    parent = _parent()
    child = parent.derive(content="PAGE ONE")

    # Act
    carried = carry_forward(child, parent=parent)

    # Assert
    assert carried.ext_as(SyntheticOrigin) is None
    assert parent.ext_as(SyntheticOrigin) is not None


def test_carrying_forward_changes_nothing_else_about_the_child() -> None:
    # Arrange
    parent = _parent()
    child = parent.derive(content="PAGE ONE")

    # Act
    carried = carry_forward(child, parent=parent)

    # Assert — identity, content and lineage are the child's own; only `ext` grew.
    assert carried.id == child.id
    assert carried.content == "PAGE ONE"
    assert carried.lineage == child.lineage


def test_a_parent_carrying_nothing_but_its_origin_leaves_the_child_untouched() -> None:
    # Arrange — the error case: nothing to carry is not an error, and must not
    # invent a namespace or raise.
    parent = Node.synthetic(
        content="page one", media_type=MediaType.TEXT, reason="extracted for a test"
    )
    child = parent.derive(content="PAGE ONE")

    # Act
    carried = carry_forward(child, parent=parent)

    # Assert
    assert carried == child
    assert dict(carried.ext) == {}
