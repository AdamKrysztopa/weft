"""`hypothetical-questions` — the first `Expander`. Task **2.31**.

`docs/build-ledger.md`: "a chunk can be found by a question it answers rather than by the
words it contains, because a generated question is its own retrievable node." `10` §1.2's
own row: doc2query (Rodrigo Nogueira, Wei Yang, Jimmy Lin, Kyunghyun Cho, *Document
Expansion by Query Prediction*, arXiv:1904.08375, 2019) — "at index time, generates the
questions a chunk would answer and indexes them as retrievable nodes" — under the *correct*
citation, per that row's own finding that a plausible-looking wrong paper (HyDE,
arXiv:2212.10496 — a *query-time* technique generating hypothetical *answers*) is what the
reference attached to this *index-time* technique that generates hypothetical *questions*.

**One call per node, run concurrently, never one call for a batch.** `weft_retrieve.
transforms.MultiQuery` batches several *query-path* seeds into one structured cascade call
because a query run is one `QuerySet`, bounded and small, and its own `cost_bound` exists to
be read by a router before the call is made. An index-path `Expander` runs over however many
nodes a chunker just produced — batching them into one numbered prompt would make the
prompt's size, and therefore the model's attention to any one passage, a function of how
many chunks happened to land in this run, which is not a property this task's own design
source asks for. `weft_index.prompts`'s own module docstring records the second reason: it
also keeps this pack off `weft_prompts.cascade` and `weft_retrieve.contract.StageLookup`
entirely, needing only `weft_prompts.contract.Prompts` and `weft_llm.contract.LLM`.

**A node whose questions could not be generated stays in the output, unchanged — degrade,
never fail the run.** `weft_index.contract.Expander`'s own docstring states this as the
contract's rule, shared with task 2.32's `raptor`, and it applies to two distinct failure
shapes the same way: a completion the model declined to give structured shape has no
questions to add (an `Outcome` that is not `Produced`, never an exception), and a completion
that parsed to zero valid lines has none either. Both leave the node itself untouched; only
its own representations are absent. A misconfigured `prompt:` name or an unmapped `role:`
is a different kind of failure — an operator's own document is wrong, not a model in a bad
mood — and propagates as the registry's or `weft_llm.roles.LLMRoles`'s own exception,
aborting the run the way every other plugin in this tree lets a configuration error abort it.
"""

import asyncio
import re
from collections.abc import Sequence
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from weft_index.payload import Representation
from weft_index.prompts import GENERATE_QUESTIONS_NAME, GenerateQuestionsRequest
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_llm.contract import LLM
from weft_prompts.contract import Prompts

#: The name this plugin is registered and selectable under — see `weft_index.register`.
NAME = "hypothetical-questions"

#: Strips a leading list marker a model wrote despite being asked not to — `"1. "`, `"1) "`,
#: `"- "`, `"* "`, `"• "` — so a completion that half-followed instructions still parses.
_LEADING_MARKER = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")


class HypotheticalQuestionsConfig(BaseModel):
    """`hypothetical-questions`'s `with:` config. Every field has a default, per this pack's
    own rule that a Phase 2 pack's settings must be constructible with none supplied.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: How many questions one call is asked to write **per node**. Capped at the number of
    #: distinct, non-empty lines the model actually returns — a model that under-delivers is
    #: not padded, and one that over-delivers is not silently kept in full.
    questions_per_node: int = Field(default=3, ge=1)
    #: How many nodes may have a completion in flight at once. **Task 8.7**, and the last
    #: unbounded fan-out in the tree: `asyncio.gather` over every node in the batch meant a
    #: 700-node corpus fired 700 concurrent completions at whatever provider was configured,
    #: on the first real corpus somebody pointed at it. `raptor` — this plugin's sibling under
    #: the same contract, doing the same thing one payload shape over — grew
    #: `max_concurrent_summaries` for exactly this reason and this one never did, which is
    #: what a rule an author has to remember looks like after one of two authors remembers it.
    #:
    #: A field rather than a constant, and the same default (`8`) as its sibling: what a
    #: provider tolerates is an operator's fact, not this plugin's, and two plugins that fan
    #: out against the same configured provider should not disagree about it by accident.
    max_concurrent_nodes: int = Field(default=8, ge=1)
    prompt: str = Field(default=GENERATE_QUESTIONS_NAME, min_length=1)
    role: str = Field(default="index", min_length=1)


class HypotheticalQuestionGenerator:
    """Derives up to `questions_per_node` question-nodes from every node it is handed.

    Satisfies `weft_index.contract.Expander` structurally. Each derived node is
    `parent.derive(content=question, media_type=MediaType.TEXT)`, so its id is its own
    content digest and its `Lineage` names `parent` — `.phase2-findings.md` §11's
    mechanism, unchanged. `Representation(technique=NAME)` is attached so a citation can
    later resolve past it — see `weft_index.payload.Representation`.
    """

    config_model: ClassVar[type[HypotheticalQuestionsConfig]] = HypotheticalQuestionsConfig

    def __init__(self, config: HypotheticalQuestionsConfig | None = None) -> None:
        self._config = config if config is not None else HypotheticalQuestionsConfig()

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        if not payload:
            return NothingToProduce(reason="no nodes to generate hypothetical questions for")

        prompts = ctx.require(Prompts)
        llm = ctx.require(LLM)
        # Bounded exactly as `weft_index.raptor` bounds its own fan-out — a semaphore held
        # across the whole call, never a chunked `gather` loop: chunking would make the batch
        # run in lockstep waves, so one slow completion would idle every other permit until
        # the wave finished. See `max_concurrent_nodes` for why the bound exists at all.
        limit = asyncio.Semaphore(self._config.max_concurrent_nodes)

        async def _bounded(node: Node) -> Sequence[Node]:
            async with limit:
                return await self._questions_for(node, prompts=prompts, llm=llm, ctx=ctx)

        derived_per_node = await asyncio.gather(*(_bounded(node) for node in payload))
        derived = [child for children in derived_per_node for child in children]
        return Produced(value=(*payload, *derived))

    async def _questions_for(
        self, node: Node, *, prompts: Prompts, llm: LLM, ctx: Context
    ) -> tuple[Node, ...]:
        """This one node's derived question-nodes — `()` when generation degrades, never raised."""
        values = GenerateQuestionsRequest(
            passage=node.content, count=self._config.questions_per_node
        )
        rendered = await prompts.render(self._config.prompt, values, ctx)
        if not isinstance(rendered, Produced):
            return ()
        completion = await llm.complete(rendered.value, role=self._config.role, ctx=ctx)
        if not isinstance(completion, Produced):
            return ()

        questions = _parse_questions(completion.value.text, limit=self._config.questions_per_node)
        return tuple(
            node.derive(content=question, media_type=MediaType.TEXT, ordinal=ordinal).with_ext(
                Representation(technique=NAME)
            )
            for ordinal, question in enumerate(questions)
        )


def _parse_questions(text: str, *, limit: int) -> tuple[str, ...]:
    """One question per line, markers stripped, blanks dropped, duplicates dropped, capped.

    Deduplicated case-insensitively on whitespace-collapsed text — `weft_retrieve.
    transforms.MultiQuery._normalised`'s own reason applies here unchanged: two lines that
    differ only in case or spacing are one question offered twice, not two representations
    worth two separate nodes and two separate embeddings.
    """
    seen: set[str] = set()
    questions: list[str] = []
    for raw_line in text.splitlines():
        line = _LEADING_MARKER.sub("", raw_line).strip()
        if not line:
            continue
        key = " ".join(line.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        questions.append(line)
        if len(questions) >= limit:
            break
    return tuple(questions)
