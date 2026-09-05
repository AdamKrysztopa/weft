"""First-party index-path pack.

Publishes the `Expander` contract (`contract.py`) and the marker every representation it
derives carries (`payload.py`). Task **2.31**: "a chunk can be found by a question it
answers rather than by the words it contains, because a generated question is its own
retrievable node." `hypothetical-questions` was the first plugin here; task **2.32** adds
`raptor` — "a query too broad for any one chunk is answerable, because summaries of
clustered chunks are themselves retrievable nodes." Both arrive with their own registered
`Prompt` in the same `register()` call — the shape every first-party pack in this tree that
asks a model a question already takes (`weft_retrieve.__init__`, `weft_generate.__init__`):
a prompt belongs to the plugin that asks it, not to `weft-prompts`, which registers nothing
of its own.

**A new distribution, not a new position inside `weft-retrieve` or `weft-generate`.**
`.phase2-design.md` §A.3: "putting them in `weft-retrieve` would make a retrieval-only
deployment carry an indexing-time LLM dependency" — the same reasoning that split
`weft-generate` from `weft-retrieve` in the first place (task 2.4), applied one layer over:
an *index-only* deployment (batch-ingest a corpus, serve queries from a separately deployed
reader) should not have to install the query-path's fusion, reranking and Boolean-parsing
machinery merely to expand a chunk into the questions it answers or the summaries that
stand in for a cluster of them.
"""

from pydantic import BaseModel, ConfigDict

from weft_index.contract import EXPANDER_CONTRACT_VERSION, Expander
from weft_index.hypothetical_questions import (
    NAME as HYPOTHETICAL_QUESTIONS_NAME,
)
from weft_index.hypothetical_questions import (
    HypotheticalQuestionGenerator,
    HypotheticalQuestionsConfig,
)
from weft_index.payload import Representation
from weft_index.prompts import (
    GENERATE_QUESTIONS_NAME,
    SUMMARIZE_CLUSTER_NAME,
    GenerateQuestionsPrompt,
    GenerateQuestionsRequest,
    SummarizeClusterPrompt,
    SummarizeClusterRequest,
)
from weft_index.raptor import NAME as RAPTOR_NAME
from weft_index.raptor import RaptorConfig, RaptorSummarizer
from weft_kernel.discovery import PackRegistrar
from weft_prompts.contract import Prompt


class Settings(BaseModel):
    """`weft-index` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register both `Expander`s and both `Prompt`s this pack owns, and `Representation` as
    this pack's own `ExtModel` — task 5.2g, see `weft_chunk.__init__`'s own module
    docstring for the full argument for why this costs no `weft-store` dependency.
    """
    del settings
    registrar.add(Expander, HYPOTHETICAL_QUESTIONS_NAME, HypotheticalQuestionGenerator)
    registrar.add(Prompt, GENERATE_QUESTIONS_NAME, GenerateQuestionsPrompt)
    registrar.add(Expander, RAPTOR_NAME, RaptorSummarizer)
    registrar.add(Prompt, SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt)
    registrar.add_ext_model(Representation)


__all__ = [
    "EXPANDER_CONTRACT_VERSION",
    "GENERATE_QUESTIONS_NAME",
    "HYPOTHETICAL_QUESTIONS_NAME",
    "RAPTOR_NAME",
    "SUMMARIZE_CLUSTER_NAME",
    "Expander",
    "GenerateQuestionsPrompt",
    "GenerateQuestionsRequest",
    "HypotheticalQuestionGenerator",
    "HypotheticalQuestionsConfig",
    "RaptorConfig",
    "RaptorSummarizer",
    "Representation",
    "Settings",
    "SummarizeClusterPrompt",
    "SummarizeClusterRequest",
    "register",
]
