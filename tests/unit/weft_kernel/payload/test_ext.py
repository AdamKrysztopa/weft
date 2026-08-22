"""Unit tests for `weft_kernel.payload.ext`.

Mirrors `packages/weft-kernel/src/weft_kernel/payload/ext.py`. Task 5.2c adds the
mandatory `__schema_version__` declaration (checked in the same
`__pydantic_init_subclass__` seam as `__namespace__`), `SCHEMA_VERSION_KEY` carrying
that version into a dumped namespace's bytes, and `upgrade`'s default refusal.
"""

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from weft_kernel.payload.ext import ExtModel, SchemaVersionRefusedError


def test_a_declared_namespace_and_transience_are_readable_as_class_attributes() -> None:
    # Arrange
    class GraphData(ExtModel):
        __namespace__ = "weft-graph"
        __schema_version__ = "1.0.0"
        __transient__ = True

        entities: tuple[str, ...] = ()

    # Act
    instance = GraphData(entities=("Acme",))

    # Assert
    assert type(instance).__namespace__ == "weft-graph"
    assert type(instance).__transient__ is True


def test_transience_defaults_to_false() -> None:
    # Arrange
    class PlainData(ExtModel):
        __namespace__ = "weft-plain"
        __schema_version__ = "1.0.0"

    # Act
    result = PlainData.__transient__

    # Assert
    assert result is False


def test_declaring_a_subclass_with_no_namespace_raises_at_class_definition() -> None:
    # Arrange
    def _build_invalid_subclass() -> type[ExtModel]:
        class NoNamespace(ExtModel):
            __schema_version__ = "1.0.0"

        return NoNamespace

    # Act / Assert
    with pytest.raises(TypeError, match="non-empty __namespace__"):
        _build_invalid_subclass()


def test_declaring_a_subclass_with_no_schema_version_raises_at_class_definition() -> None:
    # Arrange — task 5.2c: mandatory at class definition, the same posture `__namespace__`
    # already has and for the same reason (a missing declaration fails while the author is
    # standing there, not at first write or first read).
    def _build_invalid_subclass() -> type[ExtModel]:
        class NoSchemaVersion(ExtModel):
            __namespace__ = "weft-no-version"

        return NoSchemaVersion

    # Act / Assert
    with pytest.raises(TypeError, match="non-empty __schema_version__"):
        _build_invalid_subclass()


def test_an_ext_model_instance_is_frozen() -> None:
    # Arrange
    class GraphData(ExtModel):
        __namespace__ = "weft-graph"
        __schema_version__ = "1.0.0"

        entities: tuple[str, ...] = ()

    instance = GraphData(entities=())

    # Act / Assert
    with pytest.raises(ValidationError):
        instance.entities = ("mutated",)  # type: ignore[misc]


def test_upgrade_refuses_by_default_naming_namespace_and_both_versions() -> None:
    # Arrange — task 5.2c: silence is refusal, the same posture G3's permission_class
    # takes. No override, so the base class's own default fires.
    class Versioned(ExtModel):
        __namespace__ = "weft-versioned"
        __schema_version__ = "2.0.0"

    # Act / Assert
    with pytest.raises(SchemaVersionRefusedError) as excinfo:
        Versioned.upgrade({}, "1.0.0")

    assert excinfo.value.namespace == "weft-versioned"
    assert excinfo.value.stored_version == "1.0.0"
    assert excinfo.value.current_version == "2.0.0"
    assert "weft-versioned" in str(excinfo.value)
    assert "1.0.0" in str(excinfo.value)
    assert "2.0.0" in str(excinfo.value)


def test_upgrade_refuses_naming_the_absence_of_a_stored_version_distinctly() -> None:
    # Arrange — `from_version=None` is data written before schema versioning existed,
    # not a version this class simply does not recognise; the message says so.
    class Versioned(ExtModel):
        __namespace__ = "weft-versioned"
        __schema_version__ = "1.0.0"

    # Act / Assert
    with pytest.raises(SchemaVersionRefusedError) as excinfo:
        Versioned.upgrade({}, None)

    assert excinfo.value.stored_version is None
    assert "no version at all" in str(excinfo.value)


def test_upgrade_can_be_overridden_to_migrate_an_older_shape() -> None:
    # Arrange — a pack that can actually reconcile an older version overrides `upgrade`
    # rather than living with the default refusal.
    class Versioned(ExtModel):
        __namespace__ = "weft-versioned"
        __schema_version__ = "2.0.0"

        note: str

        @classmethod
        def upgrade(
            cls, data: Mapping[str, object], from_version: str | None
        ) -> Mapping[str, object]:
            del data, from_version
            return {"note": "migrated"}

    # Act
    migrated = Versioned.upgrade({}, "1.0.0")

    # Assert
    assert migrated == {"note": "migrated"}
    assert Versioned.model_validate(migrated).note == "migrated"
