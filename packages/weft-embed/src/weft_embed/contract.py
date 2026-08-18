"""The `Embedder` contract — published here, never by the kernel.

Specified in `docs/06-phase-0-build.md` step 8. `weft-embed` is the fourth
pack Phase 0 needs and the plan did not originally anticipate — the reasoning
is forced, not a design flourish: G4 forbids a `Store` from embedding
(`docs/02-extension-model.md` → *The store contract family*, "stores never
embed"), G2 has not decided whether embedding is a pipeline stage or a step
inside another one, and a walking skeleton must not depend on a model
download or an API key. Phase 0 puts embedding in the pipeline list as its
own stage — `06`'s minimal, reversible choice for G2's first trap, not an
answer to G2 — which is exactly what forces this contract to exist somewhere
a `Store` cannot own it.

**`Embedder` needs no boundary type of its own**, for the same reason
`weft_chunk.contract.Chunker` does not: `docs/02-extension-model.md` →
*Composition is typed and checked at load* states the ingest path is
`Stage[Seq[Node], Seq[Node]]` throughout, and embedding a `Node` that already
has content but no vector yet is squarely inside that stretch — a `Node` in,
the same `Node` with `embedding` set (via `Node.with_embedding`) out.

**`Embedder` declares `Stage[Sequence[Node], Sequence[Node]]` as one of its
own bases**, per `weft_kernel.runner`'s documented convention — the linear
runner reads a pipeline stage's `In`/`Out` off the *contract* named in its
`StageSpec`, via `__orig_bases__`, never off the plugin implementing it.
`@runtime_checkable` makes capability checkable by `isinstance` rather than
by a declared flag, the same property every other Phase 0 contract shares.
`Embedder.__protocol_attrs__` is exactly `{'run'}` — `Stage` itself declares
nothing beyond `run` (see `weft_kernel.runner`'s module docstring), so a
plugin implementing only `run` satisfies `Embedder`, full stop.

`version` is readable off the class (`Embedder.version`) but is not part of
that `isinstance` membership — see `weft_extract.contract`'s module
docstring for the full reasoning behind the `if TYPE_CHECKING:` /
assign-after-the-class-body split, which applies here unchanged.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
EMBEDDER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Embedder(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Attaches an embedding to each `Node` it is handed.

    One method, domain types on both sides, exactly `Chunker`'s shape one
    stage later in the pipeline. An embedder that finds nothing to embed
    (an empty batch) answers `NothingToProduce`, not an empty `Produced([])`
    — the same reference-trap fix every other Phase 0 contract documents.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Embedder.version = EMBEDDER_CONTRACT_VERSION
