"""The payload types — the domain model every stage signature names.

Settled in G5. `NodeId`, `SourceId`, `Lineage`, `MediaType`, `Node`, `ExtModel`,
`ExtMap`, `Vector` and `Outcome`. See `docs/02-extension-model.md` section 1.
"""

from weft_kernel.payload.ext import ExtMap, ExtModel
from weft_kernel.payload.ids import NodeId, SourceId
from weft_kernel.payload.lineage import Lineage
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node, SyntheticOrigin
from weft_kernel.payload.outcome import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.payload.vector import Vector

__all__ = [
    "ExtMap",
    "ExtModel",
    "Failed",
    "Lineage",
    "MediaType",
    "Node",
    "NodeId",
    "NothingToProduce",
    "Outcome",
    "Produced",
    "SourceId",
    "SyntheticOrigin",
    "Vector",
]
