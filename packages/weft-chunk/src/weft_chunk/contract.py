"""The `Chunker` contract — published here, never by the kernel.

Specified in `docs/06-phase-0-build.md` step 7 and `docs/02-extension-model.md`
section 1. Unlike `Extractor` (`weft-extract`), `Chunker` needs no boundary
type of its own: `docs/02-extension-model.md` → *Composition is typed and
checked at load* states the ingest path is `Stage[Seq[Node], Seq[Node]]`
throughout once extraction has produced the first `Node`s, and chunking is
squarely inside that stretch — a `Node` in, more (smaller) `Node`s out, each
one built through `Node.derive` so lineage is carried automatically.

**`Chunker` declares `Stage[Sequence[Node], Sequence[Node]]` as one of its
own bases**, per `weft_kernel.runner`'s documented convention: the linear
runner reads a pipeline stage's `In`/`Out` off the *contract* named in its
`StageSpec`, via `__orig_bases__`, never off the plugin implementing it.
`@runtime_checkable` is what makes capability checkable by `isinstance`
rather than by a declared flag, the same property `docs/02-extension-model.md`
→ *The store contract family* states for the store family and this contract
shares by construction, not by a special case. `Chunker.__protocol_attrs__`
is exactly `{'run'}` — `Stage` itself declares nothing beyond `run` (see
`weft_kernel.runner`'s module docstring), so a plugin that implements only
`run` satisfies `Chunker`, full stop.

`version` is readable off the class (`Chunker.version`) but is not part of
that `isinstance` membership — see `weft_extract.contract`'s module
docstring for the full reasoning behind the `if TYPE_CHECKING:` /
assign-after-the-class-body split, which applies here unchanged: fitness
function 6 gains a second subject without capability gaining a fourth member
it never asked for.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
CHUNKER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Chunker(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Splits `Node`s into smaller `Node`s, each one a child under `Node.derive`.

    One method, domain types on both sides, exactly `Extractor`'s shape one
    stage later in the pipeline. A chunker that finds nothing to split
    answers `NothingToProduce`, not an empty `Produced([])` — the same
    reference-trap fix `weft_extract.contract.Extractor` documents, applied here
    because the same ambiguity is possible at every stage that returns a
    sequence.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Chunker.version = CHUNKER_CONTRACT_VERSION
