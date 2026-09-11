"""`Removed` reports what a participant removed, by kind — ledger task `9.3`.

`Removed` has carried `node_count` and nothing else since G4
(`packages/weft-rag/src/weft_store/contract.py:185-209 'class Score'`), and G7 then made the fan-out
reach
*every* plugin satisfying `SourceDeletable`, not only node stores
(`docs/02-extension-model.md` → *Extended by G7*). A participant that removes something which is
not a node therefore reports `node_count=0` — the exact inverse of the promise `SourceDeletable`'s
own docstring makes, that a fan-out names what each participant did. Phase 9's blob store (`9.4`)
is the first participant for which that is the normal case rather than an edge one, and Phase 11
counts entities and facts through the same field.

**Why a mapping and not an `Enum`.** The project's string-constant rule says `Enum` over `Literal`,
and it is about *closed* vocabularies the kernel or a contract owns. A kind here is owned by the
participant: a blob store counts blobs, a graph pack counts entities and relations, and a pack
nobody has written yet counts something nobody has named. An `Enum` on this contract would be a
closed key space over third-party data, which is fitness function 4's own subject.

**`node` is the one reserved key, and it is refused loudly.** `node_count` already carries that
number; a second spelling of it is the two-lists-that-can-drift failure `docs/internal/README.md`
opens with, reproduced inside a single model. The refusal names `node_count`, so a participant that
reaches for the key is told where the number lives rather than silently reporting it twice.
"""

from types import MappingProxyType
from typing import cast

import pytest
from pydantic import ValidationError

from weft_kernel.payload import SourceId
from weft_store.contract import Removed


def test_a_participant_that_reports_no_kinds_is_unchanged() -> None:
    """Every participant written before this task keeps working: the field defaults empty."""
    # Arrange / Act
    removed = Removed(source_id=SourceId("src-1"), node_count=6)

    # Assert
    assert removed.node_count == 6
    assert dict(removed.removed) == {}


def test_a_participant_reports_the_kinds_it_owns() -> None:
    """9.3's property: forty blobs and no node is distinguishable from six nodes and no blob."""
    # Arrange
    blobs = Removed(source_id=SourceId("src-1"), node_count=0, removed={"blob": 40})
    nodes = Removed(source_id=SourceId("src-1"), node_count=6)

    # Act / Assert
    assert dict(blobs.removed) == {"blob": 40}
    assert blobs.node_count == 0
    assert dict(nodes.removed) == {}
    assert nodes.node_count == 6


def test_the_kind_vocabulary_is_open() -> None:
    """A kind is a string the participant owns — nothing on this contract enumerates them."""
    # Arrange / Act
    removed = Removed(
        source_id=SourceId("src-1"),
        node_count=0,
        removed={"entity": 12, "relation": 30, "something-nobody-has-written-yet": 1},
    )

    # Assert
    assert dict(removed.removed) == {
        "entity": 12,
        "relation": 30,
        "something-nobody-has-written-yet": 1,
    }


def test_what_a_participant_reported_cannot_be_edited_afterwards() -> None:
    """`Removed` is frozen, and a plain `dict` field would leave one hole in that.

    `Node.ext` closed the identical hole with the identical mechanism
    (`packages/weft-kernel/src/weft_kernel/payload/ext.py:168-172 'type ExtMap = Annotated['`).
    """
    # Arrange
    removed = Removed(source_id=SourceId("src-1"), node_count=0, removed={"blob": 40})

    # Act / Assert
    assert isinstance(removed.removed, MappingProxyType)
    with pytest.raises(TypeError):
        cast("dict[str, int]", removed.removed)["blob"] = 0


def test_the_node_kind_is_refused_because_node_count_already_carries_it() -> None:
    """The error case: two spellings of one number is the drift this model must not contain."""
    # Arrange / Act
    with pytest.raises(ValidationError) as caught:
        Removed(source_id=SourceId("src-1"), node_count=6, removed={"node": 6})

    # Assert
    assert "node_count" in str(caught.value)


def test_a_reported_mapping_survives_a_round_trip_through_json() -> None:
    """`L9.43`: a constraint that dumps correctly and reads back wrong is write-only, and this
    module has paid for that shape before. Asserted in the red phase, not after the diff.
    """
    # Arrange
    removed = Removed(source_id=SourceId("src-1"), node_count=0, removed={"blob": 40})

    # Act
    rebuilt = Removed.model_validate(removed.model_dump(mode="json"))

    # Assert
    assert rebuilt == removed
