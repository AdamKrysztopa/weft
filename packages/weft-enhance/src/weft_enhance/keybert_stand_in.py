"""`KeyBertKeywordExtractor` — a deterministic, frequency-ranked keyword picker. **Not KeyBERT.**

Named for the technique it stands in for, on the exact precedent
`docs/06-phase-0-build.md` step 8 sets for `weft_embed.hash_embedder.HashEmbedder`, and
`CLAUDE.md` records why that precedent exists at all: "a walking skeleton must not
depend on a model download or an API key." The real KeyBERT — Maarten Grootendorst,
*KeyBERT: Minimal keyword extraction with BERT*, Zenodo, 2020,
doi:10.5281/zenodo.4461265 — embeds a document and every candidate n-gram with a
transformer, then ranks candidates by cosine similarity to the document embedding. That
needs a downloaded model exactly the way a real embedder does, which is precisely what
`weft-embed` was built to avoid needing for Phase 0's walking skeleton — the identical
constraint, one pipeline stage later. This class needs none of that: it counts words.

**`docs/10-technique-catalogue.md` does not yet carry a row for `keybert`, and this
docstring says so rather than pointing at one that is not there.** That catalogue's own
`§1.2` is exactly where a *shipped* implementation's provenance belongs once one exists
— see its own header: "Phase 1 work... listed here because they are techniques with
origins." Nothing shipped here is that implementation, so entering a row for it would be
exactly the plausible-but-false citation the catalogue's own worked examples (RAGAS,
"Reverse HyDE") exist to catch, attached to a class this one is not. The citation above
is this module's own, verified directly against the source rather than assumed from the
reference's borrowed name (`docs/reference/study/02-discovery-and-config.md:199`,
`:707-708` — the reference's own `@register_enhancer('keybert')` axis, which this task's
driving use case answers without copying a line of it).

**Deterministic by construction: frequency, filtered, ranked, then broken by first
occurrence.** Every word in a node's content is counted after lower-casing and dropping
a small, fixed English stopword list this module owns outright — no corpus statistics,
no embedding, no network call. Two nodes with identical content always rank identically;
that is the only property this stand-in owes the pipeline it sits in, the same
determinism `weft-embed`'s own docstring states for the identical reason: re-indexing
must be idempotent all the way through.

**Configuration is `top_n`, and nothing else** — `docs/02-extension-model.md` §3's own
worked example, `with: {top_n: 8}`. No `diversity`, no `keyphrase_ngram_range`: those are
knobs the *real* KeyBERT exposes and this stand-in does not implement, so naming them
here would be exactly the plausible-but-false configuration surface
`weft_embed.hash_embedder`'s own docstring already refuses for `HashEmbedder`.

**No `score` alongside each term, on purpose.** The real KeyBERT ranks by cosine
similarity, a number this stand-in has no basis to fabricate — printing a plausible-
looking float next to a word count would misrepresent what ranked it. `Keywords.terms`
is ordered highest-ranked first instead, which is the one fact this implementation can
state honestly.
"""

import re
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict, model_validator

from weft_enhance.keywords import Keywords
from weft_kernel.context import Context
from weft_kernel.payload import Node, NothingToProduce, Outcome, Produced

#: `docs/02-extension-model.md` §3's own pipeline example: `with: {top_n: 8}`.
_DEFAULT_TOP_N = 5

#: A word: a run of letters, apostrophes and internal hyphens kept together — deliberately
#: simple, since this stand-in's whole point is that it needs no NLP model to run at all.
_WORD: Final[re.Pattern[str]] = re.compile(r"[A-Za-z][A-Za-z'-]*")

#: Common English function words, excluded so a frequency count is not dominated by them.
#: Written fresh for this module, not lifted from anywhere — a short, ordinary list any
#: two people asked to write "common English stopwords" from memory would largely agree on.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "between", "both",
        "but", "by", "can", "did", "do", "does", "each", "few", "for", "from", "had",
        "has", "have", "he", "her", "his", "if", "in", "into", "is", "it", "its", "just",
        "more", "most", "my", "no", "not", "of", "on", "only", "or", "other", "our",
        "over", "own", "same", "she", "so", "some", "such", "than", "that", "the",
        "their", "them", "then", "these", "they", "this", "those", "to", "too", "under",
        "very", "was", "we", "were", "will", "with", "you", "your",
    }
)  # fmt: skip

#: Below this length a "word" is usually a fragment (an initial, a stray letter) rather
#: than a keyword candidate — cheap noise reduction, not linguistic filtering.
_MIN_WORD_LENGTH = 3


class KeyBertConfig(BaseModel):
    """`KeyBertKeywordExtractor`'s `with:` config — one real field. See the module docstring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    top_n: int = _DEFAULT_TOP_N

    @model_validator(mode="after")
    def _top_n_is_positive(self) -> "KeyBertConfig":
        if self.top_n < 1:
            raise ValueError(
                f"top_n must be at least 1 — a Keywords list cannot be empty "
                f"by request (got {self.top_n})"
            )
        return self


class KeyBertKeywordExtractor:
    """Attaches a deterministic, frequency-ranked `Keywords` fact to every node it is handed.

    **Not a quality component** — see the module docstring. Satisfies
    `weft_enhance.contract.Enhancer` structurally: this class never imports it, the same
    path every third-party enhancer pack is expected to take.
    """

    config_model: type[KeyBertConfig] = KeyBertConfig

    def __init__(self, config: KeyBertConfig | None = None) -> None:
        self._config = config if config is not None else KeyBertConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx  # no service or locale this stage needs
        if not payload:
            return NothingToProduce(reason="no nodes to extract keywords from")
        enhanced = [
            node.with_ext(Keywords(terms=_top_keywords(node.content, self._config.top_n)))
            for node in payload
        ]
        return Produced(value=enhanced)


def _top_keywords(content: str, top_n: int) -> tuple[str, ...]:
    """`top_n` words from `content`, ranked by frequency then first occurrence — see the module
    docstring, *"Deterministic by construction"*.
    """
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    for index, match in enumerate(_WORD.finditer(content.lower())):
        word = match.group()
        if word in _STOPWORDS or len(word) < _MIN_WORD_LENGTH:
            continue
        counts[word] = counts.get(word, 0) + 1
        first_seen.setdefault(word, index)
    ranked = sorted(counts, key=lambda word: (-counts[word], first_seen[word]))
    return tuple(ranked[:top_n])
