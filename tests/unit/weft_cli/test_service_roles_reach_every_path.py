"""A declared role is reachable by `ctx.require` on **every** path — ledger task 9.0's whole point.

Properties (i), (ii) and (iii) each hold in isolation in their own files. This one asserts the
sentence the task line actually makes: *a pack that publishes a run-wide service is reachable by
`ctx.require` on every path — command, query, ingest — with no edit to `weft-cli`.* Each of the
three assemblers is a separate opportunity to leave a path out, and leaving one out is exactly the
failure this task exists to close: `docs/internal/build-ledger.md:4370-4366 'emits prose'` records
Phase 7's close finding that `run_command` registers four contracts and a pack needing the
configured store or embedder "still cannot reach one". The seam was repaired for the four contracts
the agent happened to need.

**The three assemblers are one list written thrice** — `build_services` (query),
`build_index_services` (ingest) and the inline block in `weft_cli.cli.run_command` (command). They
share `LLM`, `Prompts` and `TokenSink` and nothing else, so a check that reads only one of them
cannot see the gap.

**The ingest path is deliberately not symmetrical, and that is data rather than an exception.**
`build_index_services`' own docstring argues that an ambient `NodeStore` there would give one run
two paths to the same store, because an ingest document already names a store *stage*. Task 8.10's
two exclusions survive as a fact about the resolved pipeline — a role whose contract a stage in
that pipeline already fills is not registered ambiently — rather than as a hardcoded list of
capability names, which would put `weft-cli` back in the business of naming capabilities.
"""

from typing import ClassVar

import pytest

from weft_cli.service_roles import RoleTable
from weft_cli.services import ServiceSelection
from weft_embed import Embedder
from weft_kernel.context import ServiceRole
from weft_kernel.registry import Registry
from weft_llm.client import NullSink
from weft_store import NodeStore


class _BlobStore:
    """A stranger pack's contract. `weft-cli` names it nowhere."""


class _FsBlobs:
    """The plugin an operator selects for the `blobs` role.

    Takes a `config` argument because every real plugin in this tree does — `HashEmbedder`
    (`packages/weft-rag/src/weft_embed/hash_embedder.py:75 'def __init__(self'`) and `PgVectorStore`
    (`packages/weft-rag/src/weft_store/pgvector_store.py:616 'def _predic'`) both declare one with a
    default,
    and every assembler builds a plugin as `registry.entry(...).factory(None)`. A fixture
    without it would make the production call look wrong when it is the fixture that is.
    """

    version: ClassVar[str] = "1.0.0"

    def __init__(self, config: object = None) -> None:
        del config


BLOBS = ServiceRole(key="blobs", contract=_BlobStore)


class _Store:
    """A stand-in `NodeStore`. `build_services` resolves `[services] store` unconditionally, so
    a registry without one is a machine with no store rather than a test of roles.
    """

    def __init__(self, config: object = None) -> None:
        del config


class _Embedder:
    """A stand-in `Embedder`, for the same reason."""

    def __init__(self, config: object = None) -> None:
        del config


def _registry_with_a_blob_plugin() -> Registry:
    """A registry shaped like a real install: the two roles that predate the mechanism are
    filled under their default names, and the stranger's role is filled beside them.
    """
    registry = Registry()
    registry.add_many([(_BlobStore, "fs-blobs", _FsBlobs)], distribution="weft-blob")
    registry.add_many(
        [(NodeStore, "pgvector", _Store), (Embedder, "hash", _Embedder)], distribution="weft-rag"
    )
    return registry


def _selection() -> ServiceSelection:
    return ServiceSelection(roles={"blobs": "fs-blobs"})


def _table() -> RoleTable:
    return RoleTable(roles={"blobs": BLOBS})


async def test_the_query_path_reaches_a_role_no_one_here_named() -> None:
    """`build_services` — the path `weft ask` assembles."""
    # Arrange
    from weft_cli.llm_roles import LLMSection
    from weft_cli.run_services import build_services

    registry = _registry_with_a_blob_plugin()

    # Act
    services = await build_services(
        registry=registry,
        catalogue={},
        llm=LLMSection(),
        services=_selection(),
        sink=NullSink(),
        roles=_table(),
    )

    # Assert
    assert isinstance(services.resolve(_BlobStore), _FsBlobs)


async def test_the_ingest_path_reaches_a_role_no_one_here_named() -> None:
    """`build_index_services` — the path `weft index` assembles.

    Until task 8.10 this function registered nothing at all, and two registered `Expander` plugins
    had consequently never run through the CLI — found by running the binary, not by any of the
    1,929 tests green at the time (`docs/internal/lessons.md` L8.4). A role added here and not there
    would reproduce that shape exactly.
    """
    # Arrange
    from weft_cli.llm_roles import LLMSection
    from weft_cli.run_services import build_index_services

    registry = _registry_with_a_blob_plugin()

    # Act
    services = await build_index_services(
        registry=registry,
        llm=LLMSection(),
        sink=NullSink(),
        embedder=None,
        services=_selection(),
        roles=_table(),
    )

    # Assert
    assert isinstance(services.resolve(_BlobStore), _FsBlobs)


async def test_a_role_whose_contract_a_pipeline_stage_already_fills_is_not_also_ambient() -> None:
    """8.10's two ingest exclusions, as data rather than as a hardcoded absence.

    `build_index_services` argues that an ambient service for a contract an ingest document
    already names as a *stage* would give one run two paths to the same thing with no ordering
    between them. That argument is about the resolved pipeline, not about which capabilities
    `weft-cli` has heard of — so the exclusion is derived from the stages that actually resolved.
    """
    # Arrange
    from weft_cli.llm_roles import LLMSection
    from weft_cli.run_services import build_index_services

    registry = _registry_with_a_blob_plugin()

    # Act — the resolved pipeline already has a stage filling `_BlobStore`
    services = await build_index_services(
        registry=registry,
        llm=LLMSection(),
        sink=NullSink(),
        embedder=None,
        services=_selection(),
        roles=_table(),
        filled_by_stages=(_BlobStore,),
    )

    # Assert
    from weft_kernel.context import UnresolvedServiceError

    with pytest.raises(UnresolvedServiceError):
        services.resolve(_BlobStore)


async def test_the_command_path_reaches_a_role_no_one_here_named() -> None:
    """The third assembler, inline in `weft_cli.cli.run_command`.

    This is the one Phase 7's close actually measured as failing: it registered `LLM`,
    `Prompts`, `TokenSink` and `Registry`, and a pack needing the configured store or embedder
    could not reach one. A third-party `Command` reaches a role-selected service here or
    requirement 1 still fails for the next pack.
    """
    # Arrange
    from weft_cli.registry_bootstrap import Dependencies
    from weft_cli.run_services import command_path_services

    deps = Dependencies(
        registry=_registry_with_a_blob_plugin(),
        reports=(),
        services=_selection(),
        roles=_table(),
    )

    # Act
    services = command_path_services(deps, sink=NullSink())

    # Assert
    assert isinstance(services.resolve(_BlobStore), _FsBlobs)
