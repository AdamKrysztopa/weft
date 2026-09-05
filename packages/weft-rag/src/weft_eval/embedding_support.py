"""Shared "embed some text through whatever `Embedder` this run configured" helper.

Task **4.2**. Three metrics need it: `weft_eval.embedding_metrics.EmbeddingSimilarity` and two of
the six LLM judges (`weft_eval.judges.AnswerRelevance`, `weft_eval.judges.AnswerCorrectness`) — the
two the reference computes with `sentence_transformers` cosine similarity
(`.phase4-reference-recon.md` §7). All three reuse `weft_embed.contract.Embedder` instead, which is
what lets every one of them run against `hash` in an offline gate and against a real provider in
production with no code of their own changing — see `weft_eval.embedding_metrics`'s module
docstring for the full argument. Factored out once rather than written three times, so the
`Node.synthetic`/`embedder.run` sequence has exactly one place to be right.
"""

import math
from collections.abc import Sequence

from weft_embed.contract import Embedder
from weft_kernel.context import Context
from weft_kernel.payload import Failed, MediaType, Node, Outcome, Produced, Vector


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    """Cosine similarity of two equal-length embedding vectors, `0.0` for a zero vector."""
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


async def embed_texts(
    embedder: Embedder, texts: Sequence[str], ctx: Context
) -> Outcome[tuple[Vector, ...]]:
    """Every string in `texts`, embedded in order, or `Failed` naming what went wrong.

    Each string becomes a throwaway `Node.synthetic` — this helper's own caller never needs the
    node identity, only the vector it comes back carrying.
    """
    nodes = tuple(
        Node.synthetic(content=text, media_type=MediaType.TEXT, reason="weft-eval embedding")
        for text in texts
    )
    outcome = await embedder.run(nodes, ctx)
    if not isinstance(outcome, Produced):
        return Failed(reason=f"embedding failed: {outcome}")

    vectors: list[Vector] = []
    for node in outcome.value:
        if node.embedding is None:
            return Failed(reason="the configured embedder produced no vector for one input")
        vectors.append(node.embedding)
    return Produced(value=tuple(vectors))


__all__ = ["cosine_similarity", "embed_texts"]
