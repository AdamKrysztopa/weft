"""An embedding: an ordered, non-empty tuple of components.

Settled in G4: persistence accepts a vector already computed elsewhere; it
is never computed from content directly. `Node.embedding` is this type, or
`None` before an embedding has been computed. Excluded from a node's
content-addressed identity (`node.py`) because it is derived from content
and would otherwise bind an id to whichever model produced it.
"""

from pydantic import BaseModel, ConfigDict, model_validator


class Vector(BaseModel):
    """An embedding: an ordered, non-empty tuple of components."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: tuple[float, ...]

    @model_validator(mode="after")
    def _non_empty(self) -> "Vector":
        if not self.values:
            raise ValueError("Vector must carry at least one dimension")
        return self

    @property
    def dimension(self) -> int:
        return len(self.values)
