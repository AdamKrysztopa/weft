"""Unit tests for `weft_kernel.payload.node`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/node.py`. Covers the
admission rule for the six core fields, the three ways to build a `Node`,
content-addressed identity, and the two bugs G5 makes unrepresentable:
RAPTOR's unreachable summaries (`Node.combine` on an empty set) and the
transient-blob guard (`Node.without_transient`).
"""

import json

import pytest
from pydantic import ValidationError

from weft_kernel.payload.ext import SCHEMA_VERSION_KEY, ExtModel
from weft_kernel.payload.ids import NodeId, SourceId
from weft_kernel.payload.lineage import Lineage
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node, SyntheticOrigin
from weft_kernel.payload.vector import Vector


class _GraphData(ExtModel):
    __namespace__ = "weft-graph"
    __schema_version__ = "1.0.0"

    entities: tuple[str, ...] = ()


class _OtherData(ExtModel):
    __namespace__ = "weft-graph"
    __schema_version__ = "1.0.0"

    label: str = ""


class _TransientBlob(ExtModel):
    __namespace__ = "weft-vision"
    __schema_version__ = "1.0.0"
    __transient__ = True

    payload_b64: str


def test_admits_exactly_the_six_core_fields() -> None:
    # Arrange / Act
    fields = set(Node.model_fields)

    # Assert
    assert fields == {"id", "lineage", "content", "media_type", "embedding", "ext"}


def test_full_lineage_flows_through_derive_combine_and_ext() -> None:
    # Arrange
    root = Node.synthetic(
        content="full document text",
        media_type=MediaType.TEXT,
        reason="root of doc-1",
        sources=frozenset({SourceId("doc-1")}),
    )

    # Act
    first_chunk = root.derive(content="first chunk", ordinal=0)
    second_chunk = root.derive(content="second chunk", ordinal=1)
    embedded = first_chunk.with_embedding(Vector(values=(0.1, 0.2)))
    tagged = embedded.with_ext(_GraphData(entities=("Acme",)))
    summary = Node.combine(
        [first_chunk, second_chunk], content="a summary of both", media_type=MediaType.TEXT
    )

    # Assert
    assert first_chunk.lineage.parents == (root.id,)
    assert tagged.ext_as(_GraphData) == _GraphData(entities=("Acme",))
    assert tagged.id == first_chunk.id  # ext and embedding never change identity
    assert summary.lineage.parents == (first_chunk.id, second_chunk.id)
    assert summary.lineage.sources == frozenset({SourceId("doc-1")})


def test_identical_content_and_ordinal_reindexes_to_the_same_id() -> None:
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")

    # Act
    first = root.derive(content="same chunk", ordinal=0)
    second = root.derive(content="same chunk", ordinal=0)
    sibling_with_distinct_ordinal = root.derive(content="same chunk", ordinal=1)

    # Assert
    assert first.id == second.id  # re-indexing unchanged content is idempotent
    assert first.id != sibling_with_distinct_ordinal.id  # the ordinal disambiguates


def test_ext_as_returns_none_for_a_namespace_no_stage_wrote() -> None:
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")

    # Act
    result = root.ext_as(_GraphData)

    # Assert
    assert result is None


def test_combine_on_an_empty_sequence_raises() -> None:
    # Arrange
    members: list[Node] = []

    # Act / Assert
    with pytest.raises(ValueError, match="at least one member"):
        Node.combine(members, content="orphan summary", media_type=MediaType.TEXT)


def test_synthetic_requires_a_non_empty_reason() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="non-empty reason"):
        Node.synthetic(content="x", media_type=MediaType.TEXT, reason="")


def test_ext_as_raises_when_the_namespace_holds_a_different_type() -> None:
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")
    tagged = root.with_ext(_GraphData(entities=("Acme",)))

    # Act / Assert
    with pytest.raises(TypeError, match="not _OtherData"):
        tagged.ext_as(_OtherData)


def test_without_transient_strips_only_transient_namespaces() -> None:
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")
    with_both = root.with_ext(_GraphData(entities=("Acme",))).with_ext(
        _TransientBlob(payload_b64="…")
    )

    # Act
    stripped = with_both.without_transient()

    # Assert
    assert stripped.ext_as(_TransientBlob) is None
    assert stripped.ext_as(_GraphData) == _GraphData(entities=("Acme",))


def test_synthetic_attaches_its_own_greppable_origin() -> None:
    # Arrange / Act
    node = Node.synthetic(content="probe content", media_type=MediaType.TEXT, reason="unit test")

    # Assert
    origin = node.ext_as(SyntheticOrigin)
    assert origin is not None
    assert origin.reason == "unit test"


def test_a_parentless_node_without_synthetic_origin_raises() -> None:
    # Arrange / Act / Assert
    with pytest.raises(ValidationError, match="SyntheticOrigin"):
        Node(
            id=NodeId("deadbeef"),
            lineage=Lineage(),
            content="global summary of everything",
            media_type=MediaType.TEXT,
        )


def test_mutating_ext_in_place_raises() -> None:
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")

    # Act / Assert
    with pytest.raises(TypeError):
        root.ext["weft-graph"] = _GraphData(entities=("Acme",))  # type: ignore[index]


def test_ext_survives_model_dump_and_json_with_subclass_fields_intact() -> None:
    """A pack's `ExtModel` subclass fields must not be dropped or crash serialisation.

    Regression for a defect this project exists to avoid: `ExtMap`'s
    immutable `MappingProxyType` container has no
    pydantic-core serializer by default, and declaring the value type as
    the base `ExtModel` makes pydantic serialise every entry as the base
    class, silently dropping a subclass's own fields with no warning. Both
    failure modes are invisible unless a `Node` carrying an `ExtModel`
    subclass is actually dumped, which is what this test does.

    Deserialising the JSON back into typed `ExtModel` subclasses is out of
    scope here — that needs a namespace-to-class registry that does not
    exist until a later step — so this only checks the write side.

    Task 5.2c: this is also where `SCHEMA_VERSION_KEY` is proven to travel
    *in the bytes* rather than being dropped the way `Filter.version` (a
    `ClassVar`) always was — a real `Node`, dumped through the real `ext`
    serialiser, is the round trip a store actually performs, not a
    hand-assembled dict that would pass by construction.
    """
    # Arrange
    root = Node.synthetic(content="doc", media_type=MediaType.TEXT, reason="probe")
    tagged = root.with_ext(_GraphData(entities=("Acme", "Widgets Inc")))

    # Act
    dumped = tagged.model_dump()
    parsed_json = json.loads(tagged.model_dump_json())

    # Assert
    assert dumped["ext"]["weft-graph"]["entities"] == ("Acme", "Widgets Inc")
    assert parsed_json["ext"]["weft-graph"]["entities"] == ["Acme", "Widgets Inc"]
    assert dumped["ext"]["weft-graph"][SCHEMA_VERSION_KEY] == _GraphData.__schema_version__
    assert parsed_json["ext"]["weft-graph"][SCHEMA_VERSION_KEY] == _GraphData.__schema_version__
