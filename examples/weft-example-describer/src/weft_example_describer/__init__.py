"""A stranger's describer pack — proof of weft's fitness function 9, clause (c).

Nothing under weft's own `packages/` or `testing/` names this distribution, this module, or the
plugin name below. It is installed from a wheel into an environment that cannot see weft's source
tree, and it registers against a contract it did not write, through the one public entry point
weft's own first-party packs use.

`docs/07-extension-cost.md` §1 names the canonical files: this one, the implementation
(`shape_describer.py`), the `pyproject.toml` beside them and this pack's own tests. A pack
implementing somebody else's contract writes no `contract.py`.
"""

from pydantic import BaseModel, ConfigDict

from weft_example_describer.shape_describer import ShapeDescriber
from weft_kernel.discovery import Disclosure, PackRegistrar
from weft_vision import Describer

#: This pack reads bytes it is handed and reaches nothing at all — said rather than left to be
#: inferred from silence. weft's `02` §2 → *The trust model*.
DISCLOSURE = Disclosure(
    network=(),
    filesystem=(),
    subprocess=(),
    note=(
        "Reads the header of the image bytes it is handed and returns their dimensions. Reaches "
        "no network, no filesystem and no subprocess, and calls no model. An example pack."
    ),
)


class Settings(BaseModel):
    """This pack takes no settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register `ShapeDescriber` as `"example-describer"` for weft's `Describer` contract."""
    del settings
    registrar.add(Describer, "example-describer", ShapeDescriber)


__all__ = ["DISCLOSURE", "ShapeDescriber", "Settings", "register"]
