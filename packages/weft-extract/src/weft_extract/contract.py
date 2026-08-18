"""The `Extractor` contract — published here, never by the kernel.

Specified in `docs/06-phase-0-build.md` step 7 and `docs/02-extension-model.md`
section 1 ("Who publishes a contract", "The payload model"). G1 draws the
line exactly: the kernel expresses, loads and runs contracts it knows
nothing about, and this is the first one Phase 0 actually publishes — a
newcomer opening `weft-kernel` finds no `Extractor` anywhere, by design.

**`SourceDoc` is this contract's own boundary type, not the kernel's.**
`docs/02-extension-model.md` section 1's own narrowing note writes the
target shape directly: `class Extractor(Stage[Seq[SourceDoc], Seq[Node]],
Protocol)`. Everywhere else in the ingest path a `Node` is both the input
and the output (`Chunker`, the store stage) — extraction is the one stage
that has not produced a `Node` yet, so it needs a type for "a document, not
yet parsed" that `weft-kernel` has no reason to own: `Node` is a *parsed*
unit of content, and a source document is domain vocabulary specific to
extraction, exactly the same reasoning `weft-store` applies to
`SourceRecord`. `content` is `bytes` rather than `str` because an extractor
is what decides how to decode a source — `weft-extract`'s own text extractor
(`06` step 8) reads UTF-8, but nothing about this contract should assume
every implementation does.

**`Extractor` declares `Stage[Sequence[SourceDoc], Sequence[Node]]` as one of
its own bases**, per `weft_kernel.runner`'s documented convention: the linear
runner reads a pipeline stage's `In`/`Out` off the *contract* passed in its
`StageSpec`, via `__orig_bases__`, never off the plugin implementing it — see
`runner.py`'s module docstring, *"step 7 is expected to follow this
convention."* `@runtime_checkable` is what makes `docs/02-extension-model.md`
→ *The store contract family*'s "capability is derived, never declared"
verifiable for this contract too: a plugin either has the one method this
Protocol declares, or `isinstance` says so, and there is no separate flag to
write or to lie in. That "one method" claim is literal:
`Extractor.__protocol_attrs__ == frozenset({'run'})`. `Stage[In, Out]` — one
of `Extractor`'s own bases, needed so the runner can read `In`/`Out` off it
via `__orig_bases__` — declares nothing beyond `run` either (see
`weft_kernel.runner`'s module docstring for why `lifetime`, `requires` and
`provides` are deliberately not `ClassVar`s there), so inheriting it adds no
further required member.

`version` is readable directly off the class (`Extractor.version`) — not off
an instance — the same way `docs/08-manuals.md`'s generated contract
reference is specified to read it: "a small script walks the registry...
reads each registered contract's Protocol, docstring and declared version."
It is declared only under `if TYPE_CHECKING:` inside the Protocol body and
assigned for real immediately after the class statement closes. Both steps
matter: `typing.Protocol` computes `__protocol_attrs__` once, by walking
every attribute (and bare annotation) present in the class's own body at
that moment, so a `ClassVar` written directly in the body — the more obvious
spelling — would make `version` a *required* `isinstance` member, and a
third-party `Extractor` that implements `run` but never restates `version`
would fail a capability check that has nothing to do with capability. The
`TYPE_CHECKING` guard keeps the declaration visible to a type checker
without it ever executing at import time; assigning after the class body
means the value lands after `__protocol_attrs__` was already computed and
cached, so it never joins that set either way — belt and suspenders, one
line each. Fitness function 6 (`docs/01-high-level-plan.md` → *Fitness
functions*) gains its first subject here: a future check can fail the build
if this contract's shape changes without `version` moving. What a version
*means* — compatibility, deprecation — is G9's, still open; this module
states the mechanical fact FF6 needs and nothing about that policy.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from weft_kernel.context import Context
from weft_kernel.payload import Node, Outcome, SourceId
from weft_kernel.runner import Stage

#: Fitness function 6's subject for this contract — see the module docstring.
EXTRACTOR_CONTRACT_VERSION = "1.0.0"


class SourceDoc(BaseModel):
    """A source document handed to an `Extractor`, before any `Node` exists.

    `source_id` is the identity extraction stamps onto the root `Node` it
    produces (`Node.synthetic(sources={source_id})`) — see `Node.synthetic`
    in `weft_kernel.payload.node` for why a root's `sources` must be
    authored explicitly rather than derived. `content` is undecoded: what
    bytes mean is exactly the judgement an `Extractor` implementation
    exists to make.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_id: SourceId
    uri: str
    content: bytes


@runtime_checkable
class Extractor(Stage[Sequence[SourceDoc], Sequence[Node]], Protocol):
    """Turns source documents into the first `Node`s of an ingest pipeline.

    One method, domain types on both sides — `docs/02-extension-model.md`
    section 1 names the predecessor's `BaseExtractor` as the interface shape
    to copy, one `@abstractmethod extract(...)`, and the failure to fix was
    only ever its dispatch, never its narrowness. `run` is that method,
    async per G6, returning `Outcome` rather than a bare value or an
    envelope with an ambiguous empty case: a source that legitimately yields
    no text answers `NothingToProduce`, distinct from `Failed`, which is the
    fix for the reference's `fail_silently` trap where both looked like the same
    empty result downstream.
    """

    if TYPE_CHECKING:
        #: See the module docstring — declared only for a type checker, assigned for real
        #: after the class body, so it never joins `__protocol_attrs__`.
        version: ClassVar[str]

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]: ...


Extractor.version = EXTRACTOR_CONTRACT_VERSION
