"""Fitness function 34 — only a representation marker carries a `technique` field (`L28.18`).

`weft_generate.representation` cites a single-parent node carrying an ext value with a
`technique: str` attribute as its parent, because that is what `weft_index.payload.Representation`
means: a derived node standing in for the chunk it came from. Any other ext model with a field of
that name silently turns a node into a stand-in. `R38.13`'s `ExpansionDegraded` did exactly that to
every degraded chunk, which was then cited as its whole document (`R38.20`). The only check of the
constraint was one pack's unit test over its own three models, so a model added one pack over
was outside it.

The population is every `ExtModel` subclass defined under the first-party packages, found by
importing them, not a list: 27 when this was written, one of them allowed.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Final

from weft_kernel.payload import ExtModel

from .conftest import REPO_ROOT

_SOURCE_ROOTS: Final = tuple(
    path for path in (REPO_ROOT / "packages").glob("*/src") if path.is_dir()
)

#: Ext models whose `technique` field is the representation marker `citable_nodes` reads.
REPRESENTATION_MARKERS: Final[frozenset[str]] = frozenset({"weft_index.payload.Representation"})


def _first_party_ext_models() -> dict[str, type[ExtModel]]:
    tops = {top.name for root in _SOURCE_ROOTS for top in pkgutil.iter_modules([str(root)])}
    for name in tops:
        package = importlib.import_module(name)
        if hasattr(package, "__path__"):
            for info in pkgutil.walk_packages(package.__path__, name + "."):
                importlib.import_module(info.name)
    found: dict[str, type[ExtModel]] = {}
    pending = list(ExtModel.__subclasses__())
    while pending:
        model = pending.pop()
        pending.extend(model.__subclasses__())
        if model.__module__.split(".", 1)[0] in tops:
            found[f"{model.__module__}.{model.__qualname__}"] = model
    return found


def naming_a_technique(models: dict[str, type[ExtModel]]) -> set[str]:
    return {
        name
        for name, model in models.items()
        if "technique" in model.model_fields and name not in REPRESENTATION_MARKERS
    }


def test_the_population_is_not_empty() -> None:
    assert len(_first_party_ext_models()) >= 20


def test_only_a_representation_marker_names_a_technique() -> None:
    # Act
    offenders = naming_a_technique(_first_party_ext_models())

    # Assert
    assert not offenders, (
        "these ext models carry a `technique` field, so `weft_generate.representation` would "
        f"cite any single-parent node carrying one as its parent: {sorted(offenders)}. Rename the "
        "field, "
        "or add the model to REPRESENTATION_MARKERS if it really is a representation marker."
    )


def test_the_check_can_actually_fail() -> None:
    # Arrange
    class Planted(ExtModel):
        __namespace__ = "ff34-planted"
        __schema_version__ = "1.0.0"
        technique: str

    # Act
    offenders = naming_a_technique({"planted.Planted": Planted})

    # Assert
    assert offenders == {"planted.Planted"}
