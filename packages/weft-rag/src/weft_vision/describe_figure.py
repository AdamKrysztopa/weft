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
  namespace this does not copy. This is `docs/internal/lessons.md` `L9.63`.
- **A `Describer` that cannot help leaves the figure exactly as it was.** `NothingToProduce` is an
  absence, not an error, and `Failed` is a provider's error about one image, not about the document
  — `weft_vision.contract.Describer`'s own docstring: a describer "has to be able to say so without
  raising through a stage that has forty more figures to get through." Neither case synthesises a
  label; `11` §2.4 already names `f'Figure on page {n}'`-shaped template strings *"measurable index
  poisoning"*, and there is no `fallback` counter anywhere in this stage's telemetry.
- **But a batch in which *nothing* could be described is a `Failed` — ledger `9.14`, narrowing the
  clause above.** That clause is about *one figure among many* and it was written to cover all of
  them, which made a completely dead capability indistinguishable from a corpus of uninformative
  images. Phase 9's exit demonstration is what found it: `weft index` through
  `index-pdf-described` stored an `IMAGE` node carrying its caption, no `weft-vision` namespace,
  exit code `0`, and nothing anywhere saying why — while the real cause was a `BlockingCallError`
  that `openai-vision` built its SDK client on the event loop thread, converted by that plugin's
  own broad handler into a `Failed` this stage then discarded. Three green suites, a green gate,
  and `weft plugins doctor` reporting the pack `active` throughout. So: *some* refusals are still
  a success, and *no* success in a batch that asked for one is a failure naming the first reason.
  `09` §6.2's widening test applied to a decision `9.11` recorded in this same phase — the
  original argument survives, its scope does not.
- **A missing `Describer` is a wiring bug, not a legitimate absence.** `ctx.require` raises
  `UnresolvedServiceError` on its own, naming what was wanted and what is available; this module
  does not catch it.

**`Enhancer.__protocol_attrs__` is `{'run'}`, structural.** This class never imports the contract to
subclass it — the same path every third-party `Enhancer` pack is expected to take.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from weft_blob.contract import BlobStore
from weft_blob.payload import BlobRef
from weft_kernel.context import Context
from weft_kernel.payload import (
    Applies,
    ExtModel,
    Failed,
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
        described: list[Node] = []
        failures: list[str] = []
        asked = 0
        succeeded = 0
        for node in payload:
            outcome = await _describe_one(node, blobs=blobs, describer=describer)
            described.append(outcome.node)
            asked += outcome.asked
            succeeded += outcome.described
            if outcome.failure is not None:
                failures.append(outcome.failure)
        if asked and not succeeded and failures:
            # **A batch where nothing could be described is a failure, and this is `9.14`'s
            # narrowing of `9.11`.** See the module docstring: the "one refused figure is not
            # the document's failure" argument is about *one among many*, and applied to a
            # batch where every figure errored it reported a dead capability as success.
            return Failed(
                reason=(
                    f"no figure in this batch could be described: {len(failures)} asked, "
                    f"{len(failures)} failed. First reason: {failures[0]}"
                )
            )
        return Produced(value=described)


@dataclass(frozen=True, slots=True)
class _Attempt:
    """What one figure's turn produced: the node to keep, and what happened to it.

    Three counters rather than one node, because `run` now has to tell three cases apart that
    all leave the node unchanged — it carried no `BlobRef` and was never a candidate, the
    describer had nothing to say, or the describer *errored*. `9.11` returned a bare `Node` and
    so could distinguish none of them, which is how a batch in which every call failed reported
    itself as an ordinary success.
    """

    node: Node
    #: Whether this node was actually put to the describer at all.
    asked: int = 0
    #: Whether a description came back and was attached.
    described: int = 0
    #: The provider's own reason, when it errored. `None` for both other cases.
    failure: str | None = None


async def _describe_one(node: Node, *, blobs: BlobStore, describer: Describer) -> _Attempt:
    """`node`, augmented if it carries a `BlobRef` and the describer had something to say.

    Any other outcome — no `BlobRef` to read pixels from, `NothingToProduce`, or `Failed` —
    leaves `node` exactly as it was: the same node, same id, nothing about it changed. What
    changed at `9.14` is that the three are no longer *reported* alike; see `_Attempt`.
    """
    blob_ref = node.ext_as(BlobRef)
    if blob_ref is None:
        return _Attempt(node=node)

    data = await blobs.open(blob_ref.uri)
    outcome = await describer.describe(data, blob_ref.media_type, _INSTRUCTION)
    if isinstance(outcome, Failed):
        return _Attempt(node=node, asked=1, failure=outcome.reason)
    if not isinstance(outcome, Produced):
        return _Attempt(node=node, asked=1)

    described = node.derive(
        content=f"{node.content}{_JOIN}{outcome.value}", media_type=node.media_type
    )
    described = _carry_forward(described, original=node)
    return _Attempt(
        node=described.with_ext(FigureDescription(description=outcome.value)),
        asked=1,
        described=1,
    )


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
