"""Unit tests for `weft_store.pgvector_store`'s `register()`.

Mirrors `packages/weft-store/src/weft_store/pgvector_store.py`'s `register`.
Covers the happy path (`register` adds a `PgVectorStore` bound to this pack's
settings as `"pgvector"` under `NodeStore`), and that a missing `dsn` is
refused — it is the one field with no default, so it is the only shape a
`[packs.weft-store]` block can get wrong by omission. The three text-search
settings beside it are exercised in `test_pgvector_store.py`, where their
effect on a real database is what makes them worth having.
"""

import pytest
from pydantic import SecretStr, ValidationError

from weft_kernel.discovery import PackRegistrar
from weft_kernel.registry import Registry
from weft_store.contract import NodeStore
from weft_store.pgvector_store import PgVectorSettings, PgVectorStore, register


def test_register_adds_a_pgvector_store_bound_to_its_settings() -> None:
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-store")
    settings = PgVectorSettings(dsn=SecretStr("postgresql://weft:weft@localhost:5433/weft"))

    # Act
    register(registrar, settings)
    registrar.commit()

    # Assert
    entry = registry.entry(NodeStore, "pgvector")
    assert entry.distribution == "weft-store"
    built = entry.factory(None)
    assert isinstance(built, PgVectorStore)


def test_settings_requires_a_dsn() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        PgVectorSettings.model_validate({})
