"""The payload types — the domain model every stage signature names.

Settled in G5. `NodeId`, `SourceId`, `Lineage`, `MediaType`, `Node`, `ExtModel`,
`ExtMap`, `Vector` and `Outcome`. See `docs/02-extension-model.md` section 1.

`Property` is G2's addition (task 1.2, `02` §3 → *Ordering constraints*): the
marker `intact`/`destroys` name, on the same namespaced-tag footing
`ExtModel` gives `requires`/`provides`, but never itself node data.

`Applies` is G2's other addition (task 1.6, `02` §3 → *Applicability*): what
a stage's `applies_to` tuple carries — a fact, declared as data, that the
runner evaluates at the seam. See `weft_kernel.payload.applicability`.
"""

from weft_kernel.payload.applicability import Applies
from weft_kernel.payload.ext import ExtMap, ExtModel
from weft_kernel.payload.ids import NodeId, SourceId
from weft_kernel.payload.lineage import Lineage
from weft_kernel.payload.media_type import MediaType
from weft_kernel.payload.node import Node, SyntheticOrigin
from weft_kernel.payload.outcome import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.payload.property import Property
from weft_kernel.payload.vector import Vector

__all__ = [
    "Applies",
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
    "Property",
    "SourceId",
    "SyntheticOrigin",
    "Vector",
]
