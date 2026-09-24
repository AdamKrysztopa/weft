"""`repack` — the one `ContextPacker` this task ships. `Stage[Ranking, Passages]`.

Task **2.19**, `docs/internal/build-ledger.md`: "context ordering is a named, parameterised stage
whose method does what the method is named after." `docs/10-technique-catalogue.md` §1.1's
own row on this technique names exactly the failure that sentence exists to refuse: an
implementation that emitted `[d0, d6, d1, d5, d2, d4, d3]` for n=7 — best at the head,
**worst** in slot 1, median at the tail — three lines below a docstring stating the
correct definition. A best/worst zip-interleave wearing Wang et al.'s name, and
hard-coded to `sides`, which is not even that paper's own winner.

**One plugin, three methods, because the three are one mechanism with a field.**
`RepackMethod` is a closed `StrEnum` — `forward` (retrieval order, unchanged), `reverse`
(the literal reverse: worst first, best last, immediately before the question) and
`sides` (best and second-best at the two ends, worst buried in the middle). Dispatch is a
mapping keyed on the enum, never an `if`/`elif` chain reading a string — the enum member
*is* the selector, so there is nothing left for a chain to re-decide, and a fourth method
is one function and one mapping entry, not a new branch to remember to add.

**`reverse` is the default**, not `forward` and not a hard-coded `sides`: Xiaohua
Wang et al. (14 authors), *Searching for Best Practices in Retrieval-Augmented Generation*,
EMNLP 2024, arXiv:2407.01219 §3.6, Table 11, selects `reverse` on its **Avg** column at
0.483. Nelson F. Liu, Kevin Lin, John Hewitt, Ashwin Paranjape, Michele Bevilacqua, Fabio
Petroni, Percy Liang, *Lost in the Middle: How Language Models Use Long Contexts*, TACL
vol. 12, pp. 157-173, 2024, arXiv:2307.03172, is the effect both methods exploit — a model
attends best to the start and the end of its context and worst to the middle, so `reverse`
puts the single most relevant passage in the position closest to the question.

**`sides`, correctly, this time.** Split the retrieval-ordered hits into the even
positions (0, 2, 4, …) and the odd ones (1, 3, 5, …); the even half stays in order at the
front, the odd half is reversed and appended. For seven hits ranked `d0` (best) through
`d6` (worst) that is `[d0, d2, d4, d6]` then `[d5, d3, d1]` — `[d0, d2, d4, d6, d5, d3,
d1]`, pinned by `tests/unit/weft_retrieve/test_repack.py`. Best at the head, second-best
at the very tail, worst at the seam in the middle — the shape Wang et al. name and the
shape LlamaIndex's `LongContextReorder` already ships correctly (`10` §1.1's row).
`LongContextReorder` is the framework's name for the *problem*; `sides`
is Wang et al.'s name for this *operation*, and that is the name this plugin keeps.

**Labels are assigned here, and this is the type at which they become final.**
`weft_retrieve.contract.ContextPacker`'s own docstring: "the citation labels a `Generator`
resolves against are assigned here." Every packed passage gets `str(position + 1)` in its
*final*, packed order — not its retrieval rank, which `top_n` and every method above may
already have moved it away from — so `[1]` in a generated answer always names whichever
passage this stage put first, regardless of which method arranged it there.
`weft_retrieve.payload.Passages`'s own model validator is what makes a packer that forgot
this, or that labelled two passages alike, unconstructable rather than silently wrong.
A passage's `rank` stays its position in the ranking this stage was handed, so a generator
reading fewer passages than were packed reads the best (`Passages.best_ranked`, `R32.2`).

**`top_n` truncates the input, before any method sees it.** Cutting after reordering would
let `sides` or `reverse` decide *which* hits survive as a side effect of deciding where
they sit — a second, hidden truncation policy this plugin does not have and `Ranking`'s own
producer (a `Fuser`'s `top_k`, a `Reranker`'s `top_n`) already owns. `None` keeps every hit
`Ranking.hits` arrived with.

**Generic over what a hit actually is, and that is deliberate.**
`.phase2-findings.md` §11 records that collapsing several derived nodes of one parent chunk
to that parent is a separate, named operation on the retrieval pack's own to-do list
(ledger 2.33), not a behaviour a `ContextPacker` performs implicitly. This module orders
and labels whatever tuple of `Passage`s a `Ranking` carries — it has no opinion on how many
of them share a parent, so a collapsing `Reranker` slotted in ahead of this one in a
document changes what `repack` receives and nothing about what `repack` does with it.

**A token budget, ledger task 32.7, gate G25.** `budget_tokens` keeps a prefix of `kept` —
after `top_n`, before `method` arranges it — in ranking order, dropping from the tail the
moment the next whole passage would push the evidence block a `Generator` will actually
receive past the budget. Whole passages, never a truncated one: a passage cut mid-sentence
still carries its citation label, and a reader who follows `[3]` into half a sentence has
been given a broken citation, not a shorter one. The count is asked of the `role`'s own
model, through `LLM`'s `TokenCounter` shape (`weft_llm.contract.TokenCounter`,
task 32.6) — the model that will read the context is the model whose tokeniser decides
whether it fits, and `cited_answer` asks the `generate` role by default
(`weft_generate/cited_answer.py`), which is why that is this field's default too. A best
passage that alone exceeds the budget fails naming both numbers rather than packing empty:
an empty `Passages` reads downstream as "not in this corpus" (`09` §4's V2), the wrong
diagnosis for "the budget is too small for even one passage" — the operator needs to raise
the budget or lower chunk size, not be told the corpus has nothing.
"""

from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_kernel.context import Context
from weft_kernel.payload import ExtModel, Failed, Outcome, Produced
from weft_llm.contract import LLM, LLMRole, TokenCounter
from weft_retrieve.payload import Passage, Passages, Ranking

#: The name this packer is registered and selectable under — see `weft_retrieve.register`.
NAME = "repack"


class RepackBudget(ExtModel):
    """What a budgeted packing kept, against what it was offered — repair **R32.3**.

    Rides `Passages.ext`, never a stored node, like `anchor_promote.AnchorPromotion`. Present
    only when `budget_tokens` is set: without a budget nothing was counted.
    """

    __namespace__ = "weft-retrieve-repack"
    __schema_version__ = "1"

    offered: int
    kept: int
    packed_tokens: int
    budget_tokens: int

    produced_by: ClassVar[str] = NAME

    def explained(self) -> str:
        """The one-line sentence `weft_cli.explain.record_lines` prints under `--explain`."""
        return (
            f"packed {self.kept} of {self.offered} passages in "
            f"{self.packed_tokens} of {self.budget_tokens} tokens"
        )


class RepackMethod(StrEnum):
    """The three orderings Wang et al. name (`10` §1.1's `repack` row).

    `Enum`, project rule for a closed vocabulary — an operator's typo in a `with:` block is a
    `ValidationError` naming the valid set, never a silent fall-through to whichever branch a chain
    reached first.
    """

    #: Retrieval order, unchanged — the best hit stays first.
    FORWARD = "forward"
    #: The literal reverse of retrieval order — the best hit ends up last, immediately
    #: before the question. This module's default; see the module docstring for the table.
    REVERSE = "reverse"
    #: Best and second-best at the two ends, worst buried in the middle.
    SIDES = "sides"


class RepackConfig(BaseModel):
    """`Repack`'s `with:` config. Every field has a default, per this pack's own rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    method: RepackMethod = RepackMethod.REVERSE
    #: Keep only the best `top_n` hits, by the order `Ranking.hits` already arrived in,
    #: before `method` arranges them. `None` keeps every hit.
    top_n: int | None = None
    #: The evidence block's token ceiling, counted as `weft_generate.cited_answer` renders
    #: it. Applied after `top_n`, before `method`. `None` packs every kept hit, uncounted.
    budget_tokens: int | None = Field(default=None, ge=1)
    #: The `[llm.roles]` role whose model will read the packed context — `cited_answer`
    #: asks `generate` by default, so that is this field's default too. Only resolved when
    #: `budget_tokens` is set.
    role: Annotated[str, LLMRole()] = "generate"


def _forward(hits: Sequence[Passage]) -> Sequence[Passage]:
    """Unchanged — the identity ordering.

    Unchanged — the identity ordering, named so it can be selected rather than merely
    achieved by omitting a `ContextPacker` a document still needs one of.
    """
    return hits


def _reverse(hits: Sequence[Passage]) -> Sequence[Passage]:
    """Worst first, best last — the module docstring's Table 11 winner."""
    return tuple(reversed(hits))


def _sides(hits: Sequence[Passage]) -> Sequence[Passage]:
    """Keep even positions at the front and reversed odd positions at the back.

    Even retrieval-order positions kept at the front, odd positions reversed at the back —
    see the module docstring for why this, and not a best/worst zip-interleave, is what
    Wang et al.'s name is attached to.
    """
    front = hits[0::2]
    back = tuple(reversed(hits[1::2]))
    return (*front, *back)


#: One mapping, not a chain: the enum member selects its own function, so a fourth method
#: is one function and one entry here — never a new branch to remember to add.
_METHODS: Mapping[RepackMethod, Callable[[Sequence[Passage]], Sequence[Passage]]] = {
    RepackMethod.FORWARD: _forward,
    RepackMethod.REVERSE: _reverse,
    RepackMethod.SIDES: _sides,
}


class Repack:
    """Orders, truncates and labels one ranking's hits.

    Satisfies `contract.ContextPacker` structurally.

    `cost_bound = (0, 0)`: counting a rendered block against a budget is local arithmetic
    over a number a `TokenCounter` already resolved, not a model call. It resolves no
    service and calls no model *when no budget is set* — with one, it resolves `LLM` to
    count, the same claim `weft_retrieve.fusion.SingleList` and `ReciprocalRankFusion` make
    about the arity-reducing position one seam earlier.
    """

    config_model: ClassVar[type[RepackConfig]] = RepackConfig
    cost_bound: ClassVar[tuple[int, int]] = (0, 0)

    def __init__(self, config: RepackConfig | None = None) -> None:
        self._config = config if config is not None else RepackConfig()

    async def run(self, payload: Ranking, ctx: Context) -> Outcome[Passages]:
        """Truncate to `top_n`, apply the budget, arrange by `method`, label by final position.

        **The emptiness rule** — no hits at all packs to empty `Passages`, with no method
        applied and nothing computed: the identical case every other stage in this module
        handles, and for the identical reason (`weft_retrieve.contract`'s own emptiness
        rule; `09` §4's V2 requires the engine to be able to answer "not in this corpus").
        """
        if not payload.hits:
            return Produced(
                value=Passages(
                    origin=payload.origin, contributors=payload.contributors, ext=payload.ext
                )
            )

        kept = (
            payload.hits[: self._config.top_n] if self._config.top_n is not None else payload.hits
        )
        ext = payload.ext
        if self._config.budget_tokens is not None:
            budgeted = await self._within_budget(kept, self._config.budget_tokens, ctx)
            if isinstance(budgeted, Failed):
                return budgeted
            offered = len(kept)
            kept, packed_tokens = budgeted
            record = RepackBudget(
                offered=offered,
                kept=len(kept),
                packed_tokens=packed_tokens,
                budget_tokens=self._config.budget_tokens,
            )
            ext = {**ext, RepackBudget.__namespace__: record}
        ranked = tuple(
            passage.model_copy(update={"rank": position}) for position, passage in enumerate(kept)
        )
        ordered = _METHODS[self._config.method](ranked)
        passages = tuple(
            Passage(
                scored=passage.scored,
                rank=passage.rank,
                retrieved_by=passage.retrieved_by,
                label=str(position + 1),
            )
            for position, passage in enumerate(ordered)
        )
        return Produced(
            value=Passages(
                origin=payload.origin,
                passages=passages,
                contributors=payload.contributors,
                ext=ext,
            )
        )

    async def _within_budget(
        self, kept: Sequence[Passage], budget: int, ctx: Context
    ) -> tuple[tuple[Passage, ...], int] | Failed:
        """The longest ranking-order prefix of `kept` that fits `budget`.

        The longest ranking-order prefix of `kept` whose rendered block fits `budget`, and
        that block's token count.

        Renders each candidate prefix exactly as `weft_generate.cited_answer._offer` renders
        the final evidence block for labels `1..k` — the count this stage acts on has to be
        the count the model that reads the context will actually see. `TokenCountUnavailableError`
        is not caught: `weft_llm.client.LLMClient.count_tokens` raising it is the same refusal
        this module's docstring insists on elsewhere — no character estimate standing in for a
        count nothing could produce.
        """
        llm = ctx.require(LLM)
        if not isinstance(llm, TokenCounter):
            return Failed(
                reason=(
                    f"'{NAME}' was given a token budget for the '{self._config.role}' role, "
                    f"but the resolved LLM service does not satisfy {TokenCounter.__name__} "
                    "and cannot count tokens."
                )
            )
        selected: list[Passage] = []
        packed_tokens = 0
        for passage in kept:
            candidate = (*selected, passage)
            text = "\n\n".join(f"[{i + 1}] {p.node.content}" for i, p in enumerate(candidate))
            count = await llm.count_tokens(self._config.role, text)
            if count > budget:
                if not selected:
                    return Failed(
                        reason=(
                            f"'{NAME}': the best passage alone counts {count} tokens against a "
                            f"budget of {budget} tokens — raise budget_tokens or lower chunk "
                            "size."
                        )
                    )
                break
            selected.append(passage)
            packed_tokens = count
        return tuple(selected), packed_tokens
