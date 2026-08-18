"""The prompts `weft-index`'s two `Expander`s ask. The registered `Prompt`s in this pack.

Task **2.31**. One call per node, freeform text back (`output_model = None`), one question
per line — the same "boring", cascade-free shape `weft_generate.cited_answer` takes for its
own completion, chosen deliberately over the numbered-offer-and-parse, structured-cascade
shape `weft_retrieve.transforms.MultiQuery` uses for its own batched fan-out.
`.phase2-design.md` is silent on which an index-path `Expander` should take, and this
build's smallest defensible choice is the simpler one: `weft_prompts.contract.Prompts` — a
per-name render-and-nothing-else service this pack already needs `weft-prompts` for — is
then the whole surface `hypothetical-questions` needs from a prompt, and `weft-index` adds
no dependency on `weft-retrieve` to reach it. See `weft_index.hypothetical_questions`'s own
module docstring for the batching question and why per-node calls, run concurrently, is the
answer here.

**"Must not quote the passage's own wording back verbatim" is not a politeness — it is the
property task 2.31's own exit demonstration checks.** `docs/build-ledger.md`: "a question
whose wording appears nowhere in the corpus retrieves the chunk that answers it." A question
built by lifting the passage's own sentence would retrieve by keyword overlap, which is the
retrieval this technique exists to go *past* — doc2query's whole premise (Nogueira, Yang,
Lin & Cho, *Document Expansion by Query Prediction*, arXiv:1904.08375, 2019) is that a model
predicts the *questions* a passage answers, not a copy of the passage restated as a
question.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under, and `hypothetical-questions`'s
#: own default `prompt:` configuration.
GENERATE_QUESTIONS_NAME = "generate-questions"


class GenerateQuestionsRequest(BaseModel):
    """What `generate-questions` renders: one passage, and how many questions to write for it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passage: str
    count: int = Field(ge=1)


class GenerateQuestionsPrompt(TypedPrompt):
    """Ask a model for the questions one passage answers, in the passage's own language.

    The English text is the fallback every locale degrades to; the Polish one exists
    because the corpus this engine is measured against has a Polish subset (`09` §4), and
    the parsing this pack does (`weft_index.hypothetical_questions._parse_questions`) has
    to work on whichever language the model actually wrote in — `TypedPrompt`'s own rule
    that a locale nobody translated degrades the language, which a reader can see, never
    the answer, which they cannot.
    """

    name: ClassVar[str] = GENERATE_QUESTIONS_NAME
    input_model: ClassVar[type[BaseModel]] = GenerateQuestionsRequest
    output_model: ClassVar[type[BaseModel] | None] = None
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You write the questions a passage answers, for a search index. Each "
                "question must be answerable from the passage alone, written in the "
                "passage's own language, and must not quote the passage's own wording "
                "back — ask about what it says, in different words."
            ),
            user=(
                "Passage:\n${passage}\n\n"
                "Write exactly ${count} distinct questions this passage answers. One "
                "question per line, no numbering, no bullets, nothing else."
            ),
        ),
        "pl": PromptText(
            system=(
                "Piszesz pytania, na które odpowiada podany fragment tekstu, na potrzeby "
                "wyszukiwarki. Każde pytanie musi dać się odpowiedzieć wyłącznie na "
                "podstawie fragmentu, napisane w jego własnym języku, i nie może dosłownie "
                "cytować sformułowań z fragmentu — pytaj o to, co fragment mówi, innymi "
                "słowami."
            ),
            user=(
                "Fragment:\n${passage}\n\n"
                "Napisz dokładnie ${count} różnych pytań, na które odpowiada ten "
                "fragment. Jedno pytanie na linię, bez numeracji, bez wypunktowania, nic "
                "więcej."
            ),
        ),
    }


#: The name this prompt is registered and selectable under, and `raptor`'s own default
#: `prompt:` configuration.
SUMMARIZE_CLUSTER_NAME = "summarize-cluster"


class SummarizeClusterRequest(BaseModel):
    """What `summarize-cluster` renders: one cluster of passages, already numbered and
    joined into one string.

    `passages: str`, not `tuple[str, ...]` — `weft_retrieve.prompts.PassageGradeRequest`'s
    own precedent for a batch offered to a template: joining is the plugin's own job
    (`weft_index.raptor._format_cluster`), because a template substitution has no loop
    construct of its own to number and separate a variable-length sequence with.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    passages: str


class SummarizeClusterPrompt(TypedPrompt):
    """Ask a model for the one summary that stands in for a cluster of passages, in the
    cluster's own dominant language.

    Task **2.32**, `10` §1.2's `raptor` row, citing Parth Sarthi, Salman Abdullah, Aditi
    Tuli, Shubh Khanna, Anna Goldie, Christopher D. Manning, *RAPTOR: Recursive Abstractive
    Processing for Tree-Organized Retrieval*, ICLR 2024, arXiv:2401.18059 — the paper's own
    claim is that a query too broad for any one chunk is answerable from a summary
    *because* the summary was built by abstracting several chunks together, not by
    concatenating them; the system prompt says so, the same way `generate-questions`'
    own system prompt states doc2query's premise rather than leaving it implicit.
    """

    name: ClassVar[str] = SUMMARIZE_CLUSTER_NAME
    input_model: ClassVar[type[BaseModel]] = SummarizeClusterRequest
    output_model: ClassVar[type[BaseModel] | None] = None
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You write a single abstractive summary for a cluster of related "
                "passages, for a search index. The summary must stand on its own: "
                "someone who has read only the summary should learn what the whole "
                "cluster is about, in the cluster's own language, without needing to "
                "read any one passage."
            ),
            user=(
                "Passages:\n${passages}\n\n"
                "Write one summary covering everything the passages above have in "
                "common. Reply with the summary alone, nothing else."
            ),
        ),
        "pl": PromptText(
            system=(
                "Piszesz jedno abstrakcyjne streszczenie dla grupy powiązanych "
                "fragmentów tekstu, na potrzeby wyszukiwarki. Streszczenie musi być "
                "zrozumiałe samodzielnie: osoba, która przeczyta tylko streszczenie, "
                "powinna dowiedzieć się, czego dotyczy cała grupa, w jej własnym "
                "języku, bez potrzeby czytania żadnego pojedynczego fragmentu."
            ),
            user=(
                "Fragmenty:\n${passages}\n\n"
                "Napisz jedno streszczenie obejmujące to, co łączy powyższe fragmenty. "
                "Odpowiedz samym streszczeniem, nic więcej."
            ),
        ),
    }
