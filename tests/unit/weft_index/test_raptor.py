"""Unit tests for `weft_index.raptor`.

Mirrors `packages/weft-rag/src/weft_index/raptor.py`. Ledger **2.32**: "a query too
broad for any one chunk is answerable, because summaries of clustered chunks are
themselves retrievable nodes, and a summary that cannot be produced degrades the tree
rather than failing the run." Covers the happy path (four nodes cluster by embedding
similarity into one summarisable group and one singleton, the singleton left unsummarised),
the degrade edge case (two clusters form, one cluster's completion fails and produces no
summary while its sibling cluster's summary is unaffected — the tree is shallower there,
never an exception), the error case (an unmapped `prompt:` name is a configuration mistake
and propagates rather than degrading), an empty batch, and a drive through
`weft_kernel.seam.wrap`.

**`Prompts` is a stub and `SummarizeClusterPrompt.render` is real**, the same split
`tests/unit/weft_index/test_hypothetical_questions.py` takes for `generate-questions`.
**`Embedder` is a stub keyed by node content** — `tests/unit/weft_retrieve/test_routing.py`'s
own `_StubEmbedder` shape, enough to make clustering deterministic without a real model.
"""

import asyncio
import math
import re
from collections.abc import Mapping, Sequence

import pytest

from weft_embed.contract import Embedder
from weft_index.contract import Expander
from weft_index.payload import RaptorFacts, Representation
from weft_index.prompts import SUMMARIZE_CLUSTER_NAME, SummarizeClusterPrompt
from weft_index.raptor import NAME, RaptorConfig, RaptorSummarizer
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import (
    Failed,
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
    Vector,
)
from weft_kernel.seam import wrap
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered
from weft_prompts.contract import Prompts

_SOURCE = SourceId("doc-1")

# Two tight pairs, far apart from each other — `A`/`B` and `C`/`D` each cluster with
# themselves (cosine ~1) and not with the other pair (cosine ~0), deterministically, at the
# default `similarity_threshold=0.75`.
_A = Vector(values=(1.0, 0.0))
_B = Vector(values=(0.9, 0.1))
_C = Vector(values=(0.0, 1.0))
_D = Vector(values=(0.0, 0.9))


#: A rendered conversation carries the template around the cluster text, so a cap on the
#: cluster is not a cap on the whole prompt. This is the slack that template is allowed.
_PROMPT_OVERHEAD_ALLOWANCE = 2000


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="test fixture",
        sources=frozenset({_SOURCE}),
    )


class _StubEmbedder:
    """An `Embedder` answering from a fixed content-to-vector table — `test_routing.py`'s
    own `_StubEmbedder`, one field over."""

    def __init__(self, vectors: Mapping[str, Vector]) -> None:
        self._vectors = vectors

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        del ctx
        return Produced(
            value=[node.with_embedding(self._vectors[node.content]) for node in payload]
        )


class _StubPrompts:
    """A `Prompts` holding this pack's own `summarize-cluster` prompt for real."""

    def __init__(self) -> None:
        self._prompt = SummarizeClusterPrompt()

    async def render(self, name: str, values: object, ctx: Context) -> Outcome[Rendered]:
        if name != SUMMARIZE_CLUSTER_NAME:
            raise KeyError(name)
        return await self._prompt.render(values, ctx)  # type: ignore[arg-type]


class _ScriptedLLM:
    """An `LLM` answering `complete` from a per-call script, keyed by call order."""

    def __init__(self, replies: list[Outcome[Completion]]) -> None:
        self._replies = replies
        self.calls: list[str] = []

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, ctx
        self.calls.append(role)
        return self._replies[len(self.calls) - 1]

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("raptor never asks for structured output")

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("raptor never checks tier 1 availability")

    async def close(self) -> None: ...


class _RefusingLLM:
    """An `LLM` that refuses every request mentioning a given marker and answers the rest.

    Keyed on what the model was *shown* rather than on call order, because neither ordering
    nor call count is stable once summaries are retried and run under a concurrency bound.
    A test that scripts by index is really asserting a scheduling accident.
    """

    def __init__(self, refuse_marker: str) -> None:
        self._marker = refuse_marker
        self.calls = 0

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.calls += 1
        shown = "".join(message.content for message in rendered.conversation.messages)
        if self._marker in shown:
            return Failed(reason="the model declined")
        return _reply("A summary of C and D.")

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("raptor never asks for structured output")

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("raptor never checks tier 1 availability")

    async def close(self) -> None: ...


def _reply(text: str) -> Outcome[Completion]:
    return Produced(value=Completion(text=text, model="stub-model"))


def _ctx(*, embedder: object, llm: object | None = None, prompts: object | None = None) -> Context:
    services = ServiceRegistry()
    services.add(Embedder, embedder)
    services.add(LLM, llm if llm is not None else _ScriptedLLM([]))
    services.add(Prompts, prompts if prompts is not None else _StubPrompts())
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


async def test_a_tight_cluster_is_summarised_and_a_singleton_is_left_alone() -> None:
    # Arrange — A and B cluster tightly; C stands alone, below `min_cluster_size`.
    a, b, c = _node("passage a"), _node("passage b"), _node("passage c")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _B, "passage c": _C})
    llm = _ScriptedLLM([_reply("A summary of A and B.")])
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b, c), _ctx(embedder=embedder, llm=llm))

    # Assert — all three originals survive unchanged, and exactly one summary is derived.
    assert isinstance(outcome, Produced)
    nodes = outcome.value
    assert nodes[0] is a
    assert nodes[1] is b
    assert nodes[2] is c
    derived = [node for node in nodes if node.id not in (a.id, b.id, c.id)]
    assert len(derived) == 1
    summary = derived[0]
    assert summary.content == "A summary of A and B."
    assert summary.embedding is None  # `Expander` derives text; embedding is a later stage
    # **The membership, and then the *canonical* order — not the order they arrived in.**
    # This assertion read `== (a.id, b.id)` until task 10.3, which is the order the two nodes
    # happened to be handed over in and a fact no document ever stated. Sorting the clusterer's
    # input by `Node.id` made a correct repair look like a regression here, which is
    # `phase-step`'s own rule about an incidental literal being a design decision handed to
    # something that has not read the documents. What is asserted now is the pair of facts that
    # *are* specified: which nodes the summary was built from, and that their order is canonical
    # rather than incidental — a node id is a content digest over the parent ids, so a stable
    # order is what makes an index rebuilt from the same corpus the same index.
    assert set(summary.lineage.parents) == {a.id, b.id}
    assert list(summary.lineage.parents) == sorted(summary.lineage.parents)
    assert summary.lineage.sources == frozenset({_SOURCE})
    marker = summary.ext_as(Representation)
    assert marker is not None
    assert marker.technique == NAME


async def test_a_failed_summary_leaves_its_cluster_retrievable_and_its_sibling_unaffected() -> None:
    # Arrange — two summarisable clusters; the first cluster's completion fails outright.
    # Contents are prefixed so the refusal marker survives the retry's own halving — a marker
    # that truncates away would make the second attempt succeed and quietly test nothing.
    a, b, c, d = (
        _node("alpha passage a"),
        _node("alpha passage b"),
        _node("gamma passage c"),
        _node("gamma passage d"),
    )
    embedder = _StubEmbedder(
        {
            "alpha passage a": _A,
            "alpha passage b": _B,
            "gamma passage c": _C,
            "gamma passage d": _D,
        }
    )
    # Refusal is keyed on the cluster's own text, so it holds for the retry too — a single
    # `Failed` no longer degrades a cluster, because the halve-and-retry branch gets a second
    # attempt. What this test is about is a cluster that cannot be summarised *at all*.
    llm = _RefusingLLM(refuse_marker="alph")
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b, c, d), _ctx(embedder=embedder, llm=llm))

    # Assert — never an exception; all four originals are still in the output, and only the
    # cluster whose completion succeeded grew a summary. The tree is shallower over {a, b},
    # not absent, and the run still answers.
    assert isinstance(outcome, Produced)
    nodes = outcome.value
    assert a in nodes
    assert b in nodes
    assert c in nodes
    assert d in nodes
    derived = [node for node in nodes if node.id not in (a.id, b.id, c.id, d.id)]
    assert len(derived) == 1
    assert derived[0].lineage.parents == (c.id, d.id)
    assert not any(node.lineage.parents == (a.id, b.id) for node in nodes)


async def test_an_embedder_outage_fails_the_run_rather_than_degrading_to_unchanged() -> None:
    """A real infrastructure failure (auth error, rate limit, network outage) must not read
    the same as "no cluster met the similarity threshold" — `Produced(value=tuple(payload))`
    for both would make every subsequent `raptor` run silently no-op forever, indistinguishable
    from a corpus with nothing to cluster. See the repair of task 2.32's reviewer findings.
    """

    # Arrange — an `Embedder` that always answers `Failed`, the shape a broken API key or a
    # rate limit takes at `embedder.run`.
    class _BrokenEmbedder:
        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            del payload, ctx
            return Failed(reason="401 unauthorized")

    a, b = _node("passage a"), _node("passage b")
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b), _ctx(embedder=_BrokenEmbedder()))

    # Assert — the embedder's own reason survives, and the run is `Failed`, not `Produced`.
    assert isinstance(outcome, Failed)
    assert "401 unauthorized" in outcome.reason


async def test_an_embedder_with_nothing_to_produce_also_fails_the_run() -> None:
    # Arrange — `NothingToProduce` from the embedder is still an ambient-service problem,
    # not a per-cluster degrade, so it is turned into a `Failed` naming what was discarded.
    class _EmptyEmbedder:
        async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
            del payload, ctx
            return NothingToProduce(reason="embedding backend returned an empty batch")

    a, b = _node("passage a"), _node("passage b")
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b), _ctx(embedder=_EmptyEmbedder()))

    # Assert
    assert isinstance(outcome, Failed)
    assert "embedding backend returned an empty batch" in outcome.reason


async def test_an_empty_batch_is_nothing_to_produce() -> None:
    # Arrange
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((), _ctx(embedder=_StubEmbedder({})))

    # Assert
    assert isinstance(outcome, NothingToProduce)


async def test_an_unmapped_prompt_name_propagates_rather_than_degrading() -> None:
    # Arrange — a `with:` block naming a prompt nobody registered is an operator mistake,
    # not a model failure, so it must not be swallowed into "no summary for this cluster".
    a, b = _node("passage a"), _node("passage b")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _B})
    summarizer = RaptorSummarizer(RaptorConfig(prompt="nonexistent"))

    # Act / Assert
    with pytest.raises(KeyError):
        await summarizer.run((a, b), _ctx(embedder=embedder))


async def test_raptor_runs_through_the_seam() -> None:
    """FF7(b) shape: driven through `weft_kernel.seam.wrap`, not around it — the same
    obligation `tests/unit/weft_index/test_hypothetical_questions.py`'s own seam test
    carries for this pack's first `Expander`.
    """
    # Arrange
    a, b = _node("passage a"), _node("passage b")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _B})
    llm = _ScriptedLLM([_reply("A summary of A and B.")])
    summarizer = RaptorSummarizer()
    assert isinstance(summarizer, Expander)
    sealed = wrap(
        summarizer.run, distribution="weft-index", contract="Expander", plugin=NAME, stage="expand"
    )

    # Act
    outcome = await sealed((a, b), _ctx(embedder=embedder, llm=llm))

    # Assert — the seam adds spans and a guard, never behaviour: two nodes in, one cluster
    # summary derived beside them.
    assert isinstance(outcome, Produced)
    assert len(outcome.value) == 3


class _RecordingLLM:
    """An `LLM` that keeps every rendered conversation, so a test can assert on what the
    model was actually shown rather than only on what came back. `_ScriptedLLM` deliberately
    discards `rendered`; the four behaviours below are all about the request side.
    """

    def __init__(self, replies: list[Outcome[Completion]]) -> None:
        self._replies = replies
        self.shown: list[str] = []
        self.in_flight = 0
        self.peak_in_flight = 0

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # a suspension point, so overlap is observable
            self.shown.append(
                "".join(message.content for message in rendered.conversation.messages)
            )
            index = len(self.shown) - 1
            return self._replies[index] if index < len(self._replies) else _reply("summary")
        finally:
            self.in_flight -= 1


async def test_a_cluster_larger_than_the_cap_is_truncated_before_the_model_sees_it() -> None:
    """An uncapped `_format_cluster` joins every member whole, so one oversized cluster can
    exceed a model's context and take the whole cluster's summary with it.
    """
    # Arrange — two members of 400 characters each against a 100-character cap.
    a, b = _node("a" * 400), _node("b" * 400)
    embedder = _StubEmbedder({"a" * 400: _A, "b" * 400: _B})
    llm = _RecordingLLM([_reply("A summary.")])
    summarizer = RaptorSummarizer(RaptorConfig(max_cluster_chars=100))

    # Act
    outcome = await summarizer.run((a, b), _ctx(embedder=embedder, llm=llm))

    # Assert — the model saw at most the cap, and the summary still came back.
    assert isinstance(outcome, Produced)
    assert len(llm.shown) == 1
    assert len(llm.shown[0]) <= 100 + _PROMPT_OVERHEAD_ALLOWANCE


async def test_a_failed_completion_is_retried_once_with_the_cluster_halved() -> None:
    """The specific branch that made small-context models usable, and the one thing
    `weft_llm.retry` structurally cannot do: it retries the same request, and an overflow
    fails identically every time. `LLMContextLengthError` is classed *permanent* for exactly
    that reason (`weft_llm/errors.py:160`), so halving is the only move left.
    """
    # Arrange — the first attempt fails; the second must be strictly smaller.
    a, b = _node("a" * 200), _node("b" * 200)
    embedder = _StubEmbedder({"a" * 200: _A, "b" * 200: _B})
    llm = _RecordingLLM([Failed(reason="context length exceeded"), _reply("A smaller summary.")])
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b), _ctx(embedder=embedder, llm=llm))

    # Assert — exactly two attempts, the second smaller, and the summary survives.
    assert isinstance(outcome, Produced)
    assert len(llm.shown) == 2
    assert len(llm.shown[1]) < len(llm.shown[0])
    derived = [node for node in outcome.value if node.id not in (a.id, b.id)]
    assert len(derived) == 1
    assert derived[0].content == "A smaller summary."


async def test_a_retry_that_also_fails_degrades_that_cluster_without_a_third_attempt() -> None:
    # Arrange — both attempts fail for the one cluster.
    a, b = _node("passage a"), _node("passage b")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _B})
    llm = _RecordingLLM([Failed(reason="nope"), Failed(reason="still nope")])
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b), _ctx(embedder=embedder, llm=llm))

    # Assert — two attempts, never three, and every cluster degrading is not silence.
    assert len(llm.shown) == 2
    assert isinstance(outcome, Failed)
    assert "1" in outcome.reason


async def test_concurrent_summaries_are_bounded_by_configuration() -> None:
    """A 200-cluster corpus fired 200 concurrent completions at a configured provider. The
    bound is a field rather than a constant because what a provider tolerates is an operator's
    fact, not this plugin's.
    """
    # Arrange — six tight pairs, so six clusters, against a bound of two.
    pairs = [(_node(f"x{i}"), _node(f"y{i}")) for i in range(6)]
    table: dict[str, Vector] = {}
    for index, (first, second) in enumerate(pairs):
        shared = Vector(values=tuple(1.0 if i == index else 0.0 for i in range(6)))
        table[first.content] = shared
        table[second.content] = shared
    nodes = tuple(node for pair in pairs for node in pair)
    embedder = _StubEmbedder(table)
    llm = _RecordingLLM([])
    summarizer = RaptorSummarizer(RaptorConfig(max_concurrent_summaries=2))

    # Act
    outcome = await summarizer.run(nodes, _ctx(embedder=embedder, llm=llm))

    # Assert — all six summarised, never more than two at once.
    assert isinstance(outcome, Produced)
    assert len(llm.shown) == 6
    assert llm.peak_in_flight <= 2


async def test_every_cluster_degrading_fails_rather_than_looking_like_a_complete_run() -> None:
    """The silent failure mode this test closes: if every summary degraded and `run` still
    returned `Produced(payload)`, that result would be byte-identical to the answer for a
    corpus that genuinely had nothing to cluster. Two different facts, one result.
    """
    # Arrange — two clusters, every attempt fails.
    a, b, c, d = _node("passage a"), _node("passage b"), _node("passage c"), _node("passage d")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _A, "passage c": _C, "passage d": _C})
    llm = _RecordingLLM([Failed(reason="no") for _ in range(4)])
    summarizer = RaptorSummarizer()

    # Act
    outcome = await summarizer.run((a, b, c, d), _ctx(embedder=embedder, llm=llm))

    # Assert — a run that produced no summary at all says so.
    assert isinstance(outcome, Failed)
    assert "2" in outcome.reason


# --- Ledger task 10.3 — the same node set yields the same clusters whatever order it arrived in.

#: Seven nodes evenly spaced 20° apart on the unit circle. **The spacing is what makes this a
#: control rather than a decoration.** At the shipped `similarity_threshold=0.75`, neighbours 20°
#: apart (cosine 0.94) and 40° apart (0.766) clear the bar and 60° apart (0.5) does not; with
#: `cluster_size=3` the greedy pass therefore fills a cluster and opens the next one at a boundary
#: that depends entirely on where it started. Walked forwards it groups {0°,20°,40°},
#: {60°,80°,100°} and leaves 120° alone; walked backwards it groups {120°,100°,80°},
#: {60°,40°,20°} and leaves 0° alone. Seven rather than six because six is symmetric under
#: reversal and would have produced the *same* two groups both ways — a control that cannot
#: disagree, which is `docs/lessons.md` L9.58's shape exactly.
_FAN = tuple(
    Vector(values=(math.cos(math.radians(20 * step)), math.sin(math.radians(20 * step))))
    for step in range(7)
)


class _EchoLLM:
    """An `LLM` whose answer is a function of what it was shown, and of nothing else.

    A scripted-by-call-order stub cannot be used here: two runs of the same nodes in two orders
    would be handed replies by index and would agree because the *script* agreed, not because
    the tree did. Echoing the rendered prompt makes the summary's content — and therefore, since
    a node id is a content digest, the summary's id — depend on the cluster's members **and on
    the order they were rendered in**. That is deliberate: 10.3 asks that the same node set
    yield the same clusters, and a tree whose nodes carry different ids for the same membership
    is not the same tree. Fixing the input order without fixing the member order inside a
    cluster would satisfy a membership-only assertion and still rebuild a different index.
    """

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        shown = "".join(message.content for message in rendered.conversation.messages)
        return _reply(f"summary of: {shown}")

    async def complete_structured(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("raptor never asks for structured output")

    async def native_structured_available(self, role: str) -> bool:
        raise AssertionError("raptor never checks tier 1 availability")

    async def close(self) -> None: ...


async def _tree_of(nodes: Sequence[Node]) -> tuple[Node, ...]:
    """The summaries one `raptor` run builds over `nodes`, in the order it returned them."""
    table = {node.content: _FAN[index] for index, node in enumerate(sorted(nodes, key=_fan_key))}
    outcome = await RaptorSummarizer(RaptorConfig(cluster_size=3)).run(
        nodes, _ctx(embedder=_StubEmbedder(table), llm=_EchoLLM())
    )
    assert isinstance(outcome, Produced), outcome
    return tuple(node for node in outcome.value if len(node.lineage.parents) > 1)


def _fan_key(node: Node) -> int:
    """`node`'s position in the fan, read off its own content rather than off its position."""
    return int(node.content.removeprefix("fan-"))


async def test_the_same_nodes_in_a_different_order_build_the_same_tree() -> None:
    """Ledger 10.3. `_cluster_by_similarity` walked its input once in payload order, mutating
    clusters in place, so which cluster a node joined depended on what preceded it — and an
    index rebuilt from the same corpus after a different extraction order was a different tree.
    No paper motivates the greedy pass being order-dependent: all four use order-independent
    clusterers (GMM/EM, k-means, an entropy-minimising partition) and assume it. The repair is
    a stable input order, not the paper's GMM — `raptor.py`'s divergence from UMAP+GMM stands,
    and the least-evidenced component in every paper is not adopted to fix something a stable
    ordering also fixes.
    """
    # Arrange
    forwards = tuple(_node(f"fan-{step}") for step in range(7))
    backwards = tuple(reversed(forwards))

    # Act
    from_forwards = await _tree_of(forwards)
    from_backwards = await _tree_of(backwards)

    # Assert — the control first: these two orderings are genuinely different inputs, and the
    # fixture genuinely exercises the clustering decision rather than degenerating to one
    # cluster or to all singletons.
    assert [node.id for node in forwards] != [node.id for node in backwards]
    assert 1 < len(from_forwards) < len(forwards)

    assert {frozenset(node.lineage.parents) for node in from_forwards} == {
        frozenset(node.lineage.parents) for node in from_backwards
    }, "the same seven nodes grouped differently depending on which end the run started from"
    assert {node.id for node in from_forwards} == {node.id for node in from_backwards}, (
        "the clusters agree and the summary nodes do not, so the two runs built the same "
        "groupings and gave them different ids — a node id is a content digest, and a cluster "
        "rendered members-first-seen produces different content for the same membership. An "
        "index rebuilt from the same corpus must be the same index."
    )


# --- Ledger task 10.2 — no member's content is dropped without the summary recording it.


def _passages_shown(rendered: str) -> list[str]:
    """The member bodies `_format_cluster` actually put in front of the model.

    Read out of the rendered prompt rather than recomputed from the members and the budget.
    Recomputing the even share here would compare `_format_cluster`'s arithmetic against a
    second copy of itself, and a coverage record derived from the same division as the
    truncation cannot disagree with it (`docs/lessons.md` L9.28). What this parses is the
    request that left the plugin.
    """
    block = rendered.split("Passages:\n", 1)[1].split("\n\nWrite one summary", 1)[0]
    return [re.sub(r"^\d+\. ", "", part) for part in block.split("\n\n")]


async def test_a_summary_records_its_cluster_even_when_nothing_was_dropped() -> None:
    """The record exists on every summary, not only on a degraded one.

    A field written only when something went wrong cannot be read as *"nothing went wrong"* —
    its absence would mean that, or that an older `raptor` wrote the node, or that the pack is
    not installed. `10` §1.2's strongest claim is that a summary abstracts its whole cluster,
    and a reader has to be able to check it on the summaries that are fine.
    """
    # Arrange — two short members against the shipped 12,000-character budget.
    a, b = _node("passage a"), _node("passage b")
    embedder = _StubEmbedder({"passage a": _A, "passage b": _B})
    llm = _RecordingLLM([_reply("A summary of A and B.")])

    # Act
    outcome = await RaptorSummarizer().run((a, b), _ctx(embedder=embedder, llm=llm))

    # Assert
    assert isinstance(outcome, Produced)
    summary = next(node for node in outcome.value if len(node.lineage.parents) > 1)
    facts = summary.ext_as(RaptorFacts)
    assert facts is not None, (
        "the summary carries no coverage record at all, so a reader cannot tell a summary that "
        "read its whole cluster from one that read 40% of it — which is the point at which this "
        "plugin makes its strongest claim"
    )
    assert facts.members == 2
    assert facts.members_truncated == 0
    assert facts.characters_held == len(a.content) + len(b.content)
    assert facts.characters_shown == facts.characters_held


async def test_a_summary_that_saw_only_part_of_its_cluster_records_how_much() -> None:
    """The property 10.2 names. `_format_cluster` slices every member to an even share of
    `max_cluster_chars`, so a summary built from 40% of its cluster is byte-identical to one
    built from all of it — the record is what makes the two distinguishable.
    """
    # Arrange — two 400-character members against a 100-character budget.
    a, b = _node("a" * 400), _node("b" * 400)
    embedder = _StubEmbedder({"a" * 400: _A, "b" * 400: _B})
    llm = _RecordingLLM([_reply("A summary.")])

    # Act
    outcome = await RaptorSummarizer(RaptorConfig(max_cluster_chars=100)).run(
        (a, b), _ctx(embedder=embedder, llm=llm)
    )

    # Assert — the record against what the model was actually shown, which is a different
    # source from the record: one is the plugin's own accounting, the other is the request.
    assert isinstance(outcome, Produced)
    summary = next(node for node in outcome.value if len(node.lineage.parents) > 1)
    facts = summary.ext_as(RaptorFacts)
    assert facts is not None
    shown = _passages_shown(llm.shown[0])
    assert facts.characters_shown == sum(len(passage) for passage in shown)
    assert facts.characters_held == 800
    assert facts.characters_shown < facts.characters_held
    assert facts.members_truncated == sum(
        1 for member, passage in zip((a, b), shown, strict=True) if passage != member.content
    )
    assert facts.members_truncated == 2


async def test_the_record_describes_the_request_that_succeeded_not_the_one_that_failed() -> None:
    """The retry halves what was sent, so a record taken from the first attempt would overstate
    what the summary is built on — by exactly the amount the retry gave up.
    """
    # Arrange — the first completion fails, the second is handed half the text.
    a, b = _node("a" * 400), _node("b" * 400)
    embedder = _StubEmbedder({"a" * 400: _A, "b" * 400: _B})
    llm = _RecordingLLM([Failed(reason="too long"), _reply("A summary.")])

    # Act
    outcome = await RaptorSummarizer(RaptorConfig(max_cluster_chars=200)).run(
        (a, b), _ctx(embedder=embedder, llm=llm)
    )

    # Assert
    assert isinstance(outcome, Produced)
    assert len(llm.shown) == 2, "this test needs the retry to have happened"
    summary = next(node for node in outcome.value if len(node.lineage.parents) > 1)
    facts = summary.ext_as(RaptorFacts)
    assert facts is not None
    second = sum(len(passage) for passage in _passages_shown(llm.shown[1]))
    first = sum(len(passage) for passage in _passages_shown(llm.shown[0]))
    assert second < first, "the retry did not actually send less, so this test proves nothing"
    assert facts.characters_shown == second, (
        "the record describes the first, larger request — the one that failed and whose text "
        "the summary is not built on"
    )
