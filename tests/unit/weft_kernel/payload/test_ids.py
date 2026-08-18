"""Unit tests for `weft_kernel.payload.ids`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/ids.py`.
"""

from pydantic import BaseModel, ConfigDict

from weft_kernel.payload.ids import NodeId, SourceId


class _Holder(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_ids: tuple[NodeId, ...] = ()


def test_node_id_and_source_id_behave_as_strings() -> None:
    # Arrange
    node_id = NodeId("abc123")
    source_id = SourceId("doc-1")

    # Act / Assert
    assert node_id == "abc123"
    assert source_id == "doc-1"
    assert hash(node_id) == hash("abc123")
    assert sorted([NodeId("b"), NodeId("a")]) == [NodeId("a"), NodeId("b")]


def test_a_round_trip_through_a_pydantic_model_preserves_the_values() -> None:
    # Arrange
    holder = _Holder(node_ids=(NodeId("a"), NodeId("b")))

    # Act
    round_tripped = _Holder.model_validate(holder.model_dump())

    # Assert
    assert round_tripped.node_ids == (NodeId("a"), NodeId("b"))
