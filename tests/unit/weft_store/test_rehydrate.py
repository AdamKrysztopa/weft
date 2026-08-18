"""Unit tests for `weft_store.rehydrate`.

Mirrors `packages/weft-store/src/weft_store/rehydrate.py`. Covers the happy
path (a dumped `SyntheticOrigin` namespace comes back as a real
`SyntheticOrigin`, not a bare `ExtModel`), the edge case of an empty `ext`
mapping (rehydrates to an empty dict, never an error), and the error case of
a namespace this registry does not know.
"""

import pytest

from weft_kernel.payload import SyntheticOrigin
from weft_kernel.registry import UnknownPluginError
from weft_store.rehydrate import rehydrate_ext


def test_rehydrate_ext_turns_a_dumped_namespace_back_into_its_own_class() -> None:
    # Arrange
    origin = SyntheticOrigin(reason="root of a.txt")
    dumped = {origin.__namespace__: origin.model_dump()}

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
