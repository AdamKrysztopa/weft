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

#: `Revisable`'s own, ledger task **10.23** — separate from `EXPANDER_CONTRACT_VERSION`
#: because the two contracts move for different reasons, and a shared constant would leave a
#: reader attributing a bump to the wrong one by hand.
REVISABLE_CONTRACT_VERSION = "1.0.0"


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


@runtime_checkable
class Revisable(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """A stage that revises what is **already stored**, not only the payload it was handed —
    grilling session **G15**'s *Read* face, ledger task **10.23**.

    Every other stage in an ingest document is a pure function of its payload. An incremental
    tree is not: `adrap` must read the summaries a previous run wrote in order to join a new
    document to them instead of founding a second tree beside it. Ledger `10.5` settled that
    `raptor` performs **no store read** and says so in three shipped artefacts, and that
    property is exactly why decision `D2` went unreached for two phases — so the capability
    needed somewhere to live that did not quietly make it true of every `Expander`.

    **The corpus is reached through `ctx.require(NodeStore)`, and there is no new type for it.**
    G13 settled that move for `reconcile`: the primary store, from the context, zero kernel
    lines, no contract change. `NodeStore` already answers *what exists* — `scan`, `count`,
    `matching`, `get` — so a "corpus view" would be a second way to ask the same questions.

    **Why a separate contract rather than letting an `Expander` do it.** Registering the
    capability is what makes it *visible*: `weft pipeline show` prints `Expander:raptor` beside
    `Revisable:adrap`, so a reader of a resolved document can see which stages read the corpus.
    Allowing any `Expander` to call `ctx.require(NodeStore)` would turn `10.5`'s property from a
    fact about a **kind** of stage into a per-plugin habit, with nothing to key a check on and
    nothing to tell a reader — requirement 1's failure shape, an extension point decaying into
    a convention.

    **Structurally identical to `Expander`, and that is stated rather than hidden.** Both are
    `Stage[Sequence[Node], Sequence[Node]]` with `run` alone, so `isinstance` cannot separate
    them and no marker attribute will be added to make it: capability is derived, never
    declared (`02` §1), and a declared marker is one a pack could write falsely. What separates
    them is the contract a pack registers under.
    `tests/unit/weft_index/test_contract.py` pins both halves.

    **Ordering is not this contract's problem, which the session initially got wrong.** G15's
    *Read* face argued that a `Revisable` placed before a document's own `store` stage would
    read a stale corpus and should be refusable at resolution. Re-read against a real document,
    that is not so: `adrap` reads what *previous* runs stored, clusters this run's payload into
    it, and the `store` stage then writes the result — `embed, adrap, store` is the natural
    order and nothing is stale. The refusal that seemed owed is not, and the kernel could not
    have expressed it anyway without naming a capability.

    **Corrected by G16 (2026-09-08): the conclusion holds and the reason above is incomplete.**
    It argues from `adrap`'s *natural* placement, which is a fact about one plugin rather than
    about this contract — and a contract's ordering rule may not rest on its only registration.
    The durable reason is the second clause: semantic order is not a data dependency, so
    `requires`/`provides` cannot express it and the resolver cannot see it. G16 therefore
    **permits** a `Revisable` after `store` rather than leaving it undecided, and states what
    differs: it then reads a corpus already containing this run's own leaves, so `adrap` finds
    them as existing members instead of as arrivals. Nothing breaks — `put` is keyed on a
    content digest and `supersede` is idempotent by contract. A second `Revisable` in one
    document is permitted too, and runs in its declared order like any other stage.

    **How a `Revisable` actually receives the store, which G15 settled and never ran.**
    `ctx.require(NodeStore)` resolves on the ingest path **only because** a document declaring
    a `Revisable` causes `weft_cli.ingest._store_instance_for_revisable` to hand the store
    *stage's own instance* to `build_index_services`. That plumbing is G16's, not G15's: G15
    cited G13's `reconcile` precedent, `reconcile` is not a pipeline stage, and this contract,
    `NodeSupersedable` and `adrap` all shipped green over a call that could not resolve
    (`docs/internal/lessons.md` `L10.40`). An ordinary ingest document still gets no ambient store.
    """

    if TYPE_CHECKING:
        #: See `Expander.version`'s own note — readable off the class, never in
        #: `__protocol_attrs__`, so `isinstance` does not demand it of an implementer.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


Expander.version = EXPANDER_CONTRACT_VERSION
Revisable.version = REVISABLE_CONTRACT_VERSION
