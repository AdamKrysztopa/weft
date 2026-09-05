"""The `Expander` contract — published here, never by the kernel.

Task **2.31**. `.phase2-findings.md` §11 (BINDING): "a summariser, a question-generator
and a rephraser are three plugins over ONE derived-node mechanism, differing only in what
they generate and how they are configured." This is that mechanism's contract:
`Stage[Sequence[Node], Sequence[Node]]`, the identical shape `weft_chunk.contract.Chunker`
and `weft_enhance.contract.Enhancer` already publish for the same reason — the linear
runner and `weft_kernel.resolution.resolve` read a stage's `In`/`Out` off the *contract*
named in its `StageSpec`, via `__orig_bases__`, never off the plugin implementing it.
`@runtime_checkable` makes capability checkable by `isinstance`, and
`Expander.__protocol_attrs__` is exactly `{'run'}` — a plugin that implements only `run`
satisfies `Expander`, full stop, the same as every sibling contract in this tree.

**What tells `Expander` apart from `Chunker` and `Enhancer`, at the same input/output
shape.** A `Chunker` *replaces* a node with its splits — the document node does not itself
continue past chunking. An `Enhancer` never changes what is indexed at all: it attaches a
fact to the node it was handed, via `Node.with_ext`, and that node's own id and content are
untouched. An `Expander` does the third thing: every node handed in continues, unchanged,
into the output, and new nodes are *added* beside it — each one `parent.derive(content=
...)`, so its id is its own content digest and its `Lineage` names the parent it was built
from. §11's own words: "N representations become N nodes... a hit on any of them resolves
through lineage to the one parent chunk." `hypothetical-questions` (this task) is the
first registration; a summariser and a rephraser are meant to be the second and third,
over this same contract, never a bespoke path apiece — see `weft_index.payload.
Representation` for the marker that lets a citation tell a representation from a passage.

Not opted into `publishes_property_vocabulary`, on `weft_enhance.contract.Enhancer`'s own
footing: an `Expander` never rewrites a node's `content` in place, so it has nothing in
that vocabulary to destroy. A future registration that genuinely does rewrite text opts in
exactly the way `weft_chunk.contract.Chunker` does; nothing about `hypothetical-questions`
forces that decision, so it is left where it was found rather than guessed at.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
EXPANDER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Expander(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Every node handed in, unchanged, plus zero or more nodes derived from it.

    A batch with nothing to expand still answers `NothingToProduce`, never a silently
    empty `Produced([])` — the same ambiguous-empty-case fix every other contract in this
    tree documents. A single node this plugin could not generate a representation for is not
    that case: the node itself is still in the output, unchanged, and only its own
    representations are missing — degrade, never fail the run, the same posture `10` §1.2's
    `raptor` row (task 2.32) states for a summary that cannot be produced, because both
    techniques are meant to share this one mechanism rather than invent their own failure
    policy apiece.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Expander.version = EXPANDER_CONTRACT_VERSION
