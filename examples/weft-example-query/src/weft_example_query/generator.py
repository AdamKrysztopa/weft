"""`ExampleGenerator` — a stranger's `Generator`: quotes each passage's first sentence, cited.

No model call — a citation mechanism should not need one to be checkable, and this is the
plugin that proves `weft_generate.payload.Answer`'s citation obligation is satisfiable by a
generator with no vendor behind it at all: every `Citation.marker` this class writes names a
`Passage.label` that entered the prompt, so `Answer._citations_resolve` never has cause to
refuse what this plugin builds.
"""

import re
from typing import Final

from weft_generate.payload import Answer, AnswerStance, Citation
from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_retrieve.payload import Passages

NAME = "example-cite-first-sentence"

_SENTENCE_BREAK: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")


class ExampleGenerator:
    """Answers with each offered passage's first sentence, cited by the label a `ContextPacker`
    assigned it. Satisfies `weft_generate.contract.Generator` structurally.
    """

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, payload: Passages, ctx: Context) -> Outcome[Answer]:
        del ctx
        if not payload.passages:
            return Produced(
                value=Answer(
                    origin=payload.origin,
                    text="I don't know.",
                    stance=AnswerStance.NOT_IN_CORPUS,
                    answered_by=NAME,
                )
            )
        sentences: list[str] = []
        citations: list[Citation] = []
        for passage in payload.passages:
            quote = _first_sentence(passage.node.content)
            sentences.append(f"{quote} {passage.label}")
            citations.append(
                Citation(
                    marker=passage.label,
                    node_id=passage.node.id,
                    source_id=next(iter(passage.node.lineage.sources), None),
                    quote=quote,
                )
            )
        return Produced(
            value=Answer(
                origin=payload.origin,
                text=" ".join(sentences),
                citations=tuple(citations),
                used=payload.passages,
                answered_by=NAME,
            )
        )


def _first_sentence(content: str) -> str:
    return _SENTENCE_BREAK.split(content.strip(), maxsplit=1)[0].strip()
