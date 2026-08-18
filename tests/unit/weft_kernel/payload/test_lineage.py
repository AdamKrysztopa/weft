"""Unit tests for `weft_kernel.payload.lineage`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/lineage.py`.
"""

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from weft_kernel.payload.ids import NodeId, SourceId
from weft_kernel.payload.lineage import Lineage


def test_defaults_to_no_parents_and_no_sources() -> None:
    # Arrange / Act
    lineage = Lineage()

    # Assert
    assert lineage.parents == ()
    assert lineage.sources == frozenset()


def test_holds_the_parents_it_is_given_with_no_sources_authored() -> None:
    # Arrange
    parents = (NodeId("a"), NodeId("b"))

    # Act
    lineage = Lineage(parents=parents)

    # Assert
    assert lineage.parents == parents
    assert lineage.sources == frozenset()


def test_holds_authored_sources_at_a_root_with_no_parents() -> None:
    # Arrange
    sources = frozenset({SourceId("doc-1"), SourceId("doc-2")})

    # Act
    lineage = Lineage(sources=sources)

    # Assert
    assert lineage.parents == ()
    assert lineage.sources == sources


def test_authoring_sources_alongside_parents_raises() -> None:
    # Arrange
    parents = (NodeId("a"),)
    sources = frozenset({SourceId("a-source-that-does-not-exist")})

    # Act / Assert
    with pytest.raises(ValidationError, match="derived"):
        Lineage(parents=parents, sources=sources)


def test_lineage_is_frozen() -> None:
    # Arrange
    lineage = Lineage()

    # Act / Assert
    with pytest.raises(ValidationError):
        lineage.parents = (NodeId("a"),)  # type: ignore[misc]


def test_derived_still_type_checks_its_arguments() -> None:
    """`derived` trusts that `sources` was computed correctly, never that it is well-typed.

    Regression: an earlier implementation built the trusted path with
    `model_construct`, which skips validation entirely and would accept
    `parents="not-a-tuple"` without complaint.
    """
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        Lineage.derived(parents="not-a-tuple", sources=None)  # type: ignore[arg-type]


def test_derived_produces_a_lineage_that_survives_embedding_in_another_model() -> None:
    """A `Lineage` built through `derived` must still validate once nested elsewhere.

    Pydantic re-runs a nested model's `model_validator`s when the outer
    model is constructed, without replaying the context the inner value was
    first validated with — this is the exact shape `Node.derive` and
    `Node.combine` rely on when they embed the `Lineage` they build.
    """

    # Arrange
    class _Wrapper(BaseModel):
        model_config = ConfigDict(frozen=True)
        lineage: Lineage

    lineage = Lineage.derived(parents=(NodeId("a"),), sources=frozenset({SourceId("doc-1")}))

    # Act
    wrapped = _Wrapper(lineage=lineage)

    # Assert
    assert wrapped.lineage.sources == frozenset({SourceId("doc-1")})
