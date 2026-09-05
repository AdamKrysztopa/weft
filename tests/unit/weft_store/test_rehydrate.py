"""Unit tests for `weft_store.rehydrate`.

Mirrors `packages/weft-rag/src/weft_store/rehydrate.py`. Covers the happy
path (a namespace dumped the way a real `Node` dumps it — through `ExtMap`'s
`_dump`, carrying `SCHEMA_VERSION_KEY` — comes back as a real
`SyntheticOrigin`, not a bare `ExtModel`), the edge case of an empty `ext`
mapping (rehydrates to an empty dict, never an error), the error case of a
namespace this registry does not know, and — task 5.2c — the two shapes of
schema-version refusal: a stored version that disagrees with the current
one, and a namespace with no stored version at all, which is every row this
store held before task 5.2c existed.
"""

from typing import ClassVar

import pytest

from weft_kernel.discovery import PackReport, PackStatus
from weft_kernel.payload import ExtModel, Node, SyntheticOrigin
from weft_kernel.payload.ext import SchemaVersionRefusedError
from weft_kernel.payload.media_type import MediaType
from weft_kernel.registry import (
    DuplicateRegistrationError,
    Registry,
    UnknownPluginError,
)
from weft_store import rehydrate
from weft_store.rehydrate import (
    ext_models,
    register_ext_model,
    register_from_reports,
    rehydrate_ext,
)


def test_rehydrate_ext_turns_a_dumped_namespace_back_into_its_own_class() -> None:
    # Arrange — dumped the way a real store does: through `Node.model_dump()`, so
    # `SCHEMA_VERSION_KEY` is actually present, not hand-built via `model_dump()` alone.
    origin = SyntheticOrigin(reason="root of a.txt")
    node = Node.synthetic(content="a", media_type=MediaType.TEXT, reason="root of a.txt")
    dumped = node.model_dump()["ext"]

    # Act
    rehydrated = rehydrate_ext(dumped)

    # Assert
    assert rehydrated == {"weft-kernel": origin}
    assert isinstance(rehydrated["weft-kernel"], SyntheticOrigin)


def test_rehydrate_ext_of_an_empty_mapping_is_an_empty_mapping() -> None:
    # Act
    rehydrated = rehydrate_ext({})

    # Assert
    assert rehydrated == {}


def test_rehydrate_ext_fails_loudly_for_an_unregistered_namespace() -> None:
    # Act / Assert
    with pytest.raises(UnknownPluginError) as excinfo:
        rehydrate_ext({"weft-nonexistent-pack": {"whatever": "value"}})

    assert "weft-nonexistent-pack" in str(excinfo.value)
    assert "weft-kernel" in str(excinfo.value)


def test_rehydrate_ext_refuses_a_namespace_with_no_stored_version() -> None:
    # Arrange — `origin.model_dump()` alone, bypassing `ExtMap._dump`, is exactly the
    # shape every row this store held before task 5.2c existed: no `SCHEMA_VERSION_KEY`
    # at all, since the key did not exist yet when it was written.
    origin = SyntheticOrigin(reason="root of a.txt")
    dumped = {origin.__namespace__: origin.model_dump()}

    # Act / Assert
    with pytest.raises(SchemaVersionRefusedError) as excinfo:
        rehydrate_ext(dumped)

    assert excinfo.value.namespace == "weft-kernel"
    assert excinfo.value.stored_version is None
    assert excinfo.value.current_version == SyntheticOrigin.__schema_version__
    assert "no version at all" in str(excinfo.value)


def test_rehydrate_ext_refuses_a_stored_version_older_than_the_current_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange — a fresh registry, `test_registry_bootstrap.py`'s own precedent for not
    # leaking a test-only class into the module-global `ext_models` other tests share.
    class _Versioned(ExtModel):
        __namespace__ = "weft-test-schema-version"
        __schema_version__ = "2.0.0"

        note: str = ""

    fresh = Registry()
    monkeypatch.setattr(rehydrate, "ext_models", fresh)
    rehydrate.register_ext_model(_Versioned)
    dumped = {"weft-test-schema-version": {"note": "x", "__schema_version__": "1.0.0"}}

    # Act / Assert
    with pytest.raises(SchemaVersionRefusedError) as excinfo:
        rehydrate_ext(dumped)

    assert excinfo.value.namespace == "weft-test-schema-version"
    assert excinfo.value.stored_version == "1.0.0"
    assert excinfo.value.current_version == "2.0.0"


# ---------------------------------------------------------------------------
# Task 6.34 — the two registration paths do not behave identically, and this is
# the test whose absence let a docstring say they did. `docs/lessons.md` L6.28.
# ---------------------------------------------------------------------------


class _TwiceRegistered(ExtModel):
    """A namespace of this test's own, so registering it cannot disturb another test."""

    __namespace__: ClassVar[str] = "rehydrate-twice-registered"
    __schema_version__: ClassVar[str] = "1"

    value: int


def test_register_from_reports_skips_a_class_that_already_claimed_its_namespace() -> None:
    """The idempotent path — what a caller outside full discovery wants.

    `weft_cli.registry_bootstrap` calls this once per discovery, and a process that discovers
    twice must not fail on the second.
    """
    # Arrange
    report = PackReport(
        pack="test",
        distribution="weft-test",
        status=PackStatus.ACTIVE,
        ext_models=(_TwiceRegistered,),
    )

    # Act — twice, deliberately.
    register_from_reports([report])
    register_from_reports([report])

    # Assert — no exception, and the namespace still resolves to the class that claimed it.
    assert ext_models.entry(ExtModel, _TwiceRegistered.__namespace__).factory is _TwiceRegistered


def test_register_ext_model_refuses_a_second_call_for_the_same_class() -> None:
    """The refusing path — and the reason `rehydrate.py`'s docstring was wrong until task 6.34.

    It said both paths give "the identical idempotent-or-refuse behaviour either way" and named
    the caller it was wrong about: "a test, or a caller that builds a registry without running
    full discovery". They differ, and this is the assertion whose absence let the sentence stand.
    """
    # Arrange — the namespace is already claimed by the test above's own class, whichever order
    # these run in, because both go through the same process-global registry.
    register_from_reports(
        [
            PackReport(
                pack="test",
                distribution="weft-test",
                status=PackStatus.ACTIVE,
                ext_models=(_TwiceRegistered,),
            )
        ]
    )

    # Act / Assert
    with pytest.raises(DuplicateRegistrationError):
        register_ext_model(_TwiceRegistered)
