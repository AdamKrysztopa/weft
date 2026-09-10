"""`weft_blob`'s registration — ledger task `9.4`.

A pack, not a distribution: `weft_blob` ships inside `weft-rag` with its own `weft.packs` entry
point, its own `[packs.blob]` settings namespace and its own `plugins doctor` row, exactly the way
`weft_chunk` and `weft_store` do. `11` §3's revision log settles that it is not a separate wheel.

What is asserted here is what a *pack* owes: it registers through the public seam with no shortcut
a third party lacks (fitness function 2), it declares the `[services]` key that selects it (task
9.0), and the `ExtModel` it publishes reaches rehydration through `register()` (FF14).
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

import weft_blob
from weft_blob import BLOB_ROLE, BlobRef, BlobStore, Settings
from weft_cli.deletion import participants
from weft_kernel.discovery import PackRegistrar
from weft_kernel.payload import ExtModel
from weft_kernel.registry import Registry


def _committed() -> Registry:
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")
    weft_blob.register(registrar, Settings(root=Path("/blobs")))
    registrar.commit()
    return registry


def test_the_pack_registers_a_blob_store_under_the_contract_it_publishes() -> None:
    # Act
    registry = _committed()

    # Assert — `names_for` answers a `frozenset`, which is the fact: a set of names, unordered.
    assert registry.names_for(BlobStore) == frozenset({"filesystem"})


def test_the_registered_plugin_actually_satisfies_the_contract() -> None:
    """Registration proves a name resolves; this proves the thing behind it is a blob store."""
    # Arrange
    registry = _committed()

    # Act
    built = registry.entry(BlobStore, "filesystem").factory(None)

    # Assert
    assert isinstance(built, BlobStore)


def test_the_registered_factory_is_one_the_fan_out_can_inspect() -> None:
    """`weft delete` must find this pack by capability, and it inspects the **factory**.

    Found by running the binary, not by the forty-four tests around it: every one of those
    constructs `FilesystemBlobStore` directly, so all of them passed while `weft delete` reported
    one participant instead of two. `weft_cli.fanout.participants_for` asks
    `class_provides(unwrap_factory(entry.factory), SourceDeletable)`, and `unwrap_factory` peels
    `functools.partial` and nothing else (`weft_kernel/registry.py:594-614 'def unwra'`) — so a pack
    that binds
    its settings in a closure is invisible to every reader that inspects a class attribute rather
    than a constructed instance. `weft_store`'s `register()` is the shape that works.

    Asserted through the real fan-out rather than by checking for `functools.partial`, because the
    property is *participation*, not which binding idiom got it there.
    """
    # Arrange
    registry = _committed()

    # Act
    found = participants(registry=registry, store_names=frozenset())

    # Assert
    assert [target.name for target in found] == ["filesystem"]


def test_the_pack_declares_its_services_role_at_module_level() -> None:
    """Task 9.0 reads `SERVICE_ROLES` off the module at import, *before* settings are validated —
    so an operator with no `[packs.blob] root` configured is still told the key exists.
    """
    # Act / Assert
    assert weft_blob.SERVICE_ROLES == (BLOB_ROLE,)


def test_the_ext_model_this_pack_publishes_reaches_rehydration() -> None:
    """Fitness function 14 compares declared against present; `register()` is what declares."""
    # Arrange
    registry = Registry()
    registrar = PackRegistrar(registry, distribution="weft-rag")

    # Act — `commit()` answers `None`; what a pack declared is `registrar.ext_models`, which is
    # the tuple `_activate` reads and folds into the `PackReport` FF14 compares against.
    weft_blob.register(registrar, Settings(root=Path("/blobs")))
    declared = registrar.ext_models
    registrar.commit()

    # Assert
    assert BlobRef.__namespace__ in {model.__namespace__ for model in declared}


def test_the_blob_reference_is_an_ext_model_and_is_not_transient() -> None:
    """`11` §2.4: the pixels leave the payload and a **non-transient** `BlobRef` stays in `ext`.

    Transient would be exactly wrong: the reference is the durable half, and stripping it at the
    seam would leave an `IMAGE` node in the store pointing at nothing.
    """
    # Act / Assert
    assert issubclass(BlobRef, ExtModel)
    assert BlobRef.__transient__ is False
    assert BlobRef.__namespace__
    assert BlobRef.__schema_version__


def test_the_root_setting_is_required_and_has_no_default() -> None:
    """`[packs.blob] root` follows `[packs.store] dsn`: a pack cannot invent where bytes live.

    A default — `./blobs`, say — would write a corpus's figures into whatever directory the
    operator happened to run `weft index` from, and nothing would say so.
    """
    # Act / Assert — `model_validate` rather than `Settings()`, because the call this test is
    # about is one a *checker* also refuses, and the real caller is pydantic reading `weft.toml`.
    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_settings_refuse_a_key_the_pack_does_not_read() -> None:
    """`extra="forbid"`: a typo in `weft.toml` is refused, never silently ignored."""
    # Act / Assert — through `model_validate`, which is how a stray key in `weft.toml` arrives.
    with pytest.raises(ValidationError):
        Settings.model_validate({"root": "/blobs", "rooot": "/typo"})
