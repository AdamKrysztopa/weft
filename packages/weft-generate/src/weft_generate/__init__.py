"""First-party generation pack.

Publishes the `Generator` contract (`contract.py`) and the answer vocabulary
(`payload.py`). Task **2.4** built the mechanism and registered nothing under it, the
same way `weft-retrieve` did before task 2.7 — see
`packages/weft-retrieve/src/weft_retrieve/__init__.py` for the whole reason a `weft.packs`
entry point waits for a plugin to name. Task **2.9** was the first plugin here:
`cited-answer`, brought together with its own registered `Prompt` in one `register()`
call, the same shape `weft_retrieve.register` uses for `llm-rerank` and
`passage-relevance`. **Task 2.22 is the second**: `contradiction-check`, with its own two
registered prompts. **Task 2.24 is the third**: `refine-on-uncertainty`, which registers no
new prompt of its own — its own drafting call reuses `cited-answer`'s already-registered
`answer-with-citations`, and its uncertainty trigger is `weft_retrieve.contract.Sufficiency`
(task 2.4's contract; `weft_retrieve.sufficiency`, this same task's other half, is where
`llm-sufficiency` and `hedge-phrases` register), resolved by name through `StageLookup`
rather than imported here.
"""

from pydantic import BaseModel, ConfigDict

from weft_generate.cited_answer import NAME as CITED_ANSWER_NAME
from weft_generate.cited_answer import CitedAnswer, CitedAnswerConfig, WhenNoEvidence
from weft_generate.contract import GENERATE_CONTRACT_VERSION, Generator
from weft_generate.contradiction import NAME as CONTRADICTION_CHECK_NAME
from weft_generate.contradiction import Agreement, ContradictionCheck, ContradictionCheckConfig
from weft_generate.payload import Answer, AnswerStance, Citation
from weft_generate.prompts import (
    ANSWER_WITH_CITATIONS_NAME,
    CONTRADICTION_ANSWER_NAME,
    CONTRADICTION_CRITIC_NAME,
    AnswerWithCitationsPrompt,
    ConflictStatus,
    ContradictionAnswerPrompt,
    ContradictionCriticPrompt,
)
from weft_generate.refine import NAME as REFINE_ON_UNCERTAINTY_NAME
from weft_generate.refine import (
    RefinementStop,
    RefinementTrace,
    RefineOnUncertainty,
    RefineOnUncertaintyConfig,
    refinement_stop,
)
from weft_kernel.discovery import PackRegistrar
from weft_prompts.contract import Prompt


class Settings(BaseModel):
    """`weft-generate` takes no pack settings — an empty model is still the required shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")


def register(registrar: PackRegistrar, settings: Settings) -> None:
    """Register every `Generator` this pack ships, and the prompts each one asks under
    `Prompt`.

    Every `Prompt` goes through the same `registrar` as its owning `Generator` —
    `weft_retrieve.__init__`'s own docstring states why a first-party prompt belongs to
    the plugin that asks the question rather than to `weft-prompts`, which registers
    nothing at all.
    """
    del settings
    registrar.add(Generator, CITED_ANSWER_NAME, CitedAnswer)
    registrar.add(Prompt, ANSWER_WITH_CITATIONS_NAME, AnswerWithCitationsPrompt)
    registrar.add(Generator, CONTRADICTION_CHECK_NAME, ContradictionCheck)
    registrar.add(Prompt, CONTRADICTION_CRITIC_NAME, ContradictionCriticPrompt)
    registrar.add(Prompt, CONTRADICTION_ANSWER_NAME, ContradictionAnswerPrompt)
    registrar.add(Generator, REFINE_ON_UNCERTAINTY_NAME, RefineOnUncertainty)


__all__ = [
    "ANSWER_WITH_CITATIONS_NAME",
    "CITED_ANSWER_NAME",
    "CONTRADICTION_ANSWER_NAME",
    "CONTRADICTION_CHECK_NAME",
    "CONTRADICTION_CRITIC_NAME",
    "GENERATE_CONTRACT_VERSION",
    "REFINE_ON_UNCERTAINTY_NAME",
    "Agreement",
    "Answer",
    "AnswerStance",
    "AnswerWithCitationsPrompt",
    "Citation",
    "CitedAnswer",
    "CitedAnswerConfig",
    "ConflictStatus",
    "ContradictionAnswerPrompt",
    "ContradictionCheck",
    "ContradictionCheckConfig",
    "ContradictionCriticPrompt",
    "Generator",
    "RefineOnUncertainty",
    "RefineOnUncertaintyConfig",
    "RefinementStop",
    "RefinementTrace",
    "Settings",
    "WhenNoEvidence",
    "refinement_stop",
    "register",
]
