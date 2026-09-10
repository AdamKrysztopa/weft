"""`llm-facts` — a chunk's facts and mentions become nodes, once. Ledger **11.7**.

Mirrors `packages/weft-rag/src/weft_kg/extraction.py`, `weft_kg/prompts.py` and the three ext
models `weft_kg/payload.py` gained with them.

**The name, settled before the code through `paper-to-plugin` and `10` §2.1.** There is no paper:
extracting subject–predicate–object triples with a language model is ordinary practice, and `10` §5
records the absence rather than inventing a provenance. So the name states the mechanism (rule 2)
and is qualified against the sibling this pack already ships (rule 6) — `cooccurrence-graph`
produces the same *shape* with no model at all, so an unqualified `facts` would let the first of
two siblings seize the namespace. `10` §2.1 rule 6's own worked example is `llm-rerank`, which is
this same qualifier doing this same job one contract over. None of `10` §4's reserved graph names
is taken.

**The `LLM` is a stub and the cascade is real** — `tests/unit/weft_retrieve/test_rerank.py`'s own
reason, unchanged: `weft_prompts.cascade.execute` is the one path a technique in this tree takes to
a typed answer, and stubbing it out would leave this plugin's reading of that answer untested
against the shape the cascade actually returns. The stub sits at `weft_llm.contract.LLM`, exactly
where `weft_cli.run_services.build_index_services` puts a real client.

**Why the cascade rather than `Prompts.render` plus a parser.** `build_index_services` deliberately
publishes no `StageLookup` on the ingest path — *"an ingest stage able to reach them would be an
ingest plugin depending on the query path"* — so this stage cannot resolve a `Prompt` by name the
way `llm-rerank` does, and it constructs its own registered prompt class instead. That buys the
three tiers, which is what makes a triple extractor work on the offline `scripted` provider and on
a vendor that checks a JSON schema itself. It costs one thing, stated here so nobody discovers it:
a `[plugins]` pin on `extract-facts` changes what `weft plugins list` shows and does not change
what this stage asks. `weft_kg.extraction`'s own docstring names the seam that would close it.

**Every drop is counted under its own reason, and there is no total anywhere.** `11.7`'s line —
*counted per reason, never summed*. `ExtractionTally` therefore carries one entry per reason and no
sum field, refuses a repeated reason, and asserts `kept + every count == candidates`, which is what
makes *"every dropped candidate is counted"* a property of the type rather than a claim about the
loop. The donor this filter comes from skipped a malformed row silently and counted five distinct
rules as one number; both are repaired here and `test_a_row_with_a_blank_field_is_counted` is the
first of them.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest
from pydantic import ValidationError

from weft_cli.run_services import class_provides
from weft_index.contract import Expander
from weft_kernel.context import Context, ServiceRegistry
from weft_kernel.payload import (
    MediaType,
    Node,
    NothingToProduce,
    Outcome,
    Produced,
    SourceId,
)
from weft_kg.extraction import NAME, LlmFactExtractor, LlmFactsConfig
from weft_kg.payload import DropReason, ExtractedFact, ExtractionTally, MentionedEntity
from weft_kg.schema import load_schema
from weft_kg.store import GraphSettings
from weft_llm.contract import LLM
from weft_llm.payload import Completion, Rendered

_FACT_KEYS = ("source", "source_type", "predicate", "target", "target_type")


def _reply(*facts: tuple[str, str, str, str, str]) -> str:
    """The JSON a model answers tier 2 with — one object, `facts`, exactly the five keys."""
    return json.dumps({"facts": [dict(zip(_FACT_KEYS, fact, strict=True)) for fact in facts]})


class _StubLLM:
    """An `LLM` answering tier 2 of the cascade from a script keyed by what it was shown.

    `native_structured_available` is `False`, so tier 1 is skipped structurally rather than by a
    flag — the same derived-capability check a real provider is subject to. Copied in shape from
    `tests/unit/weft_retrieve/test_rerank.py`'s own stub, which is the tree's existing double for
    a technique that goes through the cascade.

    Keyed by a marker found in the conversation rather than by call index, because this plugin
    fans out with `asyncio.gather` and the order calls arrive in is not a fact any test may
    depend on.
    """

    def __init__(self, replies: Mapping[str, str], *, fallback: str = "") -> None:
        self._replies = replies
        self._fallback = fallback if fallback else _reply()
        self.calls = 0
        #: Everything the last call actually put on the wire — `11.11` asserts that an active
        #: schema reaches the model rather than only the filter, which is `L9.79`'s rule for a
        #: value whose whole job is to travel from configuration to a call.
        self.shown = ""

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del role, ctx
        self.calls += 1
        shown = "\n".join(message.content for message in rendered.conversation.messages)
        self.shown = shown
        for marker, reply in self._replies.items():
            if marker in shown:
                return Produced(value=Completion(text=reply, model="stub-model"))
        return Produced(value=Completion(text=self._fallback, model="stub-model"))

    async def close(self) -> None: ...


class _ConcurrencyWatchingLLM:
    """An `LLM` recording the high-water mark of calls in flight at once.

    The assertion is about *concurrency*, not call count: an unbounded `gather` and a capped one
    make the same number of calls, and only the peak overlap tells them apart. Copied in shape
    from `tests/unit/weft_index/test_hypothetical_questions.py`, which is the tree's existing
    double for exactly this question one contract over.
    """

    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0

    async def native_structured_available(self, role: str) -> bool:
        del role
        return False

    async def complete_structured(
        self, rendered: Rendered, schema: Mapping[str, object], *, role: str, ctx: Context
    ) -> Outcome[Completion]:
        raise AssertionError("tier 1 is unavailable on this stub and must not be reached")

    async def complete(self, rendered: Rendered, *, role: str, ctx: Context) -> Outcome[Completion]:
        del rendered, role, ctx
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        # One real suspension point, so every coroutine `gather` started actually overlaps.
        # Without it the calls run to completion one after another and the peak reads 1 whatever
        # the cap said — a test that passes for the wrong reason.
        await asyncio.sleep(0)
        self.in_flight -= 1
        return Produced(
            value=Completion(
                text=_reply(("Chucri", "person", "wrote", "adRAP", "method")), model="stub-model"
            )
        )

    async def close(self) -> None: ...


def _ctx(llm: object) -> Context:
    services = ServiceRegistry()
    services.add(LLM, llm)
    return Context(
        tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en", services=services
    )


def _node(content: str) -> Node:
    return Node.synthetic(
        content=content,
        media_type=MediaType.TEXT,
        reason="weft_kg's own fact-extraction test",
        sources=frozenset({SourceId("doc-a")}),
    )


def _derived(outcome: Outcome[Sequence[Node]], kind: type) -> tuple[Node, ...]:
    assert isinstance(outcome, Produced)
    return tuple(node for node in outcome.value if node.ext_as(kind) is not None)


def _tally_of(outcome: Outcome[Sequence[Node]]) -> ExtractionTally:
    """The one tally every derived node in the run carries — asserted identical across them.

    Read through the nodes rather than off the plugin, because *the tally reaches a reader* is
    the property, and a tally computed correctly and attached to nothing is the failure this
    helper would otherwise hide.
    """
    assert isinstance(outcome, Produced)
    tallies = [
        found for node in outcome.value if (found := node.ext_as(ExtractionTally)) is not None
    ]
    assert tallies, "no node in the output carries the run's tally"
    assert all(found == tallies[0] for found in tallies), (
        "two derived nodes disagree about the run's own tally"
    )
    return tallies[0]


async def test_a_chunk_s_facts_become_nodes_derived_from_it() -> None:
    """The happy path, and the sentence `11.7` makes true: extraction is paid once, as nodes.

    Asserted on `lineage.parents` rather than on the count, because *derived from the chunk* is
    what makes a fact reachable by a cascade delete and citable back to a passage; a fact node
    with the wrong parent is a fact that outlives the document it came from.
    """
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP and Azouz reviewed it.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Azouz", "person", "reviewed", "adRAP", "method"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    facts = _derived(outcome, ExtractedFact)
    assert {found.content for found in facts} == {"Chucri wrote adRAP", "Azouz reviewed adRAP"}
    assert all(found.lineage.parents == (node.id,) for found in facts)
    assert all(found.lineage.sources == node.lineage.sources for found in facts)


async def test_the_fact_a_node_carries_is_the_triple_and_both_its_types() -> None:
    """The ext model is the machine-readable half; `content` is the embeddable one.

    `GraphStore.add` derives entity and relation rows from this model, so a fact whose triple
    lived only in the rendered `content` would be a fact no traversal could ever walk.
    """
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    [derived] = _derived(outcome, ExtractedFact)
    fact = derived.ext_as(ExtractedFact)
    assert fact is not None
    assert (fact.source, fact.source_type) == ("Chucri", "person")
    assert fact.predicate == "wrote"
    assert (fact.target, fact.target_type) == ("adRAP", "method")


async def test_every_entity_a_kept_fact_names_becomes_one_mention_node() -> None:
    """Mentions are nodes too, and one per distinct name — `11.8` cascades its entity rows from
    these node ids, so a name mentioned twice in one chunk must not become two anchors.
    """
    # Arrange — `adRAP` is named by both facts, `Chucri` and `Azouz` by one each.
    node = _node("chunk-a: Chucri wrote adRAP and Azouz reviewed it.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Azouz", "person", "reviewed", "adRAP", "method"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    mentions = _derived(outcome, MentionedEntity)
    assert {found.content for found in mentions} == {"Chucri", "Azouz", "adRAP"}
    assert all(found.lineage.parents == (node.id,) for found in mentions)


async def test_a_mention_node_carries_the_type_the_fact_gave_it() -> None:
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    typed = {
        found.name: found.entity_type
        for node_found in _derived(outcome, MentionedEntity)
        if (found := node_found.ext_as(MentionedEntity)) is not None
    }
    assert typed == {"Chucri": "person", "adRAP": "method"}


async def test_the_chunk_itself_comes_back_unchanged() -> None:
    """`Expander`'s own contrast with `Chunker` and `Enhancer`: every node handed in continues,
    unchanged, and new nodes are added beside it.

    The tally is asserted absent from the chunk for the same reason: attaching ext to the payload
    is what defines an `Enhancer`, and a stage that did both would blur the one distinction that
    contract's docstring exists to draw.
    """
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    [returned] = [found for found in outcome.value if found.id == node.id]
    assert returned.content == node.content
    assert returned.ext == node.ext
    assert returned.ext_as(ExtractionTally) is None


async def test_one_model_call_per_node_never_one_for_the_batch() -> None:
    """`hypothetical-questions`' own argument, and it applies with more force here: batching
    chunks into one numbered prompt makes the model's attention to any one passage a function of
    how many chunks happened to land in this run.
    """
    # Arrange
    nodes = [_node(f"chunk-{index}: Chucri wrote adRAP.") for index in range(3)]
    llm = _StubLLM({}, fallback=_reply(("Chucri", "person", "wrote", "adRAP", "method")))

    # Act
    await LlmFactExtractor().run(nodes, _ctx(llm))

    # Assert — tier 1 is unavailable on the stub, so tier 2 is exactly one call per node.
    assert llm.calls == 3


async def test_no_more_than_max_concurrent_nodes_are_in_flight_at_once() -> None:
    """The cap `11.7` names, taking the field name task 8.7 gave `raptor` and
    `hypothetical-questions` — what a provider tolerates is an operator's fact, and three stages
    fanning out against one configured provider should not disagree about it by accident.
    """
    # Arrange — twenty nodes, a cap of three.
    llm = _ConcurrencyWatchingLLM()
    nodes = [_node(f"chunk-{index}: Chucri wrote adRAP.") for index in range(20)]

    # Act
    outcome = await LlmFactExtractor(LlmFactsConfig(max_concurrent_nodes=3)).run(nodes, _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert llm.peak <= 3


async def test_the_cap_is_what_bounds_it_rather_than_the_batch_being_small() -> None:
    """The non-vacuity half: with the cap raised, the same double must report a peak above the
    previous cap — otherwise the assertion above holds for a plugin with no cap at all.
    """
    # Arrange
    llm = _ConcurrencyWatchingLLM()
    nodes = [_node(f"chunk-{index}: Chucri wrote adRAP.") for index in range(20)]

    # Act
    await LlmFactExtractor(LlmFactsConfig(max_concurrent_nodes=10)).run(nodes, _ctx(llm))

    # Assert
    assert llm.peak > 3


async def test_a_candidate_naming_a_non_atomic_entity_is_dropped_under_its_own_rule() -> None:
    """The filter's verdict reaches the tally as *which rule fired*, never as one number.

    Two candidates, dropped by two different rules, so a tally that folded them together would
    fail here rather than in a corpus six months on.
    """
    # Arrange
    node = _node("chunk-a: mixed candidates.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Section II", "section", "describes", "adRAP", "method"),
                ("Chucri", "person", "cites", "Smith et al.", "work"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    tally = _tally_of(outcome)
    assert {entry.reason: entry.count for entry in tally.dropped} == {
        DropReason.DOCUMENT_REFERENCE: 1,
        DropReason.CITATION: 1,
    }
    assert len(_derived(outcome, ExtractedFact)) == 1


async def test_a_row_with_a_blank_field_is_counted_rather_than_skipped_silently() -> None:
    """The donor's own gap, repaired here.

    That module's parser skips a row missing a field and its comment says so — *"skip silently
    (not counted as dropped)"*. A candidate that vanishes without a count is indistinguishable
    from one the model never produced, so an operator reading a thin graph cannot tell a quiet
    model from a rejecting filter. `11.7`'s line is *every* dropped candidate.
    """
    # Arrange
    node = _node("chunk-a: one good, one blank.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Azouz", "person", "", "adRAP", "method"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    tally = _tally_of(outcome)
    assert {entry.reason: entry.count for entry in tally.dropped} == {DropReason.INCOMPLETE_ROW: 1}


async def test_the_same_triple_twice_in_one_chunk_is_one_node_and_one_counted_drop() -> None:
    """A repeated triple would derive the same node id twice — same content, same parent, and a
    duplicate in the batch handed to the store. Counted rather than silently collapsed, because
    a model repeating itself is a fact about the extraction worth seeing.
    """
    # Arrange
    node = _node("chunk-a: said twice.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Chucri", "person", "wrote", "adRAP", "method"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    assert len(_derived(outcome, ExtractedFact)) == 1
    tally = _tally_of(outcome)
    assert {entry.reason: entry.count for entry in tally.dropped} == {DropReason.DUPLICATE: 1}


async def test_candidates_past_the_per_node_limit_are_counted_rather_than_truncated_quietly() -> (
    None
):
    """The limit is asked for in the prompt and enforced here, because a prompt is a request.

    `hypothetical-questions` truncates silently; this stage may not, for the same reason the
    blank row may not — `11.7`'s line covers every dropped candidate, including the ones this
    plugin's own configuration dropped.
    """
    # Arrange
    node = _node("chunk-a: three facts, room for two.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Azouz", "person", "reviewed", "adRAP", "method"),
                ("Ott", "person", "funded", "adRAP", "method"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor(LlmFactsConfig(max_facts_per_node=2)).run([node], _ctx(llm))

    # Assert
    assert len(_derived(outcome, ExtractedFact)) == 2
    tally = _tally_of(outcome)
    assert {entry.reason: entry.count for entry in tally.dropped} == {DropReason.OVER_LIMIT: 1}


async def test_the_tally_accounts_for_every_candidate_the_model_returned() -> None:
    """*Every dropped candidate is counted* made a property of the type rather than of the loop.

    `kept` plus every reason's count equals `candidates`, refused at validation — so a rule
    added later that forgets to count fails at construction rather than producing a tally that
    is quietly short.
    """
    # Arrange
    node = _node("chunk-a: two kept, two dropped.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("Azouz", "person", "reviewed", "adRAP", "method"),
                ("Table 1", "table", "shows", "adRAP", "method"),
                ("Chucri", "person", "cites", "[12]", "work"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    tally = _tally_of(outcome)
    assert tally.candidates == 4
    assert tally.kept == 2
    assert tally.kept + sum(entry.count for entry in tally.dropped) == tally.candidates


def test_the_tally_carries_no_total_and_refuses_a_repeated_reason() -> None:
    """*Never summed*, enforced twice: there is no field to hold a total, and two entries under
    one reason — which is how a total sneaks back in — is a validation failure.
    """
    # Assert — no field whose name would invite a reader to treat it as the answer.
    assert set(ExtractionTally.model_fields) == {"candidates", "kept", "dropped"}

    # Act / Assert
    with pytest.raises(ValidationError, match="reason"):
        ExtractionTally.model_validate(
            {
                "candidates": 2,
                "kept": 0,
                "dropped": [
                    {"reason": DropReason.CITATION.value, "count": 1},
                    {"reason": DropReason.CITATION.value, "count": 1},
                ],
            }
        )


async def test_a_chunk_that_kept_nothing_still_has_its_drops_in_the_run_s_tally() -> None:
    """Why the tally is the run's rather than the chunk's — `RaptorFacts.clusters_found`'s own
    precedent, and the hole it closes.

    A chunk whose every candidate was dropped derives no node, so a per-chunk tally would have
    nowhere to ride and those drops would vanish. Carried on every node the *run* derived, they
    reach a reader through whichever chunk did keep something.
    """
    # Arrange
    kept = _node("chunk-a: one good fact.")
    dropped = _node("chunk-b: nothing but furniture.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method")),
            "chunk-b": _reply(("Table 1", "table", "shows", "Section II", "section")),
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([kept, dropped], _ctx(llm))

    # Assert — `chunk-b` derived nothing, and its drop is in the tally `chunk-a`'s fact carries.
    assert isinstance(outcome, Produced)
    assert all(found.lineage.parents in ((), (kept.id,)) for found in outcome.value)
    tally = _tally_of(outcome)
    assert tally.candidates == 2
    assert tally.kept == 1
    assert {entry.reason: entry.count for entry in tally.dropped} == {
        DropReason.DOCUMENT_REFERENCE: 1
    }


async def test_a_node_whose_completion_could_not_be_used_stays_in_the_output_unchanged() -> None:
    """`Expander`'s stated posture, shared with `raptor` and `hypothetical-questions`: degrade,
    never fail the run. A model in a bad mood is not an operator's configuration mistake.
    """
    # Arrange — prose the cascade cannot rescue into the output model, on one of two nodes.
    good = _node("chunk-a: one good fact.")
    bad = _node("chunk-b: the model declines.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method")),
            "chunk-b": "I would rather not answer that.",
        }
    )

    # Act
    outcome = await LlmFactExtractor().run([good, bad], _ctx(llm))

    # Assert
    assert isinstance(outcome, Produced)
    assert {found.id for found in outcome.value} >= {good.id, bad.id}
    assert len(_derived(outcome, ExtractedFact)) == 1


async def test_an_empty_batch_produces_nothing_and_calls_no_model() -> None:
    """The ambiguous-empty rule every contract in this tree documents — and the floor under the
    cost of this stage, which is the only one in `weft_kg` that spends money.
    """
    # Arrange
    llm = _StubLLM({})

    # Act
    outcome = await LlmFactExtractor().run([], _ctx(llm))

    # Assert
    assert isinstance(outcome, NothingToProduce)
    assert llm.calls == 0


def test_the_extractor_satisfies_the_expander_contract() -> None:
    """Structural, on the class — the same question `weft_kernel.resolution.resolve` asks of a
    document's `use:` name, through `class_provides`, which is the tree's own wrapper (`L11.17`).
    """
    # Assert
    assert class_provides(LlmFactExtractor, Expander)
    assert NAME == "llm-facts"


def test_no_ext_model_this_stage_writes_carries_a_field_named_technique() -> None:
    """`11.1`'s constraint, and this is the task it was written for.

    `weft_generate.representation.citable_nodes` cites a single-parent node carrying an ext model
    with a `technique: str` attribute **as its parent**. Every node this stage derives has exactly
    one parent, so a field of that name on any of these three would make every fact cite the chunk
    it came from instead of itself — and nothing would report it.
    """
    # Assert
    for model in (ExtractedFact, MentionedEntity, ExtractionTally):
        assert "technique" not in model.model_fields


@pytest.mark.parametrize(
    "field", ["max_facts_per_node", "max_concurrent_nodes", "max_entity_words"]
)
@pytest.mark.parametrize("bad", [0, -1])
def test_a_count_below_one_is_refused(field: str, bad: int) -> None:
    """A loud refusal, not a silent clamp — every one of these three can only mean a mistake, and
    a stage that quietly repaired it would produce an empty graph nobody could diagnose.
    """
    # Act / Assert
    with pytest.raises(ValidationError):
        LlmFactsConfig.model_validate({field: bad})


def test_the_config_refuses_an_unknown_field() -> None:
    # Act / Assert
    with pytest.raises(ValidationError):
        LlmFactsConfig.model_validate({"bogus": "x"})


# --- ledger task 11.11: the third layer — constrain the ask, verify the answer ---
#
# `11.7` filters what a model returns on *shape* — a name that is a clause, an equation, a
# citation. A curated schema filters it on *structure*: an operator has said which arrangements of
# which types this corpus admits, and a triple outside that is dropped and counted, never quietly
# kept. Both halves are here because either alone is weaker than it looks — constraining the prompt
# without verifying the answer trusts the model, and verifying without constraining spends a call
# to throw most of it away.
#
# **The honest note the ledger line asks for, carried into the tests rather than only the prose**:
# the prior art's only evidence that this layer was live came from a stubbed provider in its own
# test suite. So does this — `_StubAdjudicator`'s siblings above answer from a script. What that
# proves is that *this pack* drops and counts correctly; what it does not prove is that a real
# vendor's output is improved by the constraint. `10`'s row says so where an operator reads it.


_SCHEMA_TOML = "\n".join(
    [
        'name = "papers"',
        "",
        "[[relations]]",
        'source_type = "person"',
        'predicate = "wrote"',
        'target_type = "method"',
        "",
    ]
)


def _settings_with_schema(tmp_path: Path) -> GraphSettings:
    path = tmp_path / "papers.toml"
    path.write_text(_SCHEMA_TOML, encoding="utf-8")
    return GraphSettings(schema_file=str(path))


async def test_a_fact_outside_the_active_schema_is_dropped_and_counted(
    tmp_path: Path,
) -> None:
    """The arrangement case, which is why the schema is rules rather than two word lists:
    `adRAP wrote Chucri` uses only types and a predicate the operator approved, and says
    something impossible. It is dropped under its own reason and the tally says so.
    """
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM(
        {
            "chunk-a": _reply(
                ("Chucri", "person", "wrote", "adRAP", "method"),
                ("adRAP", "method", "wrote", "Chucri", "person"),
            )
        }
    )

    # Act
    outcome = await LlmFactExtractor(settings=_settings_with_schema(tmp_path)).run(
        [node], _ctx(llm)
    )

    # Assert
    facts = _derived(outcome, ExtractedFact)
    assert {found.content for found in facts} == {"Chucri wrote adRAP"}
    tally = _tally_of(outcome)
    assert dict((entry.reason, entry.count) for entry in tally.dropped) == {
        DropReason.OFF_SCHEMA: 1
    }


async def test_every_kept_fact_carries_the_schema_it_was_extracted_under(
    tmp_path: Path,
) -> None:
    """The task line's own clause. Read off the fact rather than off a run record, because
    `weft graph show` answers *which schemas does this corpus hold* from the corpus, and a
    history kept anywhere else is a history the next operator's checkout does not have.
    """
    # Arrange
    settings = _settings_with_schema(tmp_path)
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    outcome = await LlmFactExtractor(settings=settings).run([node], _ctx(llm))

    # Assert — the identity, not the name: two schemas an operator called `papers` a month apart
    # are one name and two constraints, and the fact has to say which one it survived.
    [fact] = [
        found for node in _derived(outcome, ExtractedFact) if (found := node.ext_as(ExtractedFact))
    ]
    assert fact.schema_id == load_schema(Path(settings.schema_file)).identity


async def test_a_fact_extracted_with_no_active_schema_says_so_rather_than_guessing(
    tmp_path: Path,
) -> None:
    """The default, and the state most corpora are in. An empty identity means *extracted under
    no schema*, which `weft graph show` reports as its own group — not as belonging to whichever
    schema happens to be active when somebody later asks.
    """
    # Arrange
    del tmp_path
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    outcome = await LlmFactExtractor().run([node], _ctx(llm))

    # Assert
    [fact] = [
        found for node in _derived(outcome, ExtractedFact) if (found := node.ext_as(ExtractedFact))
    ]
    assert fact.schema_id == ""


async def test_the_active_schema_reaches_the_model_as_well_as_the_filter(
    tmp_path: Path,
) -> None:
    """**Constrain and verify, not verify alone.** Dropping off-schema facts after the fact is a
    filter; telling the model what the corpus admits is what makes most of the call useful. Both,
    because either alone is weaker — and this asserts the first half actually reaches the wire,
    which is `L9.79`'s rule for a value whose whole job is to travel.
    """
    # Arrange
    node = _node("chunk-a: Chucri wrote adRAP.")
    llm = _StubLLM({"chunk-a": _reply(("Chucri", "person", "wrote", "adRAP", "method"))})

    # Act
    await LlmFactExtractor(settings=_settings_with_schema(tmp_path)).run([node], _ctx(llm))

    # Assert
    assert "wrote" in llm.shown
    assert "person" in llm.shown
