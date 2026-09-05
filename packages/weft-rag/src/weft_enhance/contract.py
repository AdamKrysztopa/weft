"""The `Enhancer` contract — published here, never by the kernel.

Task **1.9**, `docs/02-extension-model.md` §3 → *Derivation — driving use case A*: "I
need to add KeyBERT to the `specific` pipeline." That worked example already names its
contract — `weft.toml`'s pin example a few paragraphs later reads `"Enhancer:keybert" =
"weft-kw"` — and §4's graph pack registers "Entity and relation extractor | `Enhancer`".
Neither prior task published it, because neither needed a plugin to run under it: this
is the first task that hands the kernel a document naming `use: keybert`, so this is
where the contract those examples already assume has to actually exist. `docs/reference/
study/02-discovery-and-config.md:199` confirms the shape is not invented for this task:
the reference's own working axis is `@register_enhancer('keybert')` against an `Enhancer`
family — this contract is the shape that axis is missing, not a new idea.

**`Enhancer` declares `Stage[Sequence[Node], Sequence[Node]]` as one of its own bases**,
the identical convention `weft_chunk.contract.Chunker`, `weft_clean.contract.Cleaner`
and `weft_embed.contract.Embedder` all document: the linear runner and
`weft_kernel.resolution.resolve` both read a stage's `In`/`Out` off the *contract*
named in its `StageSpec`/supplied in `resolve()`'s `contracts` mapping, via
`__orig_bases__`, never off the plugin implementing it. `@runtime_checkable` makes
capability checkable by `isinstance`, and `Enhancer.__protocol_attrs__` is exactly
`{'run'}` — a plugin that implements only `run` satisfies `Enhancer`, full stop.

**What tells `Enhancer` apart from `Cleaner`, at the same input/output shape.** A
`Cleaner` repairs the text already there; an `Enhancer` attaches a new, namespaced
*fact* about a node — via `Node.with_ext`, never `Node.derive` — without touching
`content` at all. `docs/04-reference-inventory.md`'s own row for the reference's enhancer axis
names the shape: "entities, relations, summary, hypothetical_questions, caption" — every
one of those is something *added*, not text *rewritten*. That distinction is why this
contract does not opt into `publishes_property_vocabulary` the way `Cleaner` and
`Chunker` do: `docs/02-extension-model.md` §3 → *Ordering constraints* exists because a
destructive text transform can silently corrupt what an earlier stage needed intact, and
an `Enhancer` that never rewrites `content` has nothing in that vocabulary to destroy.
This is not a claim that no `Enhancer` will ever need an ordering constraint of some
other kind — a future implementation that genuinely does rewrite text opts in exactly
the way `weft_chunk.contract.Chunker` does, by declaring `publishes_property_vocabulary
= True` here; nothing about task 1.9's own driving use case forces that decision, so it
is left where it was found rather than guessed at.

`version` is readable off the class (`Enhancer.version`) but is not part of that
`isinstance` membership — see `weft_extract.contract`'s module docstring for the full
`if TYPE_CHECKING:` / assign-after-the-class-body reasoning, unchanged here.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
ENHANCER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Enhancer(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Attaches a new, namespaced fact to each `Node` it is handed — never rewrites `content`.

    One method, domain types on both sides, exactly `Cleaner`'s shape with a different
    job: where a `Cleaner` returns a *repaired* node built through `Node.derive`, an
    `Enhancer` returns the *same* node with an added `Node.with_ext` fact — identity
    (`node.id`) is unaffected, because nothing about the text changed. A batch with
    nothing to enhance still answers `NothingToProduce`, never a silently empty
    `Produced([])` — the same reference-trap fix every other contract in this tree documents.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Enhancer.version = ENHANCER_CONTRACT_VERSION
