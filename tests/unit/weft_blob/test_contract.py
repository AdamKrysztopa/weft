"""The `BlobStore` contract — ledger task `9.4`.

A **service, not a stage**: no pipeline position, no `run`, no `Stage[In, Out]` base
(`docs/11-multimodal.md:199-203 'weft-blob'`). `TokenSink` is the precedent for a service without a
stage, and
`weft_kernel.seam` wraps stages and `flush` and nothing else — which is why nothing on this contract
produces a `Node` and why bytes reaching it never enter the payload.

**Published from its own pack, and deliberately not from `weft_store`.**
`weft_cli.contract_reference.capability_siblings` enumerates a contract pack's public module, so a
`BlobStore` exported from `weft_store` would be advertised as a store-family capability that no node
store satisfies — `weft plugins doctor` would report every store as missing a capability it was
never meant to have. `weft_blob` is a pack of its own inside the `weft-rag` distribution, which is
the *module home the ledger leaves to the brief* (`docs/internal/build-ledger.md` 9.4; `11` §3's
revision log settles that it is not a separate wheel).

It joins `weft delete`'s fan-out by satisfying `SourceDeletable` structurally and declaring nothing
— `weft_cli.fanout.participants_for` walks every registered contract and asks `issubclass`.
"""

from typing import Any, Protocol, cast

from weft_blob.contract import BLOB_CONTRACT_VERSION, BLOB_ROLE, BlobStore, BlobUri
from weft_kernel.context import ServiceRole
from weft_store import SourceDeletable


def _protocol_members() -> set[str]:
    """`BlobStore.__protocol_attrs__`, reached through a cast.

    `typing` computes it on every `Protocol` and declares it on none of them, so a checker in
    strict mode cannot see it. The set is what this file is actually asserting on — which methods
    a plugin structurally owes — so it is read rather than approximated.
    """
    return cast("set[str]", cast("Any", BlobStore).__protocol_attrs__)


class _StrangerBlobStore:
    """Satisfies `BlobStore` structurally, importing nothing from it — a stranger's path."""

    async def put(self, key: str, data: bytes, media_type: str) -> str:
        del data, media_type
        return f"memory:{key}"

    async def open(self, uri: str) -> bytes:
        del uri
        return b""

    async def delete_prefix(self, prefix: str) -> int:
        del prefix
        return 0


def test_a_class_that_imports_nothing_from_the_contract_satisfies_it() -> None:
    """`@runtime_checkable` is what makes capability derived rather than declared."""
    # Act / Assert
    assert isinstance(_StrangerBlobStore(), BlobStore)


def test_a_class_missing_a_method_does_not_satisfy_it() -> None:
    """The contrast that makes the check above mean something."""

    # Arrange
    class _Partial:
        async def put(self, key: str, data: bytes, media_type: str) -> str:
            del key, data, media_type
            return ""

    # Act / Assert
    assert not isinstance(_Partial(), BlobStore)


def test_the_contract_is_not_a_stage() -> None:
    """A service has no pipeline position, so it must not carry `run` and must not be a `Stage`.

    Asserted as the fact — `run` is absent from the protocol's own member set — rather than by
    checking a base class list, because what would break is a resolver treating this as placeable.
    """
    # Act / Assert
    assert "run" not in _protocol_members()
    assert _protocol_members() == {"put", "open", "delete_prefix"}


def test_every_method_is_async() -> None:
    """`CLAUDE.md`: async only, no exceptions. A blocking `open` would stall the event loop."""
    # Act / Assert
    for name in sorted(_protocol_members()):
        member = getattr(BlobStore, name)
        assert member.__code__.co_flags & 0x80, f"{name} is not `async def`"


def test_the_contract_declares_a_version_off_the_protocol_attribute_set() -> None:
    """Fitness function 6's subject, and the `if TYPE_CHECKING:` split that keeps it out of
    `__protocol_attrs__` — a plugin restating nothing must still satisfy the Protocol.
    """
    # Act / Assert
    assert BlobStore.version == BLOB_CONTRACT_VERSION
    assert "version" not in _protocol_members()


def test_the_pack_declares_which_services_key_selects_a_blob_store() -> None:
    """Task 9.0's seam, used by its first new consumer: one constant beside the Protocol."""
    # Act / Assert
    assert isinstance(BLOB_ROLE, ServiceRole)
    assert BLOB_ROLE.contract is BlobStore


def test_a_blob_store_is_a_source_deletable_participant_by_construction() -> None:
    """9.4's cascade clause: `weft delete` reaches blobs by capability, with nothing declared.

    Asserted on a stranger rather than on the shipped implementation, because what matters is
    that the *contract's* shape makes participation available to anyone who implements it.
    """

    # Arrange
    class _StrangerThatAlsoDeletesSources(_StrangerBlobStore):
        async def delete_source(self, source_id: str) -> object:
            del source_id
            return None

    # Act / Assert
    assert isinstance(_StrangerThatAlsoDeletesSources(), SourceDeletable)


def test_a_blob_uri_is_a_string_at_runtime_and_a_distinct_type_to_a_checker() -> None:
    """`NewType` over `str`, the identical footing `SourceId` and `NodeId` already have."""
    # Act / Assert
    assert BlobUri("file:///x") == "file:///x"
    assert isinstance(BlobUri("file:///x"), str)


def test_the_protocol_is_a_protocol_and_not_a_base_class_anyone_inherits() -> None:
    """A stranger must never have to import this module to be a blob store."""
    # Act / Assert
    assert Protocol in cast("Any", BlobStore).__mro__
