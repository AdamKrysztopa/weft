"""The six prompts `weft_eval.judges`' own metrics ask, and the structured shapes they answer in.

Task **4.2**. `docs/10-technique-catalogue.md` §1.3 names each judge's provenance already —
`faithfulness`, `context-recall`, `context-relevance`, `answer-relevance`, `answer-correctness`
Es et al. (arXiv:2309.15217, the RAGAS paper) or library; `answer-completeness` cites nothing,
because RAGAS has no completeness metric in the paper or in any version of the library, and
carrying its `ragas_` prefix into Weft would be a false provenance claim §2.1 rule 4 forbids.
None of that is repeated here — this module's job is the wording, not the citation.

**Every output model is a set of counts or judgements, never a score field.** This is the fix for
a recurring LLM-judge defect: a judge reading a ratio directly off a `score` field the model
itself divided, while the numerator and denominator sit unused beside it. None of the models
below has anywhere for a model to put a
ratio — `FaithfulnessJudgement.statements`, `ContextRecallJudgement.claims`,
`ContextRelevanceJudgement.relevant_indices` and `FactualClassification`'s three tuples are all
countable judgements over discrete items; `weft_eval.judges` is where every ratio the suite reports
is computed, in Weft's own code, from these counts. `AnswerRelevance`'s `GeneratedQuestions` and
`AnswerCompleteness`'s `CompletenessJudgement` are two more instances of the identical rule, not
carved out.

**English only.** `weft_prompts.typed_prompt.FALLBACK_LOCALE` is the one locale every prompt in
this tree must declare; a translation is additive work this task does not claim to have done.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from pydantic.config import JsonDict

from weft_prompts.contract import PROMPT_CONTRACT_VERSION
from weft_prompts.typed_prompt import PromptText, TypedPrompt


def _without_docstring(schema: JsonDict) -> None:
    schema.pop("description", None)


#: For a judge's output model: its docstring is for code readers and never reaches the judge,
#: whose prompt is the JSON schema `weft_prompts.cascade` builds from this model.
_JUDGE_OUTPUT_CONFIG = ConfigDict(frozen=True, extra="forbid", json_schema_extra=_without_docstring)

# ---------------------------------------------------------------------------------------------
# faithfulness
# ---------------------------------------------------------------------------------------------

FAITHFULNESS_PROMPT_NAME = "faithfulness-judge"


class FaithfulnessRequest(BaseModel):
    """The values the faithfulness judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str
    contexts: str


class StatementSupport(BaseModel):
    """One statement taken from the answer, and whether the context supports it.

    Attributes:
        statement: A short, standalone factual statement the answer makes.
        supported: Whether the retrieved context supports it.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    statement: str
    supported: bool


class FaithfulnessJudgement(BaseModel):
    """The faithfulness judge's answer: every statement in the answer, each judged.

    Attributes:
        statements: One entry per statement; `weft_eval.judges.Faithfulness` counts them.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    statements: tuple[StatementSupport, ...] = ()


class FaithfulnessJudgePrompt(TypedPrompt):
    """Decompose the answer into standalone claims, and judge each against the given context."""

    name: ClassVar[str] = FAITHFULNESS_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = FaithfulnessRequest
    output_model: ClassVar[type[BaseModel] | None] = FaithfulnessJudgement
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You check whether an answer is grounded in the context it was supposedly "
                "written from. Break the answer into short, standalone factual statements, "
                "then judge each one strictly on whether the context supports it — not "
                "whether it is true in general."
            ),
            user=(
                "Context:\n${contexts}\n\nAnswer:\n${answer}\n\n"
                "List every standalone statement the answer makes, and whether the context "
                "supports each one."
            ),
        ),
    }


# ---------------------------------------------------------------------------------------------
# context-recall
# ---------------------------------------------------------------------------------------------

CONTEXT_RECALL_PROMPT_NAME = "context-recall-judge"


class ContextRecallRequest(BaseModel):
    """The values the context-recall judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str
    contexts: str


class ClaimSupport(BaseModel):
    """One claim taken from the reference answer, and whether the retrieved context supports it.

    Attributes:
        claim: A standalone claim the reference answer makes.
        supported: Whether the retrieved context supports it.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    claim: str
    supported: bool


class ContextRecallJudgement(BaseModel):
    """The context-recall judge's answer: every claim in the reference, each judged.

    Attributes:
        claims: One entry per claim; `weft_eval.judges.ContextRecall` counts them.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    claims: tuple[ClaimSupport, ...] = ()


class ContextRecallJudgePrompt(TypedPrompt):
    """Decompose the reference answer into claims, and judge each against the retrieved context."""

    name: ClassVar[str] = CONTEXT_RECALL_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = ContextRecallRequest
    output_model: ClassVar[type[BaseModel] | None] = ContextRecallJudgement
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You check whether retrieved context contains what a correct answer needed. "
                "Break the reference answer into standalone claims, then judge each one on "
                "whether the retrieved context supports it."
            ),
            user=(
                "Retrieved context:\n${contexts}\n\nReference answer:\n${reference}\n\n"
                "List every standalone claim the reference answer makes, and whether the "
                "retrieved context supports each one."
            ),
        ),
    }


# ---------------------------------------------------------------------------------------------
# context-relevance
# ---------------------------------------------------------------------------------------------

CONTEXT_RELEVANCE_PROMPT_NAME = "context-relevance-judge"


class ContextRelevanceRequest(BaseModel):
    """The values the context-relevance judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    sentences: str


class ContextRelevanceJudgement(BaseModel):
    """The context-relevance judge's answer: which numbered sentences are relevant.

    Attributes:
        relevant_indices: The indices of the relevant sentences, as numbered in the prompt.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    relevant_indices: tuple[int, ...] = ()


class ContextRelevanceJudgePrompt(TypedPrompt):
    """Lets context relevance be judged per sentence, so on-topic filler does not count.

    Which numbered sentence, of the retrieved context's own sentences, helps answer the question.
    """

    name: ClassVar[str] = CONTEXT_RELEVANCE_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = ContextRelevanceRequest
    output_model: ClassVar[type[BaseModel] | None] = ContextRelevanceJudgement
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You judge which sentences of a retrieved passage are relevant to a "
                "question. A sentence is relevant only if it helps answer the question "
                "directly — being on the same topic is not enough."
            ),
            user=(
                "Question: ${question}\n\nNumbered sentences:\n${sentences}\n\n"
                "List the index of every sentence that is relevant to the question."
            ),
        ),
    }


# ---------------------------------------------------------------------------------------------
# answer-relevance
# ---------------------------------------------------------------------------------------------

ANSWER_RELEVANCE_PROMPT_NAME = "answer-relevance-judge"


class AnswerRelevanceRequest(BaseModel):
    """The values the answer-relevance judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    answer: str


class GeneratedQuestions(BaseModel):
    """The answer-relevance judge's answer: the questions the answer responds to.

    Attributes:
        questions: One to three questions, embedded and compared with the one asked.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    questions: tuple[str, ...] = ()


class AnswerRelevanceJudgePrompt(TypedPrompt):
    """Reverse-engineer the questions this answer would be a direct response to.

    No score is ever asked for — `weft_eval.judges.AnswerRelevance` measures how closely the
    generated questions match the one actually asked, by embedding similarity, entirely outside
    this prompt.
    """

    name: ClassVar[str] = ANSWER_RELEVANCE_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = AnswerRelevanceRequest
    output_model: ClassVar[type[BaseModel] | None] = GeneratedQuestions
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "Given an answer, generate the question(s) it most directly responds to. "
                "Write questions a reader with no other context would naturally ask, not a "
                "restatement of the answer's own words."
            ),
            user=("Answer:\n${answer}\n\nGenerate 1 to 3 questions this answer responds to."),
        ),
    }


# ---------------------------------------------------------------------------------------------
# answer-correctness
# ---------------------------------------------------------------------------------------------

ANSWER_CORRECTNESS_PROMPT_NAME = "answer-correctness-judge"


class AnswerCorrectnessRequest(BaseModel):
    """The values the answer-correctness judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    prediction: str
    reference: str


class FactualClassification(BaseModel):
    """A confusion-matrix term set over standalone factual statements, not a single score.

    `true_positives` — statements present in both `prediction` and `reference`. `false_positives`
    — statements `prediction` makes that `reference` does not support. `false_negatives` —
    statements `reference` makes that `prediction` omits. `weft_eval.judges.AnswerCorrectness`
    derives F1 from the three counts; nothing here computes a ratio.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    true_positives: tuple[str, ...] = ()
    false_positives: tuple[str, ...] = ()
    false_negatives: tuple[str, ...] = ()


class AnswerCorrectnessJudgePrompt(TypedPrompt):
    """Lets answer correctness be scored as an F1 over facts rather than one opaque grade.

    Classify the prediction's factual statements against the reference's, as a confusion matrix.
    """

    name: ClassVar[str] = ANSWER_CORRECTNESS_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = AnswerCorrectnessRequest
    output_model: ClassVar[type[BaseModel] | None] = FactualClassification
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You compare a predicted answer against a reference answer, statement by "
                "statement. Classify every standalone factual statement either answer makes "
                "into exactly one of: supported by both (true positive), only the predicted "
                "answer makes it (false positive), or only the reference makes it (false "
                "negative)."
            ),
            user=(
                "Question: ${question}\n\nPredicted answer:\n${prediction}\n\n"
                "Reference answer:\n${reference}\n\n"
                "Classify every standalone statement from either answer."
            ),
        ),
    }


# ---------------------------------------------------------------------------------------------
# answer-completeness
# ---------------------------------------------------------------------------------------------

ANSWER_COMPLETENESS_PROMPT_NAME = "answer-completeness-judge"


class AnswerCompletenessRequest(BaseModel):
    """The values the answer-completeness judge prompt is rendered from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prediction: str
    reference: str


class CompletenessJudgement(BaseModel):
    """The answer-completeness judge's answer: the reference's key points, split in two.

    Attributes:
        covered: Key points the prediction covers.
        missing: Key points the prediction leaves out.
    """

    model_config = _JUDGE_OUTPUT_CONFIG

    covered: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()


class AnswerCompletenessJudgePrompt(TypedPrompt):
    """Break the reference into key points, and judge which ones the prediction actually covers.

    Not a RAGAS metric — `docs/10-technique-catalogue.md` §1.3's own row states RAGAS has no
    completeness metric in the paper or the library, which is why this plugin is named
    `answer-completeness` rather than carrying a `ragas_` prefix that would claim otherwise.
    """

    name: ClassVar[str] = ANSWER_COMPLETENESS_PROMPT_NAME
    version: ClassVar[str] = PROMPT_CONTRACT_VERSION
    input_model: ClassVar[type[BaseModel]] = AnswerCompletenessRequest
    output_model: ClassVar[type[BaseModel] | None] = CompletenessJudgement
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You check how completely a predicted answer covers a reference answer. "
                "Break the reference answer into its key points, then judge which of those "
                "points the predicted answer actually covers, and which it leaves out."
            ),
            user=(
                "Reference answer:\n${reference}\n\nPredicted answer:\n${prediction}\n\n"
                "List the reference's key points, split into ones the predicted answer "
                "covers and ones it leaves out."
            ),
        ),
    }


__all__ = [
    "ANSWER_COMPLETENESS_PROMPT_NAME",
    "ANSWER_CORRECTNESS_PROMPT_NAME",
    "ANSWER_RELEVANCE_PROMPT_NAME",
    "CONTEXT_RECALL_PROMPT_NAME",
    "CONTEXT_RELEVANCE_PROMPT_NAME",
    "FAITHFULNESS_PROMPT_NAME",
    "AnswerCompletenessJudgePrompt",
    "AnswerCompletenessRequest",
    "AnswerCorrectnessJudgePrompt",
    "AnswerCorrectnessRequest",
    "AnswerRelevanceJudgePrompt",
    "AnswerRelevanceRequest",
    "ClaimSupport",
    "CompletenessJudgement",
    "ContextRecallJudgePrompt",
    "ContextRecallJudgement",
    "ContextRecallRequest",
    "ContextRelevanceJudgePrompt",
    "ContextRelevanceJudgement",
    "ContextRelevanceRequest",
    "FactualClassification",
    "FaithfulnessJudgePrompt",
    "FaithfulnessJudgement",
    "FaithfulnessRequest",
    "GeneratedQuestions",
    "StatementSupport",
]
