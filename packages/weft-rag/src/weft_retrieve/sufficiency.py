"""`llm-sufficiency` and `hedge-phrases` — two `Sufficiency` implementations.

Task **2.24**, `docs/build-ledger.md`: "a draft's uncertainty is a replaceable, named signal
rather than a phrase list, so the trigger cannot break silently under another language or
model." `10` §1.1's own `refine-on-uncertainty` row states the exact failure this line exists
to close: a nine-phrase localised list checked with `str.__contains__` is a mechanism that
"fires on hedging, never on unsupportedness, and breaks silently under another language or
system prompt." *Silently* is the load-bearing word: a hard-coded English phrase list that
never matches a Polish hedge does not raise, does not log, and no test anywhere goes red — the
refinement it was supposed to trigger simply never fires.

**The fix is not a better phrase list — it is that no phrase list is hard-coded into a
generator at all.** `weft_retrieve.contract.Sufficiency` (published at task 2.4) is a named,
registered contract, resolved by name through `StageLookup` exactly the way `weft_retrieve.
iterative`'s own `sufficiency` field already resolves it; `weft_generate.refine.
RefineOnUncertainty` (task 2.24's other half) never imports either class below and does not
know which one a document names. The mechanism a trigger fires on becomes a fact a `with:`
block states, not a constant this file closes over.

**`llm-sufficiency`** is the default: one model call, asked through `weft_prompts.cascade.
execute` — the same path every other model-backed plugin in this tree already takes — against
`weft_retrieve.prompts.SufficiencyCheckPrompt`, a bilingual prompt registered under
`weft_prompts.contract.Prompt` in `weft_retrieve.register`. Reading "is this enough" through a
model that already speaks the question's own language is what keeps this implementation
correct in Polish without a line of this file knowing a word of it — the model does.

**`hedge-phrases`** is kept rather than discarded, as the documented weak baseline —
`.phase2-design.md` §10's own row states it plainly: authored fresh for Weft, documented as
the weak baseline, and exactly the `str.__contains__` mechanism it replaces. What actually
changes it from a defect into a stated limitation is that the table it reads
(`markers: Mapping[str, tuple[str, ...]]`) is *configuration*, not a literal closed over by
one call site — an operator who wants a third language adds a key to a `with:` block, never a
line here. Its own test module is written so the Polish case *can* fail — the property a
single-language table could never be checked against, because it was never expected to
handle a second language.

**Both consumers, one contract, `draft` is the fork.** `Sufficiency`'s own docstring: "a named
contract with two implementations is what 'replaceable' means here." `iterative-retrieval`
calls `assess` with `draft=None` — judging accumulated evidence alone.
`refine-on-uncertainty` calls it with the drafted answer's own text — judging whether *that
draft* shows its work. `llm-sufficiency` reads both the same way, one call either way.
`hedge-phrases` can only judge a draft's own wording: handed `draft=None` it has nothing to
inspect and answers `Assessment(observed=False)`, the contract's own "could not look" case, at
zero cost — an honest admission of a narrower job, not a guess in either direction.
"""

from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Outcome, Produced
from weft_llm.contract import LLM
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Assessment, Passage, Passages, Query
from weft_retrieve.prompts import (
    SUFFICIENCY_CHECK_NAME,
    SufficiencyCheckRequest,
    SufficiencyJudgement,
)

#: The name this `Sufficiency` implementation is registered and selectable under.
LLM_SUFFICIENCY_NAME = "llm-sufficiency"
#: The name the phrase-list baseline is registered and selectable under.
HEDGE_PHRASES_NAME = "hedge-phrases"


class LlmSufficiencyConfig(BaseModel):
    """`LlmSufficiency`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=SUFFICIENCY_CHECK_NAME, min_length=1)
    role: str = Field(default="grade", min_length=1)
    max_evidence: int = Field(default=8, ge=1)


class LlmSufficiency:
    """Asks a model whether the evidence — and, when given, a draft grounded in it — suffices.
    Satisfies `weft_retrieve.contract.Sufficiency` structurally.

    `cost_bound = (1, 1)` — one call, always. Unlike a reranker or a grader, this contract's
    whole job is to be asked; there is no "nothing offered" shortcut the way an empty
    `Ranking` gives `weft_retrieve.rerank.LlmRerank`'s own floor of zero — a question is
    always in hand, even when the evidence answering it is not.
    """

    config_model: ClassVar[type[LlmSufficiencyConfig]] = LlmSufficiencyConfig
    cost_bound: ClassVar[tuple[int, int]] = (1, 1)

    def __init__(self, config: LlmSufficiencyConfig | None = None) -> None:
        self._config = config if config is not None else LlmSufficiencyConfig()

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]:
        """One cascade call, read straight into `Assessment`.

        A cascade failure is relayed exactly as it answered, never softened into
        `Assessment(observed=False)` — that reading belongs to an implementation that
        genuinely has nothing to inspect (`hedge-phrases`, handed `draft=None`), not to this
        one when a model call it actually attempted came back unusable. A caller that wants a
        hard failure here treated as something other than a hard failure states so with its
        own field (`weft_retrieve.iterative.IterativeRetrievalConfig.on_critic_failure`,
        `weft_generate.refine.RefineOnUncertaintyConfig.on_signal_failure`) — this plugin's
        job stops at reporting what actually happened.
        """
        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        offered = evidence.passages[: self._config.max_evidence]
        request = SufficiencyCheckRequest(
            question=question.text, evidence=_offer(offered), draft=draft or ""
        )
        judged = await execute(
            llm=llm,
            prompt=prompt,
            values=request,
            output=SufficiencyJudgement,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(judged, Produced):
            return judged
        verdict = judged.value.value
        return Produced(
            value=Assessment(
                sufficient=verdict.sufficient,
                confidence=verdict.confidence,
                missing=verdict.missing,
                observed=True,
            )
        )


#: A nine-phrase weak-baseline mechanism (`10` §1.1's `refine-on-uncertainty` row),
#: authored fresh for Weft rather than ported — see the module docstring — and made a
#: *table* rather than a call site. English and Polish only: a third locale is an
#: operator's own `with: {markers: {...}}` block, never an edit here.
DEFAULT_HEDGE_MARKERS: Mapping[str, tuple[str, ...]] = {
    "en": (
        "i'm not sure",
        "i am not sure",
        "i don't know",
        "i do not know",
        "it is unclear",
        "it's unclear",
        "hard to say",
        "difficult to say",
        "i cannot determine",
        "i can't determine",
        "not certain",
        "cannot be determined",
    ),
    "pl": (
        "nie jestem pewien",
        "nie jestem pewna",
        "nie wiem",
        "trudno powiedzieć",
        "trudno jednoznacznie",
        "niejasne",
        "nie jest jasne",
        "nie da się jednoznacznie stwierdzić",
        "brak pewności",
        "nie sposób ustalić",
    ),
}


class HedgePhrasesConfig(BaseModel):
    """`HedgePhrases`'s `with:` config. Every field has a default, per this pack's own rule.

    `markers` is a locale-keyed table of substrings, checked case-insensitively — the same
    weak-baseline mechanism, with its one real defect fixed: the table an operator reaches is
    configuration, not a constant this file closes over.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    markers: Mapping[str, tuple[str, ...]] = Field(default_factory=lambda: DEFAULT_HEDGE_MARKERS)


class HedgePhrases:
    """Tests a draft's own wording against a locale-keyed phrase table. Satisfies
    `weft_retrieve.contract.Sufficiency` structurally.

    `cost_bound = (0, 0)` — no model is ever asked; that is the point of shipping this beside
    `llm-sufficiency` rather than only documenting it as a cautionary tale. **Zero model calls
    is not zero cost of every kind**: this implementation can only ever be as good as its own
    table, and it has nothing to say about *unsupportedness* — a confident, fluent, entirely
    fabricated draft with no hedge phrase in it reads as `sufficient=True` here exactly as it
    would to any purely lexical mechanism. `10` §1.1's own stated divergence ("this fires on
    hedging, never on unsupportedness") is carried forward as a fact about *this
    implementation*, not fixed by it — `llm-sufficiency` is the one that can judge grounding,
    because it reads the evidence, not only the draft's own tone.
    """

    config_model: ClassVar[type[HedgePhrasesConfig]] = HedgePhrasesConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: HedgePhrasesConfig | None = None) -> None:
        self._config = config if config is not None else HedgePhrasesConfig()

    async def assess(
        self, question: Query, evidence: Passages, draft: str | None, ctx: Context
    ) -> Outcome[Assessment]:
        """Substring-match `draft` against `question.locale`'s own marker table.

        `evidence` is not read — this implementation judges a draft's *wording*, never
        whether it is grounded, which is the module docstring's own stated limitation rather
        than a hidden one. `draft=None` (`iterative-retrieval`'s own evidence-sufficiency use)
        is not a case this plugin guesses at: there is no draft to inspect, so it answers
        honestly that it could not look, at zero cost, rather than defaulting either way.
        """
        del ctx
        if draft is None:
            return Produced(
                value=Assessment(sufficient=False, confidence=0.0, missing=(), observed=False)
            )
        markers = _markers_for(question.locale, self._config.markers)
        hedged = any(marker.lower() in draft.lower() for marker in markers)
        return Produced(
            value=Assessment(
                sufficient=not hedged,
                confidence=0.0 if hedged else 1.0,
                missing=(),
                observed=True,
            )
        )


def _offer(passages: tuple[Passage, ...]) -> str:
    """The offered evidence as one string, numbered by each passage's own `label` — the same
    shape every other model-backed plugin in this pack builds; see `weft_retrieve.rerank.
    _offer`'s own docstring for why a template cannot do this itself. `(none gathered yet)`
    rather than an empty string: `iterative-retrieval`'s first round and a `refine-on-
    uncertainty` document with no upstream retrieval both legitimately reach this with
    nothing offered, and the model should read that as a fact, not a blank line.
    """
    if not passages:
        return "(none gathered yet)"
    return "\n\n".join(f"[{passage.label}] {passage.node.content}" for passage in passages)


def _markers_for(locale: str | None, markers: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """`markers`'s own entry for `locale`, falling back exact → primary subtag → `en` → none.

    The same three-step fallback `weft_prompts.typed_prompt.TypedPrompt`'s own selection uses
    for translated text (that module's own docstring: "exact locale → primary subtag → en"),
    applied here to a configuration table instead of a template, so `pl-PL` reaches the same
    markers `pl` does without a second key in every operator's table.
    """
    if locale is not None:
        if locale in markers:
            return markers[locale]
        primary = locale.split("-", 1)[0]
        if primary in markers:
            return markers[primary]
    return markers.get("en", ())
