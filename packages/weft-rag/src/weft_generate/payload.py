"""The answer vocabulary — what leaves the query path and reaches a reader.

Task **2.4**, with task **2.9**'s property ("an answer carries citations a reader can
follow back to a passage") held here *by construction* rather than by a check someone
must remember to run: an `Answer` whose citation resolves to no passage that entered the
prompt raises at validation and therefore cannot be built at all.

**Why `Answer` is published by `weft-generate` and not by `weft-retrieve`.** A boundary
type belongs to the distribution publishing the contract that *produces* it, and
first-party dependencies flow one way along the pipeline — `weft-kernel ← weft-store ←
weft-retrieve ← weft-generate`. The type that would break that is this one:
`refine-on-uncertainty` retrieves again after drafting, so it looks like a `Retriever`
that needs an `Answer`. It is therefore published as a `Generator` and reaches a retriever
through the `StageLookup` service rather than through an import, and that single placement
is what keeps the graph acyclic. Stated here so nobody "fixes" it later by moving the
type up one package.

**`stance` is an enum, not a `refused: bool`.** `09` §4's V2 requires unanswerable
questions in the question set, and ledger 2.22 requires a critic that could not look to
say so. "The corpus does not contain it" and "the engine could not decide" are different
facts about the world; a boolean forces one of them to be reported as the other, which is
the reference's `has_consensus=True`-on-failure defect wearing a different type.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_kernel.payload import ExtMap, NodeId, SourceId
from weft_retrieve.payload import Passage, Query


class AnswerStance(StrEnum):
    """What an answer is claiming about itself. `Enum` per the project's string-constant rule."""

    ANSWERED = "answered"
    NOT_IN_CORPUS = "not-in-corpus"
    UNDETERMINED = "undetermined"


class Citation(BaseModel):
    """One claim's trail back to the passage it rests on.

    `source_id` is optional and `None` is a fact, never a placeholder: a node built
    through `Node.synthetic` — a summary of a cluster, a generated question — genuinely
    has no source document, and `weft_kernel.payload.Lineage` permits that root case
    explicitly. Inventing a source id for one would be a citation a reader could follow to
    somewhere that does not exist, which is worse than a citation that says where it stops.

    `quote` is the span the claim rests on when one is isolable, and empty when it is not.
    `09` §4's V2 pins its judgements to `(source_id, quote)` spans, so this is the field a
    later evaluation reads; leaving it empty says "this claim is not attributable to one
    span", which is a different and honest answer.

    `page` closes the gap this task's own ledger line names: a `node_id` is a content
    digest, and a `uri` alone still leaves a reader searching a whole document for one
    claim. `weft_generate.page.page_for` resolves it, when it can, from two facts a
    chunk carries — `weft_chunk.payload.ChunkOffset` (where this passage's content
    starts in the document it was cut from) and whatever ext model on that same node can
    turn an offset into a page, `weft_pdf.PdfPages` being the one this build ships.
    `None` is not "page 1" and is not omitted silently: it is what this field says when
    the source is not paginated, or when nothing in the pipeline attached either fact —
    a citation that still resolves to *a passage*, just not to a page of one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: What appears in the answer text — the label a `ContextPacker` assigned.
    marker: str = Field(min_length=1)
    node_id: NodeId
    source_id: SourceId | None = None
    uri: str = ""
    quote: str = ""
    page: int | None = Field(default=None, ge=1)


class Answer(BaseModel):
    """What the query path returns: text, the evidence behind it, and what it claims to be.

    `used` is exactly the passages that entered the prompt — not the ranking, not the
    candidates. That is what makes the citation check below decidable, and it is what a
    reader needs to judge the answer without re-running the pipeline.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    origin: Query
    text: str
    citations: tuple[Citation, ...] = ()
    used: tuple[Passage, ...] = ()
    stance: AnswerStance = AnswerStance.ANSWERED
    #: The `Generator` plugin name — provenance for the same reason `Passage.retrieved_by`
    #: is refused empty, and the field a comparison across two derived pipelines reads.
    answered_by: str = Field(min_length=1)
    #: G5's namespaced extension mechanism, reused rather than a second one invented —
    #: `contradiction-check` attaches its `Agreement` here instead of growing two fields
    #: on a type eleven other techniques share. See `weft_retrieve.payload`'s module
    #: docstring for the transient-stripping gap this carries.
    ext: ExtMap = Field(default_factory=dict, validate_default=True)

    @model_validator(mode="after")
    def _citations_resolve(self) -> "Answer":
        """Task 2.9, held by construction rather than by a reviewer noticing.

        A citation resolves when it names **one** passage, so all three ways it can fail to
        are checked and they are not the same failure. A marker naming a label nothing in
        `used` carries is a footnote pointing at nothing. A `node_id` naming a node that
        never entered the prompt is a citation attached to evidence the model never saw.
        And a marker and a `node_id` that each resolve, *to different passages*, is the
        renumbering bug — the common one, and the one a check on the two sets independently
        cannot see: a reader who follows `[1]` lands on the passage the answer does not
        claim to rest on. Two passages in `used` sharing a label is the same defect one step
        earlier, and is refused whether or not a citation names it, because a marker that
        resolves to two passages resolves to none.

        The pairing is decidable precisely because `ContextPacker` exists as its own
        position: this is the type at which the labels are final. `weft_retrieve.payload.
        Passages` refuses a blank or repeated label where they are assigned; this refuses
        one that survived into an answer anyway, at the seam where the generator made its
        mistake rather than in front of a reader.
        """
        by_label: dict[str, list[Passage]] = {}
        for passage in self.used:
            if passage.label:
                by_label.setdefault(passage.label, []).append(passage)
        ids = {passage.node.id for passage in self.used}

        shared = sorted(label for label, group in by_label.items() if len(group) > 1)
        stray_markers = sorted({c.marker for c in self.citations} - set(by_label))
        stray_nodes = sorted(str(c.node_id) for c in self.citations if c.node_id not in ids)
        mispaired = sorted(
            c.marker
            for c in self.citations
            if len(by_label.get(c.marker, ())) == 1 and by_label[c.marker][0].node.id != c.node_id
        )
        if shared or stray_markers or stray_nodes or mispaired:
            raise ValueError(
                f"every citation must resolve into `used`, and to one passage: marker(s) "
                f"{stray_markers or 'none'} match no passage label "
                f"({sorted(by_label) or 'no labelled passages'}); node id(s) "
                f"{stray_nodes or 'none'} name no passage that entered the prompt; "
                f"marker(s) {mispaired or 'none'} name a different passage than their own "
                f"node id does; and label(s) {shared or 'none'} are carried by two passages "
                f"at once. An answer whose citation a reader cannot follow is what task 2.9 "
                f"makes unconstructable."
            )
        return self
