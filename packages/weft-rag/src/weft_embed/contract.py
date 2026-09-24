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

**`IdentifiedEmbedder` joins the family at task 34.4, `weft_store.contract.NodeSupersedable`'s
precedent: a new optional one-member Protocol beside the base, not a member added to `Embedder`
itself.** `Embedder.__protocol_attrs__` is exactly `{'run'}` — adding a second required member
there would be a major for every third-party implementer under G9's table, for a capability most
embedders can already state and a few genuinely cannot (a stranger with no declared model).
`embedding_model` is what a target's `claim_embedding` and a query's identity check are built on
(`weft_engine.targets`) — the model and width an embedder actually calls with, not a stage's
config default. `1.0.0` → `1.1.0`: a new optional Protocol is minor for both audiences, the same
reasoning `NodeSupersedable` recorded for the store family.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context, ServiceRole
from weft_kernel.payload import Node, Outcome
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
EMBEDDER_CONTRACT_VERSION = "1.1.0"


@runtime_checkable
class Embedder(Stage[Sequence[Node], Sequence[Node]], Protocol):
    """Attaches an embedding to each `Node` it is handed.

    One method, domain types on both sides, exactly `Chunker`'s shape one
    stage later in the pipeline. An embedder that finds nothing to embed
    (an empty batch) answers `NothingToProduce`, not an empty `Produced([])`
    — the same fix every other Phase 0 contract documents for collapsing a
    legitimately empty result into the same ambiguous case as a failure.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        """Attach an embedding to each node in `payload`.

        Args:
            payload: The nodes to embed.
            ctx: The run's context.

        Returns:
            `Produced` carrying the embedded nodes, or `NothingToProduce` when there were none.
        """
        ...


Embedder.version = EMBEDDER_CONTRACT_VERSION


class EmbeddingModel(BaseModel):
    """The model and width one call to `embedding_model` reports.

    The model and width one call to `embedding_model` reports — the request an embedder
    actually sends, never a stage's config default. `width` is `None` when the model's
    dimensionality is not fixed by the embedder itself (an API embedder that has not been
    asked to truncate).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str
    width: int | None


@runtime_checkable
class IdentifiedEmbedder(Protocol):
    """An embedder that can state what it embeds with.

    An embedder that can state what it embeds with — one member, `NodeSupersedable`'s
    shape (`weft_store.contract`), for the same reason: growing `Embedder` itself would be a
    major for every third-party implementer, for a capability most already have and a
    stranger with no declared model does not.
    """

    if TYPE_CHECKING:
        #: See `Embedder.version`'s note above — the same `if TYPE_CHECKING:` mechanism,
        #: assigned below.
        version: ClassVar[str]

    async def embedding_model(self) -> EmbeddingModel:
        """Report the model and width this embedder's requests actually use.

        Returns:
            The model name and, when the embedder fixes it, the vector width.
        """
        ...


IdentifiedEmbedder.version = EMBEDDER_CONTRACT_VERSION

#: Ledger task **9.0** — `weft_embed`'s own declaration that `[services].embed` selects an
#: `Embedder`. A plain module-level constant beside the Protocol, never a `ClassVar` on
#: `Embedder` itself: `typing.Protocol` computes `__protocol_attrs__` by walking the class
#: body once, so a marker placed there would become a *required* structural member — see
#: `weft_extract.contract` (`:44-56`) for the identical reasoning about `version`.
EMBED_ROLE = ServiceRole(key="embed", contract=Embedder)
