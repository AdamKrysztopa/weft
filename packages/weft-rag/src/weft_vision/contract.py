"""The `Describer` contract — published here, never by the kernel. Ledger task `9.9`.

One method: bytes, what they are, and what to say about them.

**It names the medium, not the model, and that is the whole design.** A contract called
`VisionLLM`, or one taking a `model=` argument, would be a vendor's category leaking into Weft's.
`media_type` is Weft's own vocabulary, and `docs/11-multimodal.md` §2.1 gives the consequence that
makes it worth insisting on: *"the same contract covers audio transcription later"*. Which
implementation runs, and what it costs, is a plugin name in a pipeline document and a `with:` block
beside it.

**A service, not a stage.** No pipeline position, no `run`, no `Stage[In, Out]` base. `TokenSink` is
the precedent for a service without one, and `weft_kernel.seam` wraps stages and `flush` and nothing
else — which is why nothing on this contract produces a `Node`. Two stages consume it at *opposite*
ends of a pipeline: an index-time describer (ledger `9.11`) and a query-side enricher whose name
`docs/10-technique-catalogue.md` §4 reserves and nobody has built. That is the argument for one
service contract rather than an index-only `Enhancer` — an `Enhancer` cannot be reached from the
query path at all.

**It answers `Outcome[str]`, not `str`.** A describer that cannot see the image, or is refused by
its provider, has to be able to say so without raising through a stage that has forty more figures
to get through. `NothingToProduce` and `Failed` are not the same claim — an absence and an error —
and `docs/02-extension-model.md` §1's three-outcome rule is what keeps them apart here as everywhere
else.

**A local or hosted model is the same plugin with a different `base_url`.** That is a constraint on
this module rather than a note about deployment: nothing here may name a provider, a model family,
or a hosting arrangement, and a test reads this file's whole source to make sure nothing does.
"""

from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from weft_kernel.context import ServiceRole
from weft_kernel.payload import Outcome

#: Fitness function 6's subject for this contract — read by AST from this file, never imported.
DESCRIBER_CONTRACT_VERSION = "1.0.0"


@runtime_checkable
class Describer(Protocol):
    """Says what an image (or, later, some other medium) contains, in words.

    `data` is the bytes themselves and `media_type` is the IANA type that says how to read them —
    a plain `str` for the reason `weft_extract.payload.Rendition.media_type` gives: the IANA set is
    open by construction, and a closed enum here would need a member added in a distribution a
    third party does not own.

    `instruction` is what the caller wants said. It is an argument rather than plugin
    configuration because two stages consume this contract for different purposes — an index-time
    describer wants a retrieval-shaped description, a query-side one wants the user's own question
    answered about the image — and a prompt fixed at registration could serve only one of them.
    """

    if TYPE_CHECKING:
        #: Declared for a type checker only and assigned after the class body, so it never joins
        #: `__protocol_attrs__` — a structurally conforming plugin that never restates it must
        #: still satisfy `isinstance`. `weft_extract.contract` carries the reasoning in full.
        version: ClassVar[str]

    async def describe(self, data: bytes, media_type: str, instruction: str) -> Outcome[str]: ...


Describer.version = DESCRIBER_CONTRACT_VERSION

#: Ledger task **9.0** — this pack's declaration that `[services].describe` selects a `Describer`.
#: A plain module-level constant beside the Protocol, never a `ClassVar` on it: a `ClassVar` in a
#: Protocol body breaks `issubclass`, which `weft_extract.contract` records having paid for.
DESCRIBE_ROLE = ServiceRole(key="describe", contract=Describer)
