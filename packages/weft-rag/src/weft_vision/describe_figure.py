"""`describe-figure` — a described figure keeps its caption and gains a description. Ledger `9.11`.

`docs/11-multimodal.md` §2.4 stage 4 is unusually specific about what this stage does: *"`requires`
`BlobRef`, `provides` `FigureDescription`. Reads the bytes back through
`ctx.require(BlobStore).open(uri)`, calls `ctx.require(Describer)`, and **augments** the node's
content — caption *and* description — rather than replacing it."* Every clause of that sentence is
load-bearing:

- **Augments, never replaces.** `content = description` would discard the caption a human or the
  source document supplied, and `11` §2.4's own ingest table already picked that caption as the
  honest fallback when nothing else was available — throwing it away here would undo that decision
  one stage later. `_describe_one` joins the two with a blank line (`_JOIN`): a caption reads as a
  short, title-like line and the description as the paragraph elaborating it, the same visual
  convention a captioned figure already uses in prose, and a blank line keeps the boundary between
  them legible even when the description itself happens to start with the caption's own words.
- **Carries every namespace forward.** `Node.derive` drops `ext` on purpose — a fresh piece of
  content has no automatic claim to what was attached to its parent's — but `BlobRef` and
  `PageSpan` are facts about *this* figure that describing it does not change, and `11` §2.4's
  *Query time* paragraph requires the retrieved node's `BlobRef` to stay durable so a vision-capable
  generator can reopen the pixels later. `_carry_forward` below is the same shape and the same
  exclusion `weft_chunk.fixed_size._carry_forward` uses — `SyntheticOrigin` states that a node has
  no real lineage, which is no longer true the moment `derive` gives it a parent, so it is the one
  namespace this does not copy. This is `docs/lessons.md` `L9.63`.
- **A `Describer` that cannot help leaves the figure exactly as it was.** `NothingToProduce` is an
  absence, not an error, and `Failed` is a provider's error about one image, not about the document
  — `weft_vision.contract.Describer`'s own docstring: a describer "has to be able to say so without
  raising through a stage that has forty more figures to get through." Neither case synthesises a
  label; `11` §2.4 already names `f'Figure on page {n}'`-shaped template strings *"measurable index
  poisoning"*, and there is no `fallback` counter anywhere in this stage's telemetry.
- **A missing `Describer` is a wiring bug, not a legitimate absence.** `ctx.require` raises
  `UnresolvedServiceError` on its own, naming what was wanted and what is available; this module
  does not catch it.

**`Enhancer.__protocol_attrs__` is `{'run'}`, structural.** This class never imports the contract to
subclass it — the same path every third-party `Enhancer` pack is expected to take.
"""

from collections.abc import Sequence

from weft_blob.contract import BlobStore
from weft_blob.payload import BlobRef
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    ExtModel,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SyntheticOrigin,
)
from weft_vision.contract import Describer

#: What an index-time description is for, per `Describer`'s own docstring: "an index-time
#: describer wants a retrieval-shaped description" — as opposed to a query-side one answering a
#: user's own question about the image.
_INSTRUCTION = (
    "Describe this figure for a search index: what it shows, its key labels or values, and "
    "anything a reader searching for this topic would expect it to contain."
)

#: Caption and description are two paragraphs, not one run-on sentence — see the module docstring.
_JOIN = "\n\n"


class FigureDescription(ExtModel):
    """The description a `Describer` gave a figure's pixels, attached to the described node.

    Modelled on `weft_enhance.keywords.Keywords`, which is the same shape: one field, no score,
    no confidence — this stage has no basis to fabricate either.
    """

    __namespace__ = "weft-vision"
    __schema_version__ = "1.0.0"

    description: str


class FigureDescriber:
    """Reads a figure's pixels back through `BlobStore`, describes them, and augments `content`.

    Satisfies `weft_enhance.contract.Enhancer` structurally. That contract's own class docstring
    says an enhancer "never rewrites `content`" — this one does, and it is a widening rather than
    a violation of that rule; see `weft_enhance.contract`'s module docstring for the marked note
    recording it, and this module's own docstring for why the rewrite is additive rather than
    destructive.
    """

    applies_to: tuple[Applies, ...] = (Applies(media_type=MediaType.IMAGE),)
    requires: tuple[type[ExtModel], ...] = (BlobRef,)
    provides: tuple[type[ExtModel], ...] = (FigureDescription,)

    def __init__(self, config: object) -> None:
        del config  # this stage takes no configuration

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no figures to describe")
        blobs = ctx.require(BlobStore)
        describer = ctx.require(Describer)
        described = [
            await _describe_one(node, blobs=blobs, describer=describer) for node in payload
        ]
        return Produced(value=described)


async def _describe_one(node: Node, *, blobs: BlobStore, describer: Describer) -> Node:
    """`node`, augmented if it carries a `BlobRef` and the describer had something to say.

    Any other outcome — no `BlobRef` to read pixels from, `NothingToProduce`, or `Failed` — leaves
    `node` exactly as it was: the same node, same id, nothing about it changed. See the module
    docstring for why that is the honest answer rather than a synthesised one.
    """
    blob_ref = node.ext_as(BlobRef)
    if blob_ref is None:
        return node

    data = await blobs.open(blob_ref.uri)
    outcome = await describer.describe(data, blob_ref.media_type, _INSTRUCTION)
    if not isinstance(outcome, Produced):
        return node

    described = node.derive(
        content=f"{node.content}{_JOIN}{outcome.value}", media_type=node.media_type
    )
    described = _carry_forward(described, original=node)
    return described.with_ext(FigureDescription(description=outcome.value))


def _carry_forward(described: Node, *, original: Node) -> Node:
    """`described`, plus every namespace `original.ext` carries except its root-origin marker.

    The same shape and the same exclusion `weft_chunk.fixed_size._carry_forward` uses: `derive`
    drops `ext` on the assumption that a new piece of content has no automatic claim to what was
    attached to the node it came from, which is wrong for a fact — `BlobRef`, `PageSpan` — that is
    still true of this figure after describing it. `SyntheticOrigin` is excluded because it states
    that a node has no real lineage, and `described` was just given one by `derive`.
    """
    for namespace, model in original.ext.items():
        if namespace == SyntheticOrigin.__namespace__:
            continue
        described = described.with_ext(model)
    return described
