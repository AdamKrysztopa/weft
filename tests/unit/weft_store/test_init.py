"""Unit tests for `weft_store.pgvector_store`'s `register()`.

Mirrors `packages/weft-store/src/weft_store/pgvector_store.py`'s `register`.
Covers the happy path (`register` adds a `PgVectorStore` bound to this pack's
settings as `"pgvector"` under `NodeStore`), and that an unresolvable `dsn`
field is refused — `PgVectorSettings` has exactly one field, so a missing
`dsn` is the only shape it can get wrong.
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
