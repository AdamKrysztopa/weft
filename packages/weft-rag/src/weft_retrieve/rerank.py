"""Rerankers — the position after fusion. `llm-rerank` is the one this task ships.

Task **2.7**, `docs/build-ledger.md`: "fusion and reranking are composable plugins a third
party can retune, not a fixed ladder." `weft_retrieve.fusion`'s module docstring carries the
evidence for the fusion half; this is the reranking half of the same sentence. A reranking step
fused into a single monolithic pipeline rather than exposed as its own plugin is how a name
promising one pass came to cost "a query-rewrite call, all-modes hybrid retrieval,
cross-encoder reranking and up to *N* regenerations" (`10` §1.1's row, quoted in
`weft_retrieve.vector_top_k`). A rung nobody can remove is a rung nobody can measure.

**Reranking is a separate contract from fusion, and that is the whole claim.** `Reranker` is
`Stage[Ranking, Ranking]`, so a document may place none, one, or two of them, before or after
each other, and the kernel's own `_check_composition` refuses only the orders that do not
compose — a reranker before a fuser, because `Candidates` is not `Ranking`. Nothing in this
module knows whether a fuser ran, which fuser it was, or whether another reranker follows.
That is what "not a ladder" means mechanically: the sequence is data in a document, and
`tests/unit/weft_retrieve/test_init.py` resolves four of those documents to prove it.

**`cross-encoder-rerank` is deliberately not what ships here.** `.phase2-design.md` §10 states
the reason rather than dropping the row quietly: it needs a model download, which `09` §4.4's
argument keeps out of the gate, and `10` §1.2 files it on the index path anyway. `llm-rerank`
adds no dependency — it asks the model an operator has already configured, under a role they
already map.

**How a technique reaches a prompt, recorded because the design record is silent on it.**
`.phase2-design.md` publishes `Prompts` (render a prompt *by name*) and
`weft_prompts.cascade.execute` (take a `Prompt` *object* through the three tiers), and never
says which one a plugin with a `prompt: str` configuration field uses to get from the first to
the second. This build resolves the name through `StageLookup.build_capability(Prompt, name)`
— the published service whose signature is exactly "give me the registered capability of this
contract type under this name", the same way ledger 2.20 will resolve its `sufficiency: str`
against the `Sufficiency` contract. That reaches the cascade with the prompt object it needs,
refuses an unregistered name with the registry's own `UnknownPluginError` (naming the contract,
the name and every valid option), and invents no second prompt-resolution path. The alternative
— rendering through `Prompts` and re-implementing the step-down here — would put a second copy
of the cascade in a technique pack: the same three-copies-of-one-formula failure this design
refuses, in a different corner.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import Failed, Outcome, Produced
from weft_llm.contract import LLM
from weft_prompts.cascade import execute
from weft_prompts.contract import Prompt
from weft_retrieve.contract import StageLookup
from weft_retrieve.payload import Passage, Ranking
from weft_retrieve.prompts import (
    PASSAGE_RELEVANCE_NAME,
    PassageRelevance,
    PassageRelevanceRequest,
)
from weft_store.contract import Scored

#: The name this reranker is registered and selectable under — see `weft_retrieve.register`.
NAME = "llm-rerank"


class LlmRerankConfig(BaseModel):
    """`LlmRerank`'s `with:` config. Every field has a default, per this pack's own rule.

    Three fields, and each is a thing an operator genuinely retunes: **which wording** the
    model is judged by (`prompt`), **which model** answers (`role`, resolved against
    `[llm.roles]` in `weft.toml` — a stage never names a provider), and **how much evidence
    survives** (`top_n`). None of them is a threshold on the model's own numbers: a
    `keep_above: float` here would be `10` §2.1's tuning constant with no measurement behind
    it, and `graded-retrieval` (ledger 2.21) is the plugin whose job is a *filter* with a
    stated grade cut-off. This one orders and truncates.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt: str = Field(default=PASSAGE_RELEVANCE_NAME, min_length=1)
    role: str = Field(default="rerank", min_length=1)
    top_n: int = Field(default=20, ge=1)


class LlmRerank:
    """Rescores one ranking against the question. Satisfies `contract.Reranker` structurally.

    `cost_bound = (0, 1)` — zero when the ranking is empty, because `run` returns before
    resolving anything; one otherwise. A cascade that steps down from tier 1 to tier 3 is the
    *same* ask re-put in three ways rather than three questions, which is the arithmetic
    `.phase2-design.md` §10 already uses when it gives `graded-retrieval` `(1, 4)` for four
    batches of five. Stating the other reading would make every cascading plugin in this phase
    declare a ceiling three times its real one.
    """

    config_model: ClassVar[type[LlmRerankConfig]] = LlmRerankConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 1)

    def __init__(self, config: LlmRerankConfig | None = None) -> None:
        self._config = config if config is not None else LlmRerankConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Ranking]:
        """Every hit judged against `origin`, reordered by what came back, truncated to `top_n`.

        **`payload.origin`, never a derived query.** The question the passages are judged
        against is the user's own words. `QuerySet.origin`'s docstring records why that is a
        type-level invariant rather than a convention here: a HyDE implementation that hands its
        hallucinated document to the reranker *as the query* scores every candidate for
        resemblance to something the model had just invented. A reranker that reads
        `origin` cannot repeat it.

        **An empty ranking is returned exactly as it arrived**, with no model call — the
        emptiness rule from `weft_retrieve.contract`, and the floor of `cost_bound`. Answering
        `NothingToProduce` would stop the pipeline where `09` §4's V2 requires the engine to
        say "not in this corpus".

        **A judgement set that is not exactly one per offered passage is refused.** Filling in
        the gaps from the retrieval order would produce an ordering half chosen by a model and
        half by the store, indistinguishable from one somebody chose — the silent fallback the
        project rules refuse, landing on the one number a reader never sees.
        """
        if not payload.hits:
            return Produced(value=payload)

        llm = ctx.require(LLM)
        lookup = ctx.require(StageLookup)
        prompt = await lookup.build_capability(Prompt, self._config.prompt)
        values = PassageRelevanceRequest(
            question=payload.origin.text, passages=_offer(payload.hits)
        )
        judged = await execute(
            llm=llm,
            prompt=prompt,
            values=values,
            output=PassageRelevance,
            role=self._config.role,
            ctx=ctx,
        )
        if not isinstance(judged, Produced):
            # A cascade that could not get a typed answer, or a prompt that had nothing to
            # ask, is relayed exactly as it answered. Reinterpreting it here would invent a
            # judgement nobody made.
            return judged

        scored = _scores_by_index(judged.value.value, offered=len(payload.hits))
        if isinstance(scored, Failed):
            return scored
        ordered = sorted(enumerate(payload.hits), key=lambda pair: (-scored[pair[0]], pair[1].rank))
        hits = tuple(
            _rescored(passage, relevance=scored[index], rank=rank)
            for rank, (index, passage) in enumerate(ordered[: self._config.top_n])
        )
        return Produced(
            value=Ranking(
                origin=payload.origin,
                hits=hits,
                contributors=payload.contributors,
                ext=payload.ext,
            )
        )


def _offer(hits: tuple[Passage, ...]) -> str:
    """The candidates, one per line, numbered by the index an answer refers back to.

    The numbering is written here and read back in `_scores_by_index`, so the two cannot
    disagree about what `[2]` meant. Content is passed whole: truncating it would be a tuning
    constant in the one place it changes what the model is judging, and how much evidence
    reaches a reranker is the *retriever's* `top_k` — a number an operator already sets.
    """
    return "\n".join(f"[{index}] {passage.node.content}" for index, passage in enumerate(hits))


def _scores_by_index(judged: PassageRelevance, *, offered: int) -> dict[int, float] | Failed:
    """One relevance per offered index, or a `Failed` naming exactly how the set was wrong.

    Three ways it can be wrong and all three are named separately, because "the model answered
    badly" is not something an operator can act on: an index nobody offered means the model
    invented a passage, a missing index means it skipped one, and a repeated index means it
    answered twice and the two answers disagree about the same passage.
    """
    scores: dict[int, float] = {}
    unknown: list[int] = []
    repeated: list[int] = []
    for judgement in judged.judgements:
        if judgement.index >= offered:
            unknown.append(judgement.index)
        elif judgement.index in scores:
            repeated.append(judgement.index)
        else:
            scores[judgement.index] = judgement.relevance
    missing = [index for index in range(offered) if index not in scores]
    if unknown or repeated or missing:
        return Failed(
            reason=(
                f"'{NAME}' offered {offered} passage(s) and asked for one judgement each, and "
                f"the model did not answer that: index/indices {unknown or 'none'} were never "
                f"offered, {repeated or 'none'} were judged more than once, and "
                f"{missing or 'none'} were not judged at all. Reordering on a partial answer "
                f"would mix the model's ranking with the retriever's."
            )
        )
    return scores


def _rescored(passage: Passage, *, relevance: float, rank: int) -> Passage:
    """`passage` carrying the reranker's own score and its new position.

    The retrieval score is replaced rather than kept alongside. `Scored[Node]`'s own docstring
    settles this: the score "is a property of one search, not of the node", and after this
    stage the search whose opinion the list is sorted by is *this* one. Leaving the retrieval
    score in place would leave a ranking sorted by one number and labelled with another, which
    any downstream consumer that sorts by score would silently undo.
    """
    return Passage(
        scored=Scored(value=passage.node, score=relevance),
        rank=rank,
        retrieved_by=passage.retrieved_by,
        label=passage.label,
    )
