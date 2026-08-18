"""The prompts `weft-generate`'s own plugins ask. Registered here, under the plugin that
asks each one.

Task **2.10**'s ledger line settles where a prompt lives: "every first-party prompt
belongs to the plugin that asks it a question." `weft_retrieve.prompts` is the precedent
this module follows exactly — same shape, same reasoning, moved one pack downstream
because `cited-answer` is `weft-generate`'s question, not `weft-retrieve`'s. Task **2.22**
extends this file the same way task 2.16 and 2.17 extended `weft_retrieve.prompts`: one
file accumulating every prompt this pack's plugins ask, rather than one module per prompt.

**Plain text, not structured output.** `output_model = None`: the shape of an answer is
prose with bracketed markers in it, not a JSON schema a model fills in, so
`weft_generate.cited_answer` calls `weft_llm.contract.LLM.complete` directly rather than
`weft_prompts.cascade.execute` — the cascade exists for typed answers, and forcing one
here would trade "the model wrote an answer" for "the model wrote an answer *and* filled
in a schema describing it", which is strictly more ways for a completion to fail for no
gain: `cited_answer._citations_for` reads the markers back out of the text itself.

**Why the offered passages arrive as one pre-rendered string, numbered by their own
label.** Exactly `weft_retrieve.prompts`'s own reason — `${name}` over `string.Template`
cannot iterate, so joining and numbering the evidence is the plugin's work. What is
different here, and load-bearing: the numbers shown are `Passage.label`, the marker a
`ContextPacker` already assigned, never a re-derived index. A model that writes `[1]`
because it was shown `[1]` writes a marker `Answer._citations_resolve` can resolve; a
model shown position `0` and asked to cite "index 0" would hand this plugin a second
numbering to reconcile against the packer's, which is exactly the renumbering bug that
validator exists to refuse.
"""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from weft_prompts.typed_prompt import PromptText, TypedPrompt

#: The name this prompt is registered and selectable under, and `cited-answer`'s default.
ANSWER_WITH_CITATIONS_NAME = "answer-with-citations"


class AnswerWithCitationsRequest(BaseModel):
    """What `answer-with-citations` renders: the question, and the numbered evidence.

    `passages` is `""` exactly when `cited_answer.WhenNoEvidence.ANSWER_FROM_MEMORY` is
    configured and nothing was retrieved — the template still has to render, so the
    instruction below covers that case in words rather than this model growing a flag
    the prompt would then have to branch on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    passages: str


class AnswerWithCitationsPrompt(TypedPrompt):
    """Ask a model to answer the question, citing every claim by the passage number shown."""

    name: ClassVar[str] = ANSWER_WITH_CITATIONS_NAME
    input_model: ClassVar[type[BaseModel]] = AnswerWithCitationsRequest
    output_model: ClassVar[type[BaseModel] | None] = None
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You answer questions using only the passages you are given. Cite every "
                "claim with the bracketed number of the passage it rests on, exactly as "
                "shown to you, for example [1]. Never invent a number you were not shown. "
                "If no passages are given, say plainly that you are answering from your "
                "own knowledge rather than from a source, and write no bracketed numbers "
                "at all."
            ),
            user="Question: ${question}\n\nPassages:\n${passages}",
        ),
        "pl": PromptText(
            system=(
                "Odpowiadasz na pytania, korzystając wyłącznie z podanych fragmentów. Każde "
                "twierdzenie opatrz numerem fragmentu w nawiasie kwadratowym, dokładnie tak, "
                "jak został ci pokazany, np. [1]. Nigdy nie wymyślaj numeru, którego nie "
                "pokazano. Jeśli nie podano żadnych fragmentów, powiedz wprost, że "
                "odpowiadasz z własnej wiedzy, a nie ze źródła, i nie pisz żadnych numerów "
                "w nawiasach."
            ),
            user="Pytanie: ${question}\n\nFragmenty:\n${passages}",
        ),
    }


#: The name this prompt is registered and selectable under, and `contradiction-check`'s
#: own `critic_prompt` default.
CONTRADICTION_CRITIC_NAME = "contradiction-critic"


class ConflictStatus(StrEnum):
    """Whether the offered sources agree, disagree, or the critic could not tell.

    Rongwu Xu, Zehan Qi, Zhijiang Guo, Cunxiang Wang, Hongru Wang, Yue Zhang, Wei Xu,
    *Knowledge Conflicts for LLMs: A Survey*, EMNLP 2024, pp. 8541-8565, arXiv:2403.08319
    — "inter-context conflict" is the phenomenon `CONFLICT` names. `docs/10-technique-
    catalogue.md`'s own row records that Vignesh Gokul, Srikanth Tenneti, Alwarappan
    Nakkiran, *Contradiction Detection in RAG Systems*, arXiv:2504.00180, 2025 postdates
    the reference and is a parallel framing, not a source this plugin implements.

    **`UNDETERMINED` is not a fourth possible fact about the sources — it is what a
    critic that could not judge them reports**, and it is the one member this whole task
    exists to make reachable. `weft_generate.contradiction`'s own module docstring is
    where that is made mechanical: `UNDETERMINED` is both what the model answers when it
    genuinely cannot tell from the evidence in front of it, and what `ContradictionCheck`
    substitutes locally when the critic's own cascade call could not be parsed at all —
    the same value either way, because from a reader's side both are "the engine did not
    establish agreement", and neither may ever be silently reported as `AGREE`. The
    reference's `critique.py:158-166` returned `has_consensus=True` on critique failure; this
    enum's third member is the fix, held at the type a reader actually sees rather than
    left to a docstring's promise.
    """

    AGREE = "agree"
    CONFLICT = "conflict"
    UNDETERMINED = "undetermined"


class ContradictionCriticRequest(BaseModel):
    """What `contradiction-critic` renders: the question, and the numbered evidence.

    `question` is `Passages.origin.text` — the user's own words, never a query an
    earlier stage derived, the same obligation every prompt in this pack and
    `weft_retrieve`'s own carries.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    passages: str


class ContradictionCritique(BaseModel):
    """The critic's own judgement: whether the offered sources agree, and on what.

    `agreed` and `conflicts` are short statements, each free to reference an offered
    passage by the bracketed label it was shown under (`weft_generate.contradiction._offer`
    numbers them exactly the way `weft_generate.cited_answer._offer` does) — read back
    only as prose the final answer weaves in, never re-validated against a label the way
    `Answer.citations` is, because this model is the critic's private working note, not
    the citation a reader follows.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: ConflictStatus
    agreed: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class ContradictionCriticPrompt(TypedPrompt):
    """Ask a model whether the offered passages agree, disagree, or cannot be judged.

    The instruction is explicit that `undetermined` is a real, expected answer — not a
    last resort the model reaches for only when confused — because a critic that reaches
    for `agree` whenever it is unsure is exactly the reference's own defect, moved from a
    caught exception into the model's own judgement instead of out of it.
    """

    name: ClassVar[str] = CONTRADICTION_CRITIC_NAME
    input_model: ClassVar[type[BaseModel]] = ContradictionCriticRequest
    output_model: ClassVar[type[BaseModel] | None] = ContradictionCritique
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You judge whether a set of retrieved passages agree with each other about "
                "a question. Answer 'conflict' only when two or more passages state facts "
                "that cannot both be true. Answer 'undetermined' whenever you cannot tell "
                "from the passages given — too little overlap between them, or too little "
                "detail to compare — rather than guessing 'agree'. Every point you list, in "
                "either agreed or conflicts, should reference the bracketed passage number "
                "it rests on, for example [1]."
            ),
            user=(
                "Question: ${question}\n\n"
                "Passages:\n${passages}\n\n"
                "Judge whether these passages agree about the question. Answer with a "
                "status of 'agree', 'conflict' or 'undetermined', the points they agree on, "
                "and the points on which they conflict."
            ),
        ),
        "pl": PromptText(
            system=(
                "Oceniasz, czy zbiór odnalezionych fragmentów jest ze sobą zgodny w "
                "odniesieniu do pytania. Odpowiedz 'conflict' tylko wtedy, gdy dwa lub "
                "więcej fragmentów podaje fakty, które nie mogą być jednocześnie prawdziwe. "
                "Odpowiedz 'undetermined', gdy nie potrafisz tego ocenić na podstawie "
                "podanych fragmentów — zbyt mało części wspólnej między nimi lub zbyt mało "
                "szczegółów do porównania — zamiast zgadywać 'agree'. Każdy punkt, "
                "zgodności lub konfliktu, powinien odwoływać się do numeru fragmentu w "
                "nawiasie kwadratowym, na którym się opiera, np. [1]."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Fragmenty:\n${passages}\n\n"
                "Oceń, czy te fragmenty są ze sobą zgodne w odniesieniu do pytania. "
                "Odpowiedz statusem 'agree', 'conflict' lub 'undetermined', punktami "
                "zgodności oraz punktami konfliktu."
            ),
        ),
    }


#: The name this prompt is registered and selectable under, and `contradiction-check`'s
#: own `answer_prompt` default.
CONTRADICTION_ANSWER_NAME = "contradiction-answer"


class ContradictionAnswerRequest(BaseModel):
    """What `contradiction-answer` renders: the question, the numbered evidence, and the
    critic's own findings, pre-rendered as text for the same reason `AnswerWithCitations
    Request.passages` is — `${name}` over `string.Template` cannot iterate.

    `findings` is `weft_generate.contradiction._findings_text`'s own rendering of a
    `ContradictionCritique` — including the case where the critic could not look, so this
    prompt's own instruction can tell the reader that plainly rather than writing an
    answer that is silent about it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    question: str
    passages: str
    findings: str


class ContradictionAnswerPrompt(TypedPrompt):
    """Ask a model to write a final answer that separates agreement from conflict, cited.

    Plain text, not structured output — the same split `weft_generate.prompts.
    AnswerWithCitationsPrompt`'s own docstring states: the shape of an answer is prose
    with bracketed markers in it, and `weft_generate.contradiction._citations_for` reads
    the markers back out of the text itself rather than asking for a second structured
    list a model's prose and its own citations could disagree about.
    """

    name: ClassVar[str] = CONTRADICTION_ANSWER_NAME
    input_model: ClassVar[type[BaseModel]] = ContradictionAnswerRequest
    output_model: ClassVar[type[BaseModel] | None] = None
    texts: ClassVar[Mapping[str, PromptText]] = {
        "en": PromptText(
            system=(
                "You answer questions using only the passages you are given, and you have "
                "already been told whether those passages agree. Write an answer that "
                "states plainly whether the sources agree, conflict, or could not be "
                "compared, and separates what they agree on from what they conflict on. "
                "Cite every claim with the bracketed number of the passage it rests on, "
                "exactly as shown to you, for example [1]. Never invent a number you were "
                "not shown."
            ),
            user=(
                "Question: ${question}\n\n"
                "Passages:\n${passages}\n\n"
                "Critic's findings:\n${findings}\n\n"
                "Write the final answer, citing every claim."
            ),
        ),
        "pl": PromptText(
            system=(
                "Odpowiadasz na pytania, korzystając wyłącznie z podanych fragmentów, a "
                "informację o tym, czy te fragmenty są ze sobą zgodne, już otrzymałeś. "
                "Napisz odpowiedź, która wprost stwierdza, czy źródła są zgodne, "
                "sprzeczne, czy nie dało się ich porównać, i oddziela to, na czym się "
                "zgadzają, od tego, w czym są sprzeczne. Każde twierdzenie opatrz numerem "
                "fragmentu w nawiasie kwadratowym, dokładnie tak, jak został ci pokazany, "
                "np. [1]. Nigdy nie wymyślaj numeru, którego nie pokazano."
            ),
            user=(
                "Pytanie: ${question}\n\n"
                "Fragmenty:\n${passages}\n\n"
                "Ustalenia krytyka:\n${findings}\n\n"
                "Napisz ostateczną odpowiedź, cytując każde twierdzenie."
            ),
        ),
    }
