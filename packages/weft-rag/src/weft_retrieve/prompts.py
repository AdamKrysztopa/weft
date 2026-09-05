"""The prompts `weft-retrieve`'s own plugins ask. The first registered `Prompt` in this tree.

Task **2.7**, extended by tasks **2.15**, **2.16** and **2.17**. `docs/build-ledger.md`'s 2.10 line
settles where a prompt lives: "`weft-prompts` declares no `weft.packs` entry point and
registers nothing … every first-party prompt belongs to the plugin that asks it a question
(2.9, 2.7, 2.16, 2.17)." So the wording `llm-rerank` sends a model is *this* pack's,
registered under `weft_prompts.contract.Prompt` through the same public entry point a third
party's prompt pack uses, and replaceable the same way: an operator who wants different
wording pins a different name in the reranker's `with:` block, or pins their own class over
this name in `[plugins]`. Neither is an edit to this file.

**Why the offered passages arrive as one pre-rendered string.** `weft_prompts.template`
renders `${name}` over `string.Template`, so a field is substituted as its own text and a
template cannot iterate. Numbering and joining the candidates is therefore the *plugin's*
work, not the prompt's — which is the right split anyway: how many passages a reranker offers
and how it truncates them is `llm-rerank`'s configuration, while what the model is asked about
them is a translatable string. `weft_retrieve.rerank._offer` is the one place that numbering
is written, and the same numbers are what the answer is read back against.

**No sample answer in the template.** The shape of the reply is `PassageRelevance`'s JSON
schema, and `weft_prompts.cascade` is what puts it in front of a model — tier 1 as the
vendor's own schema parameter, tier 2 as a schema instruction, tier 3 by rescuing JSON out of
prose. A hand-written example here would be a fourth copy of that shape, drifting from the
model it claims to describe the first time a field is renamed.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under, and `llm-rerank`'s default.
PASSAGE_RELEVANCE_NAME = "passage-relevance"


class PassageRelevanceRequest(BaseModel):
    """What `passage-relevance` renders: the question as asked, and the numbered candidates.

    `question` is `Ranking.origin.text` — the user's own words, never a derived query.
    `QuerySet.origin`'s own docstring records the reference defect that makes this load-bearing:
    its HyDE fed a hallucinated passage to the cross-encoder *as the query*, so the reranker
    scored candidates against a document the model invented. A reranker that reads `origin`
    and nothing else is structurally unable to repeat that, and the type is where it is held.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    passages: str


class PassageJudgement(BaseModel):
    """One passage's relevance to the question, by the index it was offered under.

    `relevance` is bounded rather than free: a model that answers `7` on an implied ten-point
    scale would otherwise sort above everything and be indistinguishable from a confident
    `0.7`. Out of range is a validation failure the cascade steps down through and finally
    reports, which is what makes the bound worth declaring rather than clamping.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    relevance: float = Field(ge=0.0, le=1.0)


class PassageRelevance(BaseModel):
    """Every offered passage, judged once. `llm-rerank` refuses a set that is not exactly that.

    A tuple rather than a mapping keyed by index, because a JSON object with numeric keys is
    the shape models are worst at and because the duplicate a list can carry is a fact worth
    seeing: `llm-rerank` names a repeated index in its refusal instead of silently keeping the
    last one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    judgements: tuple[PassageJudgement, ...] = ()


class PassageRelevancePrompt(TypedPrompt):
    """Ask a model how much each offered passage helps answer the question.

    The English text is the fallback every locale degrades to; the Polish one exists because
    the corpus this engine is measured against has a Polish subset (`09` §4), and a reranker
    that judges Polish passages through an English instruction is the quiet quality loss
    locale-keyed prompts exist to prevent. A locale nobody translated degrades the *language*,
    which a reader can see, never the answer, which they cannot — `TypedPrompt`'s own rule.
    """

    name: ClassVar[str] = PASSAGE_RELEVANCE_NAME
    input_model: ClassVar[type[BaseModel]] = PassageRelevanceRequest
    output_model: ClassVar[type[BaseModel] | None] = PassageRelevance
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You judge how much each retrieved passage helps answer a question. "
                "You judge only what is in front of you: a passage that is on the same "
                "topic but does not help answer the question is not relevant."
            ),
            user=(
                "Question: ${question}\n\n"
                "Passages:\n${passages}\n\n"
                "Judge every passage exactly once, using the index shown in brackets. "
                "Give each one a relevance between 0.0 (does not help at all) and 1.0 "
                "(answers the question directly)."
            ),
        ),
        "pl": PromptText(
            system=(
                "Oceniasz, na ile każdy odnaleziony fragment pomaga odpowiedzieć na pytanie. "
                "Oceniasz wyłącznie to, co masz przed sobą: fragment dotyczący tego samego "
                "tematu, który nie pomaga odpowiedzieć na pytanie, nie jest istotny."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Fragmenty:\n${passages}\n\n"
                "Oceń każdy fragment dokładnie raz, używając indeksu podanego w nawiasach "
                "kwadratowych. Przypisz każdemu istotność od 0.0 (zupełnie nie pomaga) do "
                "1.0 (odpowiada na pytanie wprost)."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.transforms.ContextualQueryRewriteConfig.prompt`'s default.
STANDALONE_QUESTION_NAME = "standalone-question"


class StandaloneQuestionRequest(BaseModel):
    """What `standalone-question` renders: the follow-up as asked, and the history it depends on.

    `question` is `QuerySet.origin.text` — the user's own words. `history` is already text by
    the time it arrives here: a `${name}` template cannot iterate a tuple of `Turn`s, so
    turning history into one string is `weft_retrieve.transforms._render_history`'s work, the
    same split `passage-relevance` makes for its own numbered candidates.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    history: str


class StandaloneQuestion(BaseModel):
    """The follow-up, rewritten to need no earlier turn. What `contextual-query-rewrite` derives
    its new `Query` from — `text` refuses empty the same way `Query.text` itself does, so a
    cascade tier that answered with nothing steps down rather than handing this plugin a blank
    rewrite to build a `Query` from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)


class StandaloneQuestionPrompt(TypedPrompt):
    """Ask a model to rewrite a follow-up question so it stands on its own.

    The instruction is explicit that the model never answers the question and never adds a
    fact the conversation did not already state — a rewrite that resolves "what about him?"
    into a claim about who "he" is would be putting an answer in the query, which is exactly
    the kind of invention `QuerySet.origin`'s own docstring exists to keep out of what a
    reranker or a generator is later asked to trust.
    """

    name: ClassVar[str] = STANDALONE_QUESTION_NAME
    input_model: ClassVar[type[BaseModel]] = StandaloneQuestionRequest
    output_model: ClassVar[type[BaseModel] | None] = StandaloneQuestion
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You rewrite a follow-up question into a standalone question. You never "
                "answer it, and you never add a fact the conversation does not already state."
            ),
            user=(
                "Conversation so far:\n${history}\n\n"
                "Follow-up question: ${question}\n\n"
                "Rewrite the follow-up question as a standalone question that keeps its "
                "meaning but needs none of the conversation above to understand it — resolve "
                "every pronoun and implicit reference against the history above. Answer with "
                "the rewritten question and nothing else."
            ),
        ),
        "pl": PromptText(
            system=(
                "Przekształcasz pytanie uzupełniające w pytanie samodzielne. Nigdy na nie nie "
                "odpowiadasz i nigdy nie dodajesz faktu, którego nie ma w rozmowie."
            ),
            user=(
                "Dotychczasowa rozmowa:\n${history}\n\n"
                "Pytanie uzupełniające: ${question}\n\n"
                "Przekształć pytanie uzupełniające w pytanie samodzielne, które zachowuje jego "
                "znaczenie, ale nie wymaga powyższej rozmowy do zrozumienia — rozwiąż każdy "
                "zaimek i domyślne odniesienie na podstawie powyższej historii. Odpowiedz "
                "wyłącznie przekształconym pytaniem."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.transforms.HydeConfig.prompt`'s default.
HYDE_DOCUMENT_NAME = "hyde-document"


class HydeDocumentRequest(BaseModel):
    """What `hyde-document` renders: the question as asked, and how many documents to write.

    `question` is `QuerySet.origin.text` — the user's own words, per `hyde`'s own obligation
    (task 2.16's ledger line, and 2.4's before it) to build every derived `Query` off
    `payload.origin`, never off whatever an earlier transform in the same document already
    produced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    #: `HydeConfig.samples`, rendered as text. `weft_prompts.template.render_template`
    #: substitutes `str(value)` for whatever a field holds, so an `int` here renders exactly
    #: as the operator's own number — never a word hard-coded in this file.
    samples: int


class HydeDocuments(BaseModel):
    """One or more hypothetical passages, each one answering the question directly.

    A flat tuple of strings, unlike `PassageRelevance`'s array of objects: every entry here
    is one fact (a passage's text), where a `PassageJudgement` needed two fields (an index
    and a score) to be addressable at all. `min_length=1` is what stops a cascade tier that
    answered with an empty array from validating — `hyde` would then have nothing to derive
    a `Query` from, and `QuerySet.queries` itself refuses empty.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    documents: tuple[str, ...] = Field(min_length=1)

    @field_validator("documents", mode="after")
    @classmethod
    def _no_blank_document(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """A blank passage is not a hypothetical document.

        Caught here rather than at `Query` construction one call later: `Query.text` itself
        refuses empty text, but the error there would name a field on a type this prompt's
        own caller did not build, not the model answer that actually produced the problem.
        """
        if any(not document.strip() for document in value):
            raise ValueError(
                "every entry hyde-document answers with must be a non-blank hypothetical "
                "passage; a blank one cannot become a Query, which refuses empty text."
            )
        return value


class HydeDocumentPrompt(TypedPrompt):
    """Ask a model to write one or more passages that would answer the question directly, as
    if drawn from the source material — the "hypothetical document" `hyde` retrieves against
    instead of the question itself. Luyu Gao, Xueguang Ma, Jimmy Lin, Jamie Callan, *Precise
    Zero-Shot Dense Retrieval without Relevance Labels*, arXiv:2212.10496 (2022), ACL 2023
    pp. 1762-1777 — the technique this prompt exists to ask for, cited here rather than
    restated on `weft_retrieve.transforms.Hyde`, which cites it again for what it does with
    the answer.

    The instruction is explicit that the model must not hedge: a passage that reads "I do
    not have specific information, but generally speaking…" is a worse dense-retrieval probe
    than a confident, possibly wrong, one — HyDE's premise is that a hypothetical answer
    passage sits nearer the *real* answer passage in embedding space than the bare question
    does, and hedging text does not resemble either.
    """

    name: ClassVar[str] = HYDE_DOCUMENT_NAME
    input_model: ClassVar[type[BaseModel]] = HydeDocumentRequest
    output_model: ClassVar[type[BaseModel] | None] = HydeDocuments
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You write short passages that could appear in a source document and would "
                "directly and confidently answer the question below. You never hedge, never "
                "say what you do not know, and never mention that the passage is hypothetical."
            ),
            user=(
                "Question: ${question}\n\n"
                "Write ${samples} different short passages (two to four sentences each), "
                "every one directly and confidently answering the question as if it were "
                "found in the source material. Vary the wording and the angle across "
                "passages rather than repeating one sentence with synonyms."
            ),
        ),
        "pl": PromptText(
            system=(
                "Piszesz krótkie fragmenty, które mogłyby pochodzić z dokumentu źródłowego i "
                "bezpośrednio, pewnie odpowiadają na poniższe pytanie. Nigdy nie zastrzegasz, "
                "nigdy nie piszesz, czego nie wiesz, i nigdy nie wspominasz, że fragment jest "
                "hipotetyczny."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Napisz ${samples} różnych krótkich fragmentów (od dwóch do czterech zdań "
                "każdy), z których każdy bezpośrednio i pewnie odpowiada na pytanie, tak jakby "
                "pochodził z materiału źródłowego. Różnicuj sformułowania i ujęcie tematu "
                "między fragmentami, zamiast powtarzać jedno zdanie innymi słowami."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.transforms.StepBackConfig.prompt`'s default.
#:
#: **Not `"step-back"`.** `.phase2-design.md` §10's own row for task 2.17 writes the config
#: default as the literal string `"step-back"`, which is also `weft_retrieve.transforms.
#: STEP_BACK_NAME` — the `QueryTransform` plugin's own registered name. `.phase2-design.md`
#: §5's own derived rule, "no plugin name may be registered under two Phase 2 contracts",
#: makes that collision real rather than cosmetic: `weft_cli.compile._contract_for` infers a
#: pipeline stage's contract by asking *every* registered contract which one answers to a
#: bare `use:` name, `Prompt` included, so a document naming `use: step-back` for the
#: transform would raise `AmbiguousStageContractError` the moment this prompt shared its
#: name. `hyde` already drew this line once (`hyde` the transform, `hyde-document` the
#: prompt); this constant draws it the same way rather than reproducing the table's literal
#: string and breaking the rule it sits three sections below.
STEP_BACK_QUESTION_NAME = "step-back-question"


class StepBackRequest(BaseModel):
    """What `step-back-question` renders: the question exactly as the user asked it.

    `question` is `QuerySet.origin.text`, never a query an earlier transform already
    derived — the same obligation `HydeDocumentRequest.question` and
    `StandaloneQuestionRequest.question` carry, for the same stated reason: a transform
    that abstracts an already-abstracted query compounds drift nobody asked for.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str


class StepBackQuestion(BaseModel):
    """The abstracted, more general question `step-back` derives its second `Query` from.

    `text` refuses empty the same way `StandaloneQuestion.text` and `Query.text` do, so a
    cascade tier that answered with nothing steps down rather than handing this plugin a
    blank abstraction to build a `Query` from.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)


class StepBackPrompt(TypedPrompt):
    """Ask a model to abstract a question into a more general one the same fact would answer.

    Huaixiu Steven Zheng, Swaroop Mishra, Xinyun Chen, Heng-Tze Cheng, Ed H. Chi, Quoc V. Le,
    Denny Zhou, *Take a Step Back: Evoking Reasoning via Abstraction in Large Language
    Models*, ICLR 2024 (poster; OpenReview forum `3bq3jsvcQ1`), arXiv:2310.06117 — the paper
    `weft_retrieve.transforms.StepBack` is named after and cited again there for what it does
    with the answer.

    The instruction asks for a *broader* question in the same topic, not a rephrasing and
    not an answer: "what year was the Eiffel Tower built?" steps back to "what is the
    history of the Eiffel Tower?", never to a restatement of the original question's own
    words, which would make the second `Query` redundant with the first rather than a
    genuinely different retrieval probe.
    """

    name: ClassVar[str] = STEP_BACK_QUESTION_NAME
    input_model: ClassVar[type[BaseModel]] = StepBackRequest
    output_model: ClassVar[type[BaseModel] | None] = StepBackQuestion
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You take a step back from a specific question and ask a more general "
                "question about the same underlying topic — a broader question whose "
                "answer would help answer the original one. You never answer the "
                "question, and you never simply reword it."
            ),
            user=(
                "Question: ${question}\n\n"
                "Write one more general, higher-level question about the same underlying "
                "topic or concept — a step back from the specific question above, not a "
                "rephrasing of it and not an answer to it. Answer with the step-back "
                "question and nothing else."
            ),
        ),
        "pl": PromptText(
            system=(
                "Cofasz się o krok od szczegółowego pytania i zadajesz bardziej ogólne "
                "pytanie na ten sam temat — szersze pytanie, którego odpowiedź pomogłaby "
                "odpowiedzieć na pytanie oryginalne. Nigdy nie odpowiadasz na pytanie i "
                "nigdy go po prostu nie przeformułowujesz."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Napisz jedno bardziej ogólne pytanie wyższego poziomu na ten sam temat lub "
                "pojęcie — krok w tył od szczegółowego pytania powyżej, a nie jego "
                "przeformułowanie ani odpowiedź na nie. Odpowiedz wyłącznie pytaniem "
                "cofniętym o krok."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.transforms.MultiQueryConfig.prompt`'s default. Not `"multi-query"`, for the
#: same collision reason `STEP_BACK_QUESTION_NAME` is not `"step-back"` — see that constant's
#: own docstring. `multi-query` (the `QueryTransform`) already claims the shorter name.
MULTI_QUERY_VARIANTS_NAME = "multi-query-variants"


class MultiQueryVariantsRequest(BaseModel):
    """What `multi-query-variants` renders: one or more seed questions, numbered, and how many
    alternatives to write for each.

    `questions` arrives pre-rendered for the same reason `passage-relevance`'s `passages` and
    `standalone-question`'s `history` do: `string.Template` cannot iterate, so numbering and
    joining the seeds is `weft_retrieve.transforms._offer_seeds`'s work, and the same numbers
    are what the answer is read back against in `weft_retrieve.transforms._groups_by_index`.
    `expansion` is a full instruction clause, not the bare `ExpansionKind` value — `PARAPHRASE`,
    `ASPECT` and `TERM` are this pack's own vocabulary, not words a model has been told what to
    do with, so `weft_retrieve.transforms._EXPANSION_INSTRUCTIONS` renders the clause the
    plugin actually wants asked.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    questions: str
    variants: int
    expansion: str


class SeedVariants(BaseModel):
    """One seed question's alternatives, by the index it was offered under.

    Mirrors `PassageJudgement`'s own shape for the identical reason: a JSON object keyed by a
    numeric index is the shape models answer worst, so the index travels *inside* each entry
    of a list instead.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    variants: tuple[str, ...] = Field(min_length=1)

    @field_validator("variants", mode="after")
    @classmethod
    def _no_blank_variant(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """A blank alternative is not a search query — the same refusal `HydeDocuments`
        makes for a blank hypothetical passage, and for the identical reason: caught here,
        against the model answer that actually produced it, rather than one call later
        against a `Query.text` that refuses empty for a different-sounding reason."""
        if any(not variant.strip() for variant in value):
            raise ValueError(
                "every alternative multi-query-variants answers with must be a non-blank "
                "search query; a blank one cannot become a Query, which refuses empty text."
            )
        return value


class MultiQueryVariants(BaseModel):
    """Every offered seed's alternatives, answered once each. `multi-query` refuses a set that
    is not exactly that — see `weft_retrieve.transforms._groups_by_index`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: tuple[SeedVariants, ...] = ()


class MultiQueryVariantsPrompt(TypedPrompt):
    """Ask a model to fan one or more questions out into several alternative search queries.

    Nicholas J. Belkin, Paul Kantor, Edward A. Fox, Joseph A. Shaw, *Combining the evidence of
    multiple query representations for information retrieval*, Information Processing &
    Management 31(3), pp. 431-448, 1995 — multiple representations of one question retrieve
    better together than any one alone, the idea `weft_retrieve.transforms.MultiQuery` is named
    after. George W. Furnas, Thomas K. Landauer, Louis M. Gomez, Susan T. Dumais, *The
    vocabulary problem in human-system communication*, CACM 30(11), pp. 964-971, 1987 — the
    problem this instruction is written against: a corpus rarely uses the asker's own words,
    which is why the instruction below asks for different *vocabulary*, not only different
    phrasing. Rolf Jagerman, Honglei Zhuang, Zhen Qin, Xuanhui Wang, Michael Bendersky, *Query
    Expansion by Prompting Large Language Models*, arXiv:2305.03653, 2023 — generating the
    alternatives through a model call is this paper's mechanism, cited again on `MultiQuery`
    for what it does with the answer.

    The instruction is explicit that an answer is a *searchable query*, never a restatement of
    the model's own opinion or an answer to the question — `10` §1.1's own row on this
    technique names the reference's narrower prompt directly: it asked only for paraphrases,
    "forbidding the two things the expansion literature credits" (new vocabulary, and a
    different facet of the question). `weft_retrieve.transforms.ExpansionKind` is where those
    two are named as configuration instead of left unreachable.
    """

    name: ClassVar[str] = MULTI_QUERY_VARIANTS_NAME
    input_model: ClassVar[type[BaseModel]] = MultiQueryVariantsRequest
    output_model: ClassVar[type[BaseModel] | None] = MultiQueryVariants
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You expand one or more questions into alternative search queries that would "
                "help retrieve the same information from different angles. You never answer "
                "any question, and every alternative you write is itself a searchable query, "
                "never a restatement of your own opinion or an answer."
            ),
            user=(
                "Questions:\n${questions}\n\n"
                "For every question above, write ${variants} alternative search queries — "
                "${expansion}. Answer once per question, using the same index shown in "
                "brackets, and do not skip an index or answer for one that was not offered."
            ),
        ),
        "pl": PromptText(
            system=(
                "Rozwijasz jedno lub więcej pytań w alternatywne zapytania wyszukiwania, które "
                "pomogłyby odnaleźć tę samą informację z różnych stron. Nigdy nie odpowiadasz "
                "na żadne pytanie, a każda alternatywa, którą piszesz, jest sama w sobie "
                "zapytaniem do wyszukiwarki, nigdy powtórzeniem własnej opinii ani odpowiedzią."
            ),
            user=(
                "Pytania:\n${questions}\n\n"
                "Dla każdego pytania powyżej napisz ${variants} alternatywnych zapytań "
                "wyszukiwania — ${expansion}. Odpowiedz raz na każde pytanie, używając tego "
                "samego indeksu podanego w nawiasach kwadratowych, i nie pomijaj żadnego "
                "indeksu ani nie odpowiadaj na taki, którego nie podano."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.graded.GradedRetrievalConfig.prompt`'s default.
RELEVANCE_GRADE_NAME = "relevance-grade"


class Grade(StrEnum):
    """How well one retrieved passage supports answering a question — `graded-retrieval`'s
    own three-way judgement per hit.

    Corrected from CRAG's own Correct/Incorrect/Ambiguous (Shi-Qi Yan, Jia-Chen Gu, Yun Zhu,
    Zhen-Hua Ling, *Corrective Retrieval Augmented Generation*, arXiv:2401.15884, 2024, §3.1's
    retrieval evaluator) into the vocabulary `passage-relevance` already uses in this pack —
    "relevant" reads the same way whether a caller is looking at a continuous score from
    `llm-rerank` or a discrete grade from here, rather than asking an operator to learn two
    words for the same axis. `weft_retrieve.graded`'s own module docstring is where the paper
    is cited again for what a caller does with the answer, and for the naming condition
    (`10` §1.1) that keeps a plugin grading alone from claiming `corrective`.

    **Three grades, because a threshold on a raw float is a tuning constant.** `llm-rerank`
    sorts by a continuous `relevance`; a *filter*, by contrast, needs a line drawn somewhere,
    and a bare `keep_above: float` would be `10` §2.1's tuning constant with no measurement
    behind it — a named grade an operator can require "at least relevant" against reads as a
    decision, not a magic number.

    **Ordered, and the order lives in `GRADE_ORDER` below, not in `StrEnum`'s own comparison.**
    A `StrEnum` member compares as the `str` it wraps, so `Grade.IRRELEVANT < Grade.RELEVANT`
    would silently mean "the string 'irrelevant' sorts before 'relevant'" — true here only by
    coincidence of spelling, and a trap for whichever member is added next.
    `weft_retrieve.graded` reads `GRADE_ORDER`, never `<`.
    """

    IRRELEVANT = "irrelevant"
    AMBIGUOUS = "ambiguous"
    RELEVANT = "relevant"


#: `Grade`'s own order, worst to best — the one place it is written. See `Grade`'s docstring.
GRADE_ORDER: tuple[Grade, ...] = (Grade.IRRELEVANT, Grade.AMBIGUOUS, Grade.RELEVANT)


class PassageGradeRequest(BaseModel):
    """What `relevance-grade` renders: the question, and one batch of numbered candidates.

    A request type of its own rather than a reuse of `PassageRelevanceRequest`, even though
    the two fields are named alike: the two prompts ask for different shapes of answer — a
    continuous score there, a three-way grade here — and `weft_prompts.template`'s
    two-direction validator checks a `TypedPrompt`'s own `input_model` against its own
    template, never against a sibling's.

    `passages` is one *batch*, not every hit `graded-retrieval` was handed — batching is
    `weft_retrieve.graded._offer`'s work, the same split `passage-relevance`'s own docstring
    draws between "how many passages a reranker offers" and "what the model is asked about
    them".
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    passages: str


class PassageGrade(BaseModel):
    """One passage's grade, by the index it was offered under — mirrors `PassageJudgement`,
    the discrete axis's counterpart to the continuous one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    grade: Grade


class GradedPassages(BaseModel):
    """Every offered passage, graded once. `graded-retrieval` refuses a batch that is not
    exactly that — the same refusal `PassageRelevance`'s own docstring states for a
    continuous score, applied to a discrete grade.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    grades: tuple[PassageGrade, ...] = ()


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.boolean.BooleanRetrievalConfig.prompt`'s default.
BOOLEAN_PARSE_NAME = "boolean-parse"


class BooleanTokenKind(StrEnum):
    """What one token of a tokenised Boolean query names — a search term, a combinator
    keyword, or a parenthesis. `weft_retrieve.boolean`'s own recursive-descent parser is
    what turns a sequence of these into a precedence-respecting `BoolExpr`; this prompt's
    only job is lexical — deciding where one token ends and the next begins — never deciding
    what the tokens mean together. Splitting the two is the fix for the reference's flat
    `(operator, list[str])`: a *tokeniser* cannot silently collapse `a AND b OR c` into
    `MIXED`, because it never sees the operators as a single "type of query" to begin with.
    """

    TERM = "term"
    AND = "and"
    OR = "or"
    NOT = "not"
    LPAREN = "lparen"
    RPAREN = "rparen"


class BooleanQueryRequest(BaseModel):
    """What `boolean-parse` renders: the query to tokenise, and which operator keywords this
    document's own `operators` config allows.

    `operators` is rendered text (`AND, OR, NOT`, upper-cased), never the bare `BoolOp`
    members — the same split every other request type in this module draws between "what a
    plugin computed" and "what a template can substitute": `string.Template` cannot iterate
    a tuple, so `weft_retrieve.boolean.BooleanRetrieval.run` renders it once, the same way
    `_render_history` and `_offer_seeds` render theirs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    operators: str


class BooleanToken(BaseModel):
    """One token: a search term's own text, or a bare combinator/parenthesis with none.

    `text` is checked against `kind` rather than left to mean whatever the model happened to
    fill in: a `TERM` with a blank `text` cannot become a `Query` (`Query.text` itself
    refuses empty), and a combinator carrying text nobody asked for is the model answering a
    question this prompt did not pose.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: BooleanTokenKind
    text: str = ""

    @model_validator(mode="after")
    def _text_matches_kind(self) -> "BooleanToken":
        if self.kind is BooleanTokenKind.TERM:
            if not self.text.strip():
                raise ValueError("a 'term' token must carry non-blank text")
        elif self.text:
            raise ValueError(f"a '{self.kind.value}' token carries no text, and this one does")
        return self


class BooleanTokens(BaseModel):
    """The whole query, tokenised in order. `weft_retrieve.boolean.parse_tokens` is what
    turns this into a `BoolExpr` — precedence, parentheses and the shape of the AST are all
    that function's work, never this prompt's or this model's.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tokens: tuple[BooleanToken, ...] = Field(min_length=1)


class BooleanParsePrompt(TypedPrompt):
    """Ask a model to tokenise a Boolean query into terms, combinators and parentheses, in
    the order they appear — never to decide how they combine.

    Christopher D. Manning, Prabhakar Raghavan, Hinrich Schütze, *Introduction to Information
    Retrieval*, Ch. 1 "Boolean retrieval", Cambridge University Press, 2008 — the technique
    `weft_retrieve.boolean.BooleanRetrieval` is named after; no origin paper is claimed
    because operational Boolean systems predate any single citable one (`10` §1.1's own row).
    Chaitanya Malaviya, Peter Shaw, Ming-Wei Chang, Kenton Lee, Kristina Toutanova, *QUEST*,
    ACL 2023, arXiv:2305.11694 — a model reading a query and producing the pieces of a
    Boolean decomposition, the mechanism this prompt asks for; the decomposition into a real
    *precedence-respecting tree*, rather than a flat operator-plus-term-list, is
    `weft_retrieve.boolean.parse_tokens`'s own work, not asked of the model here.

    The instruction is explicit that the model's job stops at lexical splitting: a query
    already written with explicit `AND`/`OR`/`NOT`/parentheses is tokenised almost
    mechanically, and a query written in plain language is read for the terms and the
    Boolean relationship the asker meant, without inventing an operator none of the
    configured `${operators}` names.
    """

    name: ClassVar[str] = BOOLEAN_PARSE_NAME
    input_model: ClassVar[type[BaseModel]] = BooleanQueryRequest
    output_model: ClassVar[type[BaseModel] | None] = BooleanTokens
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You tokenise a Boolean query into an ordered sequence of terms, "
                "combinators and parentheses. You never decide how the pieces combine — "
                "that is somebody else's job — you only split the query into its parts, "
                "in the order they appear."
            ),
            user=(
                "Query: ${question}\n\n"
                "Supported combinator keywords: ${operators}\n\n"
                "Split this query into tokens, in order: every search term as one 'term' "
                "token (its own words as text), every combinator keyword as its own token "
                "with no text, and every literal parenthesis as its own token with no text. "
                "Use only the supported combinator keywords above — never invent one that "
                "is not listed."
            ),
        ),
        "pl": PromptText(
            system=(
                "Dzielisz zapytanie logiczne na uporządkowaną sekwencję terminów, "
                "spójników i nawiasów. Nigdy nie decydujesz, jak te elementy się łączą — to "
                "zadanie kogoś innego — dzielisz zapytanie wyłącznie na jego części, w "
                "kolejności występowania."
            ),
            user=(
                "Zapytanie: ${question}\n\n"
                "Obsługiwane słowa kluczowe spójników: ${operators}\n\n"
                "Podziel to zapytanie na tokeny, w kolejności: każdy termin wyszukiwania "
                "jako osobny token 'term' (jego własne słowa jako tekst), każde słowo "
                "kluczowe spójnika jako osobny token bez tekstu, każdy dosłowny nawias jako "
                "osobny token bez tekstu. Używaj wyłącznie obsługiwanych słów kluczowych "
                "powyżej — nigdy nie wymyślaj własnego."
            ),
        ),
    }


class RelevanceGradePrompt(TypedPrompt):
    """Ask a model to grade each offered passage's support for the question, three ways.

    Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling, *Corrective Retrieval Augmented
    Generation*, arXiv:2401.15884, 2024 — §3.1's retrieval evaluator, the per-document
    judgement this prompt exists to ask for. `weft_retrieve.graded`'s own module docstring
    cites the paper again for what it does with the answer, and states the naming condition
    (`10` §1.1) that this prompt's own plugin does not, on its own, earn the name `corrective`.

    The instruction asks for exactly the paper's own three-way distinction — support, no
    support, and cannot tell — rather than collapsing "on topic but does not answer" into
    either of the other two, which is the distinction a plain relevant/irrelevant grade would
    lose and `Grade.AMBIGUOUS` exists to keep.
    """

    name: ClassVar[str] = RELEVANCE_GRADE_NAME
    input_model: ClassVar[type[BaseModel]] = PassageGradeRequest
    output_model: ClassVar[type[BaseModel] | None] = GradedPassages
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You grade how well each retrieved passage supports answering a question. "
                "Grade a passage 'relevant' only if it would actually help answer the "
                "question, 'irrelevant' if it would not help at all, and 'ambiguous' if it "
                "is on the same topic but you cannot tell whether it actually answers the "
                "question."
            ),
            user=(
                "Question: ${question}\n\n"
                "Passages:\n${passages}\n\n"
                "Grade every passage exactly once, using the index shown in brackets, as "
                "one of: relevant, ambiguous, irrelevant."
            ),
        ),
        "pl": PromptText(
            system=(
                "Oceniasz, na ile każdy odnaleziony fragment wspiera odpowiedź na pytanie. "
                "Oceń fragment jako 'relevant' tylko wtedy, gdy rzeczywiście pomaga "
                "odpowiedzieć na pytanie, jako 'irrelevant', gdy wcale nie pomaga, oraz jako "
                "'ambiguous', gdy dotyczy tego samego tematu, ale nie da się ocenić, czy "
                "faktycznie odpowiada na pytanie."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Fragmenty:\n${passages}\n\n"
                "Oceń każdy fragment dokładnie raz, używając indeksu podanego w nawiasach "
                "kwadratowych, jako jeden z: relevant, ambiguous, irrelevant."
            ),
        ),
    }


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.sufficiency.LlmSufficiencyConfig.prompt`'s default.
SUFFICIENCY_CHECK_NAME = "sufficiency-check"


class SufficiencyCheckRequest(BaseModel):
    """What `sufficiency-check` renders: the question, the evidence gathered so far, and —
    when there is one — a draft answer built from it.

    One request type serves both of `weft_retrieve.contract.Sufficiency`'s consumers — that
    contract's own docstring: "a named contract with two implementations is what 'replaceable'
    means here." `iterative-retrieval` (ledger 2.20) asks whether the *evidence* suffices,
    nothing drafted yet; `refine-on-uncertainty` (ledger 2.24) asks whether a *draft* built
    from that evidence is itself confident and grounded. `draft` is the empty string in the
    first case, never `None` — `string.Template` cannot substitute a `None`, so the plugin
    that renders this (`weft_retrieve.sufficiency.LlmSufficiency`) is what turns the
    contract's own `str | None` into text, and the template says plainly what an absent draft
    means rather than leaving a blank line for a model to guess at.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    evidence: str
    draft: str


class SufficiencyJudgement(BaseModel):
    """Whether the evidence — and the draft, when one was offered — is enough. Read straight
    into `weft_retrieve.payload.Assessment` by the plugin that asks this prompt; the two
    types stay separate because `Assessment.observed` is a fact about whether the *call
    itself* landed, which this prompt has no way to report about its own failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sufficient: bool
    confidence: float = Field(ge=0.0, le=1.0)
    missing: tuple[str, ...] = ()


#: The name this prompt is registered and selectable under — see `weft_retrieve.register` and
#: `weft_retrieve.routing.QueryScorerConfig.prompt`'s default.
ROUTE_QUERY_NAME = "route-query"


class RouteQueryRequest(BaseModel):
    """What `route-query` renders: the question, the dimensions to score it on, and the
    pipelines a router could currently choose between.

    `dimensions` and `candidates` arrive pre-rendered for the same reason every other
    request type in this module does — `string.Template` cannot iterate, so numbering and
    joining is the plugin's own work (`weft_retrieve.routing._offer_dimensions` and
    `_offer_candidates`). Showing the model what is actually installed, rather than a fixed
    prose description of "simple" and "complex" pipelines, is what keeps this prompt from
    writing a pipeline name into its own text: `weft_retrieve.routing`'s own module
    docstring is where the reason for reading the catalogue at all — rather than leaving
    that to the policy half of the router — is argued in full.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    dimensions: str
    candidates: str


class DimensionScore(BaseModel):
    """One dimension's score, by the name it was asked under.

    A named field rather than a positional index, unlike `PassageJudgement`'s: a
    `QueryScorer`'s dimensions are `weft_retrieve.routing.Dimension`s an operator's own
    `with:` block can add to, drop or rename, so there is no fixed position for an index to
    mean the same thing from one deployment to the next the way an offered passage's rank
    does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)


class RouteQueryScores(BaseModel):
    """Every asked dimension, scored once. `weft_retrieve.routing.QueryScorer` refuses a
    set that is not exactly the dimensions it asked for — see that module's own
    `_score_mapping`, the identical refusal `PassageRelevance`'s own docstring states for a
    reranker's judgement set, applied to a name instead of an index.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    scores: tuple[DimensionScore, ...] = ()


class RouteQueryPrompt(TypedPrompt):
    """Ask a model to score a query along named dimensions, informed by the pipelines a
    router could actually choose between.

    Soyeong Jeong, Jinheon Baek, Sukmin Cho, Sung Ju Hwang, Jong C. Park, *Adaptive-RAG:
    Learning to Adapt Retrieval-Augmented Large Language Models through Question
    Complexity*, NAACL 2024, arXiv:2403.14403 — the route-by-query-complexity formulation
    `weft_retrieve.contract.QueryScorer` is named after. Alex Mallen, Akari Asai, Victor
    Zhong, Rajarshi Das, Daniel Khashabi, Hannaneh Hajishirzi, *When Not to Trust Language
    Models: Investigating Effectiveness of Parametric and Non-Parametric Memories*, ACL
    2023, arXiv:2212.10511 — the parametric-vs-retrieved distinction one of the seven
    default dimensions below measures. Yile Wang, Peng Li, Maosong Sun, Yang Liu,
    *Self-Knowledge Guided Retrieval Augmentation for Large Language Models*, Findings of
    EMNLP 2023, arXiv:2310.05002 — a model's own sense of what it does and does not already
    know, the same idea named differently.

    The instruction is explicit that scoring is not deciding: this prompt asks for a
    measurement on every named dimension and nothing else — `weft_retrieve.routing`'s own
    module docstring states why the two are two plugins rather than one.
    """

    name: ClassVar[str] = ROUTE_QUERY_NAME
    input_model: ClassVar[type[BaseModel]] = RouteQueryRequest
    output_model: ClassVar[type[BaseModel] | None] = RouteQueryScores
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You score a question along a fixed set of named dimensions, each from 0.0 "
                "to 1.0. You never decide what to do with a score — you only measure. You "
                "are shown the pipelines a router could choose between so your scores are "
                "grounded in what is actually available, not a routing decision you make "
                "yourself."
            ),
            user=(
                "Question: ${question}\n\n"
                "Dimensions to score:\n${dimensions}\n\n"
                "Pipelines a router could choose between:\n${candidates}\n\n"
                "Score the question on every dimension listed above, using its own name, "
                "each from 0.0 to 1.0. Score every dimension exactly once, and none that "
                "was not listed."
            ),
        ),
        "pl": PromptText(
            system=(
                "Oceniasz pytanie wzdłuż ustalonego zestawu nazwanych wymiarów, każdy od 0.0 "
                "do 1.0. Nigdy nie decydujesz, co zrobić z oceną — wyłącznie mierzysz. "
                "Pokazano ci potoki, spośród których router mógłby wybierać, aby twoje "
                "oceny były osadzone w tym, co faktycznie dostępne, a nie decyzją routingu, "
                "którą sam podejmujesz."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Wymiary do oceny:\n${dimensions}\n\n"
                "Potoki, spośród których router mógłby wybierać:\n${candidates}\n\n"
                "Oceń pytanie na każdym wymiarze wymienionym powyżej, używając jego własnej "
                "nazwy, każdy od 0.0 do 1.0. Oceń każdy wymiar dokładnie raz i żadnego, "
                "którego nie wymieniono."
            ),
        ),
    }


class SufficiencyCheckPrompt(TypedPrompt):
    """Ask a model whether the evidence in hand — and, when given, a draft grounded in it —
    is enough to confidently answer the question.

    Zhengbao Jiang, Frank F. Xu, Luyu Gao, Zhiqing Sun, Qian Liu, Jane Dwivedi-Yu, Yiming
    Yang, Jamie Callan, Graham Neubig, *Active Retrieval Augmented Generation*, EMNLP 2023,
    pp. 7969-7992, arXiv:2305.06983 — `10` §1.1's `refine-on-uncertainty` row names FLARE as
    "the nearest published ancestor, and the reference does not cite it". Cited here for the same
    reason, not as a claim this prompt implements FLARE's own mechanism: FLARE's signal is the
    drafting model's *token probability*, regenerated sentence by sentence; this prompt asks a
    model to judge a *whole* draft once, which is a different, coarser signal — see
    `weft_retrieve.sufficiency`'s module docstring for what this task actually ships instead.

    The instruction asks for exactly what `SufficiencyJudgement` can hold: a yes/no on
    sufficiency, a confidence in that judgement, and — only meaningful when the answer is
    no — which facts are still missing, never a rewritten question.
    """

    name: ClassVar[str] = SUFFICIENCY_CHECK_NAME
    input_model: ClassVar[type[BaseModel]] = SufficiencyCheckRequest
    output_model: ClassVar[type[BaseModel] | None] = SufficiencyJudgement
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You judge whether the evidence gathered so far is enough to confidently "
                "answer a question. When a draft answer is shown, you also judge whether "
                "the draft itself is well supported by that evidence, or whether it hedges, "
                "guesses, or leaves something unanswered. You never answer the question "
                "yourself — you only judge whether enough is in hand to do so."
            ),
            user=(
                "Question: ${question}\n\n"
                "Evidence gathered so far:\n${evidence}\n\n"
                "Draft answer (empty if none has been written yet): ${draft}\n\n"
                "Is this enough to confidently answer the question? If not, list the "
                "specific facts that are still missing."
            ),
        ),
        "pl": PromptText(
            system=(
                "Oceniasz, czy zebrane dotąd dowody wystarczą, aby pewnie odpowiedzieć na "
                "pytanie. Jeśli pokazano szkic odpowiedzi, oceniasz też, czy jest on dobrze "
                "poparty tymi dowodami, czy raczej zawiera niedopowiedzenia, domysły albo "
                "pomija coś istotnego. Nigdy sam nie odpowiadasz na pytanie — oceniasz "
                "wyłącznie, czy zebrano już wystarczająco dużo, by to zrobić."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Zebrane dotąd dowody:\n${evidence}\n\n"
                "Szkic odpowiedzi (puste, jeśli jeszcze go nie napisano): ${draft}\n\n"
                "Czy to wystarczy, aby pewnie odpowiedzieć na pytanie? Jeśli nie, wypisz "
                "konkretne fakty, których wciąż brakuje."
            ),
        ),
    }
