"""The `Cleaner` contract — published here, never by the kernel.

Task **1.7**, `docs/01-high-level-plan.md` → Phase 1 **Lift**. Shaped exactly
the way `weft_chunk.contract.Chunker` is —
one `Node` sequence in, a repaired `Node` sequence out — because `docs/02-
extension-model.md` → *No canonical ingest order* says cleaning is not one
thing, just several stages that happen to share this contract: "hyphenation
repair wants to precede chunking... while whitespace normalization must
follow a structure-aware chunker." A `Cleaner` never knows where in a
pipeline it sits; what it knows is what has to be true of the text it is
handed, stated through `intact`, and what it does to that text, stated
through `destroys` — see `weft_clean.property`.

**`Cleaner` declares `Stage[Sequence[Node], Sequence[Node]]` as one of its own
bases**, the identical convention `Chunker` documents: the linear runner
reads a stage's `In`/`Out` off the *contract* named in its `StageSpec`, via
`__orig_bases__`, never off the plugin implementing it. `@runtime_checkable`
makes capability checkable by `isinstance`, and `Cleaner.__protocol_attrs__`
is exactly `{'run'}` — a plugin that implements only `run` satisfies
`Cleaner`, full stop, the same way a stray `HyphenationRepair`-shaped class
from any third-party pack would.

`version` and `publishes_property_vocabulary` are declared under
`if TYPE_CHECKING:` and assigned after the class body, for the reason
`weft_chunk.contract`'s module docstring gives in full: neither may join
`__protocol_attrs__`, or a structurally-conforming plugin that never restates
them would fail an `isinstance` check that has nothing to do with capability.

**`publishes_property_vocabulary = True` is this task's whole point, made
mechanical.** `docs/02-extension-model.md` §3 → *Ordering constraints*:
"`destroys` is mandatory wherever a contract publishes a property
vocabulary." `weft_kernel.registry` reads this attribute generically off
*any* contract — never a hardcoded list of contract names — so opting in
here is the entire mechanism: every `Cleaner` implementation, first-party or
not, must state `destroys` explicitly or registration refuses it, naming the
missing declaration. This is what turns an ordering requirement that would
otherwise live only as a warning comment into a check
`weft_kernel.resolution.resolve` runs on every pipeline that names a
`Cleaner` stage.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
CLEANER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Cleaner(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Repairs or normalises a `Node`'s text, one node in, one repaired node out.

    A cleaning stage's job is narrower than a chunker's: it never splits or
    merges nodes, so every implementation returns exactly as many nodes as it
    was handed, each built through `Node.derive` so lineage records the
    repair as its own step. A batch with nothing to clean still answers
    `NothingToProduce`, never a silently empty `Produced([])` — the same fix
    `weft_extract.contract.Extractor` and `weft_chunk.contract.Chunker`
    already document for collapsing a legitimately empty result into the
    same ambiguous case as a failure, applied here because the same
    ambiguity is possible at every stage returning a sequence.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]
        publishes_property_vocabulary: ClassVar[bool]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Cleaner.version = CLEANER_CONTRACT_VERSION
Cleaner.publishes_property_vocabulary = True
