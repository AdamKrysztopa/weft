"""`ExampleExtractor` — a stranger's `Extractor`: one root node per source document.

Decodes UTF-8 (best effort — `errors="replace"`, so a source with a stray non-UTF-8 byte
still produces a node rather than raising) and drops a document that is blank after
decoding, the same "a stage says what it actually did" posture
`weft_example_chunker.word_chunker.WordChunker` documents for its own empty case: a batch
that drops every document answers `NothingToProduce`, never a silently empty `Produced([])`.
"""

from collections.abc import Sequence

from weft_extract.contract import SourceDoc
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced


class ExampleExtractor:
    """Turns each `SourceDoc` into one synthetic root `Node`.

    Satisfies `weft_extract.contract.Extractor` structurally — this class never imports it,
    the same path every third-party extractor pack is expected to take.
    """

    def __init__(self, config: object = None) -> None:
        # No `with:` configuration this extractor takes — the runner's factory call always
        # passes a `spec.config` (`None` when a `StageSpec` names none).
        del config

    async def run(self, payload: Sequence[SourceDoc], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        nodes = [
            Node.synthetic(
                content=text,
                media_type=MediaType.TEXT,
                reason=f"extracted from {doc.uri}",
                sources=frozenset({doc.source_id}),
            )
            for doc in payload
            if (text := doc.content.decode("utf-8", errors="replace").strip())
        ]
        if not nodes:
            return NothingToProduce(reason="no source document decoded to non-blank text")
        return Produced(value=nodes)
