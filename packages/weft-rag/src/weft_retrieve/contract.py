"""The query-path contracts — published here, never by the kernel.

Task **2.4**, `docs/02-extension-model.md` §1 → *Composition is typed and checked at
load*, and `01` → Phase 2's **Read** item. Seven `Stage` subtypes, one named capability
that is not a pipeline position, and two services. Each declares `Stage[In, Out]` as one
of its *own* bases where it is a pipeline position, because `weft_kernel.runner.
_stage_signature` reads the pair off the contract via `__orig_bases__` and never off the
plugin implementing it — the identical convention `weft_chunk.contract.Chunker` and
`weft_embed.contract.Embedder` already document.

**Why four contracts across the middle of the query path rather than one `Strategy`.**
A single `Stage[QuerySet, Answer]` would make every pipeline exactly one stage long, and
`01` → requirement 6's second clause ("shipped technique is parameterisable *and
composable*") would have nothing to compose. Splitting at `Retriever` → `Fuser` →
`Reranker` → `ContextPacker` puts the arity reduction in the type system: `Candidates`
means k lists, `Ranking` means one, so a pipeline that reaches a reranker, a packer or a
generator without having fused does not resolve, and the check that refuses it is the
kernel's own. Publishing a `Strategy` alongside this decomposition was considered and
declined — it would give the router two key spaces to choose between where fitness
function 4 demands the no-closed-key-space property of every one, and `10` §2.1 rule 5
already says a composition is a pipeline.

**The emptiness rule, and it is a contract term, not advice.**
`weft_kernel.runner._run_one_batch` stops a batch the moment a stage answers
`NothingToProduce`, which on a query path means no `Answer` reaches the caller at all —
and `09` §4's V2 *requires* the engine to answer "not in this corpus". So, for every
contract in this module:

> A query-path stage that ran and found nothing returns `Produced` carrying an empty
> collection inside a non-empty payload. `NothingToProduce` means the stage declined to
> act, and the pipeline stops.

**`applies_to` is inert here, stated so it is not rediscovered.**
`weft_kernel.runner._is_routable` engages only for a non-empty `Sequence` whose every
element is a `Node`; a `QuerySet`, a `Ranking` and a `Passages` all take the unfiltered
path silently. No plugin registered under a contract in this module may declare
`applies_to` — "skip hyde for a short query" is hyde's own configuration, never routing.

**No contract here sets `publishes_property_vocabulary`.** A query-path stage rewrites no
node content and destroys no ingest-time property, so making `destroys` mandatory on
every third-party retriever would be a registration tax with no failure behind it —
`weft_enhance/contract.py`'s own declining argument, applied to a different reason.

`version` is readable off each class but is not part of `isinstance` membership — see
`weft_extract.contract`'s module docstring for the full `if TYPE_CHECKING:` /
assign-after-the-class-body reasoning, unchanged here.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import Context
from weft_kernel.payload import Outcome
from weft_kernel.runner import Stage
from weft_retrieve.payload import (
    Assessment,
    Candidates,
    Passages,
    Query,
    QuerySet,
    Ranking,
    Route,
    RouteCandidate,
    Scorecard,
)

#: Fitness function 6's subject for this contract family — one version for the family,
#: not one per Protocol, on `weft_store.contract`'s own precedent: these eight are
#: published together, versioned together, and a change to the query vocabulary they
#: share is a change to all of them.
RETRIEVE_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class QueryTransform(Stage[QuerySet, QuerySet], Protocol):
    """Rewrites, expands or narrows the set of queries that will be retrieved for.

    `Stage[QuerySet, QuerySet]` is what makes a transform omittable by construction
    (ledger 2.15): removing it from a document leaves the seams either side composing
    unchanged, so no strategy pays for a rewrite it did not ask for. It also makes two
    transforms composable in either order, which is how `hyde` then `multi-query` becomes
    a document edit rather than a new plugin.

    A transform must not rewrite `QuerySet.origin` — see that field's own docstring for
    the reference defect the invariant closes.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[QuerySet]: ...


@runtime_checkable
class Retriever(Stage[QuerySet, Candidates], Protocol):
    """Turns queries into ranked lists — one per query per channel, never fused.

    **A retriever never builds its own index** (ledger 2.5): text and vector search are
    things a store *advertises*, reached through `ctx.require(...)` and declared by a
    `needs_store: ClassVar[tuple[type, ...]]` class attribute the run assembler checks
    before any stage runs. `docs/02-extension-model.md` §1 → *The store contract family*
    is the owning text, narrowed in this task to say where the check happens.

    Producing `Candidates` rather than one list is the whole fan-out mechanism: k lists
    with the `Query` and `Channel` that produced each, so a fuser has something to weight
    and so hybrid retrieval and query fan-out arrive at the fuser in the same shape.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: QuerySet, ctx: Context) -> Outcome[Candidates]: ...


@runtime_checkable
class Fuser(Stage[Candidates, Ranking], Protocol):
    """Collapses k ranked lists into one. The arity-reducing position, by definition.

    `Out` being `Ranking` rather than `Candidates` is the load-bearing choice in this
    module: **fan-in is expressed in the type, not by a combinator.** It is also what
    discharges ledger 2.18 with a single implementation — hybrid retrieval and query
    fan-out are the same shape here, because multiplicity is uniform in `Candidates`.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: Candidates, ctx: Context) -> Outcome[Ranking]: ...


@runtime_checkable
class Reranker(Stage[Ranking, Ranking], Protocol):
    """Rescores one list against the question, and returns one list.

    Separate from `Fuser` (ledger 2.7: "not a fixed ladder") so that either can be
    retuned, replaced or omitted in a document without touching the other. Same in and
    out, so a second reranker composes after the first with no new type and no operator.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]: ...


@runtime_checkable
class ContextPacker(Stage[Ranking, Passages], Protocol):
    """Chooses, orders and labels the evidence that will enter a prompt.

    A distinct position rather than a knob on the generator, because `10` §1.1's `repack`
    row is a measured technique with its own parameters, and because the citation labels
    a `Generator` resolves against are assigned here — which is what lets
    `weft_generate.payload.Answer` refuse an unfollowable citation at construction.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Passages]: ...


@runtime_checkable
class QueryScorer(Stage[Query, Scorecard], Protocol):
    """Measures a query along named dimensions. Decides nothing (ledger 2.25).

    Two contracts rather than one so a threshold ladder can be replaced by a trained
    classifier without touching the measurement, and so the router is two ordinary stages
    in an ordinary pipeline rather than an engine — `02` §3, "express the router as a
    stage rather than as an engine."
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: Query, ctx: Context) -> Outcome[Scorecard]: ...


@runtime_checkable
class RoutingPolicy(Stage[Scorecard, Route], Protocol):
    """Turns a scorecard into a named pipeline. The second half of the router.

    `reachable` is deliberately not a `Stage` method — it answers "which of these
    candidates could this policy ever choose?" for `weft plugins doctor` and for the
    registered-but-unroutable check, which is data the caller already holds rather than a
    payload flowing down a pipeline. It is nonetheless `async`, like everything else here:
    `01` → *Colour*, settled in **G6**, is categorical — "every contract method is
    `async def`. There is no sync protocol" — and this is a published contract a third
    party implements, not a service. `weft_kernel.seam.wrap` wraps a coroutine, so a sync
    method on a registered contract would run outside the seam: no span, no error
    attribution, and nothing for FF7(b)'s blocking-call detector to see. A
    `nearest-description` policy whose `reachable` reads a file or calls an embedding
    endpoint would then block the loop thread with the gate unable to notice, which is the
    concern that made G6 categorical in the first place. `.phase2-design.md` §3 calls this
    method "deliberately sync"; that file's own status line says `docs/` wins where they
    disagree, and this is where they did.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def run(self, payload: Scorecard, ctx: Context) -> Outcome[Route]: ...

    async def reachable(self, candidates: Sequence[RouteCandidate]) -> frozenset[str]: ...


@runtime_checkable
class Sufficiency(Protocol):
    """Judges whether the evidence in hand answers the question. **Not a pipeline position.**

    Declares no `Stage[In, Out]` base, on purpose: it takes three arguments, not one
    payload, and it is reached *inside* a looping technique by name through `StageLookup`
    rather than placed in a document. Ledger 2.24 wants the uncertainty signal to be a
    replaceable named thing rather than a phrase list buried in a generator, and a named
    contract with two implementations is what "replaceable" means here.

    An implementation that could not look answers `Assessment(observed=False)`. It must
    never answer `sufficient=False` to mean "I could not tell" — see `Assessment`.
    """

    if TYPE_CHECKING:
        version: ClassVar[str]

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]: ...


class StageLookup(Protocol):
    """The one late-binding seam a looping technique gets. **A service, never registered.**

    Resolved by type through `ctx.require(StageLookup)`, carries no `version`, and is
    never named in a pipeline — the mechanical rule that keeps a service out of the
    contract reference and out of fitness function 9(c)'s left side.

    **Why this is not the service locator `02` §1 rules out.** The reference's locator
    resolved *literal module paths* at import time, untyped and unregistered, reaching
    past its own boundary. This resolves exactly what discovery registered, keyed by a
    published contract type the calling plugin already imports, and it is handed to a
    stage by the run assembler rather than imported by it.

    **Why it exists at all, stated as the departure it is.** A resolved pipeline is a
    finite ordered list, and G2 settled that resolution *checks* an order and never solves
    one — so "retrieve again if the evidence is thin" cannot be said as data without
    turning a document into a program and breaking the closed operator set fitness
    function 11(a) rests on. The concession is that a looping technique is one plugin that
    owns its loop in code and reaches a sibling through here. Its cost is real: `weft
    pipeline show` sees the sibling as a string in a `with:` block rather than as a
    resolved stage, so a looping technique's interior is not diffable the way the top
    level is.

    `build` returns a callable already through `weft_kernel.seam.wrap`, so a sub-plugin
    gets its span, its error attribution, its blocking guard and its transient stripping
    without the calling technique's author writing any of it. An unregistered name raises
    the registry's own `UnknownPluginError`, naming the contract, the name and every valid
    option.
    """

    def names(self, contract: type[object]) -> frozenset[str]: ...

    async def build[In, Out](
        self, contract: type[Stage[In, Out]], name: str, config: object = None
    ) -> Callable[[In, Context], Awaitable[Outcome[Out]]]: ...

    async def build_capability[T](
        self, contract: type[T], name: str, config: object = None
    ) -> T: ...


class RouteCatalogue(Protocol):
    """What pipelines a router may choose between. **A service, never registered.**

    Populated by the same eager discovery pass that builds the registry, from the
    pipelines packs contribute — so a third party's pipeline becomes routable on install
    with no edit anywhere under `packages/`, which is the property ledger 2.8's exit
    demonstration is about.
    """

    def candidates(self) -> tuple[RouteCandidate, ...]: ...

    def names(self) -> frozenset[str]: ...


ContextPacker.version = RETRIEVE_CONTRACT_VERSION
Fuser.version = RETRIEVE_CONTRACT_VERSION
QueryScorer.version = RETRIEVE_CONTRACT_VERSION
QueryTransform.version = RETRIEVE_CONTRACT_VERSION
Reranker.version = RETRIEVE_CONTRACT_VERSION
Retriever.version = RETRIEVE_CONTRACT_VERSION
RoutingPolicy.version = RETRIEVE_CONTRACT_VERSION
Sufficiency.version = RETRIEVE_CONTRACT_VERSION
