"""`weft index --target` binds the blob service it offers the run to that target — ledger task
**34.12**, its wiring half.

A figure extractor writes through `ctx.require(BlobStore)`, the service `build_index_services`
registers from the selected role. The store stages are bound to the target after `runner.resolve`
(`34.6`); without this, the blob service stayed `default`'s and a candidate build overwrote the
live index's figures at the same key.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import cast

import pytest

from weft_blob import BLOB_ROLE, BlobStore, FilesystemBlobSettings, FilesystemBlobStore
from weft_blob.keys import blob_key
from weft_engine.llm_roles import LLMSection
from weft_engine.run_services import build_index_services
from weft_engine.service_roles import RoleTable
from weft_engine.services import ServiceSelection
from weft_engine.targets import StoreHoldsNoTargetsError
from weft_kernel.payload import SourceId
from weft_kernel.registry import Registry
from weft_llm.client import NullSink

_KEY = blob_key(tenant_id="tenant-a", source_id=SourceId("doc"), ordinal=0, extension="png")


class _UntargetableBlobs:
    """A third party's blob store with no `bind_target`: it cannot keep a candidate apart."""

    def __init__(self, config: object = None) -> None:
        del config


def _registry(root: Path, plugin: Callable[..., object]) -> Registry:
    registry = Registry()
    registry.add_many([(BlobStore, "blobs", plugin)], distribution="weft-rag")
    return registry


async def _services(registry: Registry, target: str | None) -> object:
    services = await build_index_services(
        registry=registry,
        llm=LLMSection(),
        sink=NullSink(),
        embedder=None,
        roles=RoleTable(roles={BLOB_ROLE.key: BLOB_ROLE}),
        services=ServiceSelection(roles={BLOB_ROLE.key: "blobs"}),
        offer_models=False,
        target=target,
    )
    return services.resolve(BlobStore)


async def test_a_candidate_run_writes_blobs_into_the_candidates_subtree(tmp_path: Path) -> None:
    # Arrange
    registry = _registry(
        tmp_path, partial(FilesystemBlobStore, FilesystemBlobSettings(root=tmp_path))
    )

    # Act
    blobs = cast(FilesystemBlobStore, await _services(registry, "w128"))
    await blobs.put(_KEY, b"candidate figure", "image/png")

    # Assert
    assert (tmp_path / ".targets" / "w128" / _KEY).is_file()
    assert not (tmp_path / _KEY).exists()


async def test_a_run_naming_no_target_writes_where_it_always_did(tmp_path: Path) -> None:
    # Arrange
    registry = _registry(
        tmp_path, partial(FilesystemBlobStore, FilesystemBlobSettings(root=tmp_path))
    )

    # Act
    blobs = cast(FilesystemBlobStore, await _services(registry, None))
    await blobs.put(_KEY, b"live figure", "image/png")

    # Assert
    assert (tmp_path / _KEY).is_file()


async def test_a_blob_store_that_cannot_hold_targets_is_refused_for_a_candidate_run(
    tmp_path: Path,
) -> None:
    # Act / Assert
    with pytest.raises(StoreHoldsNoTargetsError) as caught:
        await _services(_registry(tmp_path, _UntargetableBlobs), "w128")
    assert "'blobs'" in str(caught.value)
