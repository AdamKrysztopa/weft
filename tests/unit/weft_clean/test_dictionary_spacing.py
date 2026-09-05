"""Unit tests for `weft_clean.dictionary_spacing`.

Mirrors `packages/weft-rag/src/weft_clean/dictionary_spacing.py`. Covers
the happy path (a preposition fused onto the next word is split), the edge
case of a word that merely *looks* fused but is a real word in the exception
set (left alone, diacritics and case folded first), and the error case of a
remainder too short to plausibly be a word on its own (left alone without
even consulting the exception set). Also covers task 1.7's own ordering
claim: `PolishFusedWordFixer` needs nothing `intact` — "can run on clean
text", unlike `weft_clean.hyphenation.HyphenationRepair` and
`weft_clean.table_linearizer.TableLinearizer` — and task 2.35's addition:
it still destroys `Verbatim`, the same honest reason every processor in this
pack does, per `weft_clean.property`'s module docstring.

**`test_run_through_the_runner_leaves_a_node_with_no_language_fact_untouched`
is a repair test.** A review of tasks 1.7/1.8 found `PolishFusedWordFixer`
shipping with no `applies_to` at all, so `weft_kernel.runner`'s documented
default — "a stage that declares no `applies_to` applies to everything" —
applied literally, and this fixer's Polish-only logic ran on every node in a
mixed-language batch, silently mangling English text
(`'The dogma of water conservation'` -> `'The do gma of w ater conservation'`).
The direct `fixer.run(...)` tests above never exercised this, because
`applies_to` is enforced at the seam (`weft_kernel.runner`), never inside
`run()` itself — this file's earlier tests call `run` directly and therefore
prove nothing about routing. This test goes through a real
`weft_kernel.runner.Runner` instead, the only path that evaluates
`applies_to` at all.
"""

import functools
from collections.abc import AsyncIterator, Callable, Sequence

from weft_clean.contract import Cleaner
from weft_clean.dictionary_spacing import PolishFusedWordFixer, PolishFusedWordFixerConfig
from weft_clean.language import Language
from weft_clean.property import Verbatim
from weft_kernel.context import Context
from weft_kernel.payload import MediaType, Node, NothingToProduce, Outcome, Produced
from weft_kernel.payload.property import Property
from weft_kernel.registry import Registry
from weft_kernel.runner import Runner, StageSpec


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _node(content: str) -> Node:
    return Node.synthetic(content=content, media_type=MediaType.TEXT, reason="test fixture")


class _CapturesNodes:
    """Records the batch it is handed — `Runner.run` itself returns only counts.

    `destroys = ()` is not decoration: `Cleaner` publishes a property
    vocabulary, so `weft_kernel.registry` refuses to register any
    implementation that never states it — even a test's own stand-in.
    """

    destroys: tuple[type[Property], ...] = ()

    def __init__(self, captured: list[Sequence[Node]], config: object = None) -> None:
        del config
        self._captured = captured

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        self._captured.append(payload)
        return Produced(value=payload)


def _capture_factory(captured: list[Sequence[Node]]) -> Callable[[object], _CapturesNodes]:
    """Binds `captured` ahead of the `config` argument `Runner.resolve` calls every factory
    with — `functools.partial`, the one shape `weft_kernel.registry.unwrap_factory` also
    knows how to see `destroys` through, unlike an ordinary closure."""
    return functools.partial(_CapturesNodes, captured)


async def test_run_splits_a_preposition_fused_onto_the_next_word() -> None:
    # Arrange — "wcelu" is the extraction artefact for "w celu" ("for the purpose of").
    fixer = PolishFusedWordFixer()
    parent = _node("To jest wcelu testowania.")

    # Act
    outcome: Outcome[Sequence[Node]] = await fixer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "To jest w celu testowania."


async def test_run_leaves_an_exception_word_alone_case_and_diacritics_folded() -> None:
    # Arrange — "Oczywiście" ("obviously") begins with "o", the preposition, but is one word.
    fixer = PolishFusedWordFixer()
    parent = _node("Oczywiście to prawda.")

    # Act
    outcome = await fixer.run([parent], _ctx())

    # Assert — untouched, and in its original casing/diacritics.
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "Oczywiście to prawda."


async def test_run_leaves_a_word_alone_when_the_remainder_is_too_short() -> None:
    # Arrange — "dom" ("house") begins with "do", but the remainder "m" is one letter: the
    # short-word guard exempts it without ever consulting the exception set.
    fixer = PolishFusedWordFixer()
    parent = _node("To jest dom.")

    # Act
    outcome = await fixer.run([parent], _ctx())

    # Assert
    assert isinstance(outcome, Produced)
    assert outcome.value[0].content == "To jest dom."


async def test_run_answers_nothing_to_produce_for_an_empty_batch() -> None:
    # Arrange
    fixer = PolishFusedWordFixer()

    # Act
    outcome = await fixer.run([], _ctx())

    # Assert
    assert outcome == NothingToProduce(reason="no nodes to fix")


def test_config_takes_no_fields() -> None:
    # Act / Assert — an empty `with:` model is still the required shape.
    assert PolishFusedWordFixerConfig().model_dump() == {}


def test_needs_nothing_intact_but_still_destroys_verbatim() -> None:
    # Act / Assert — "can run on clean text", unlike the two ordering-constrained stages;
    # it still ends `Verbatim`, per task 2.35, the same as every processor in this pack.
    assert PolishFusedWordFixer.intact == ()
    assert PolishFusedWordFixer.destroys == (Verbatim,)


async def test_run_through_the_runner_leaves_a_node_with_no_language_fact_untouched() -> None:
    # Arrange — a mixed batch: one node carrying no `Language` fact at all (the honest
    # case today, with no `detect` stage yet to produce one — "unknown language flows
    # past"), one explicitly marked Polish. Before this repair, the fixer had no
    # `applies_to`, so the English-shaped node below would have been corrupted too.
    english = _node("Do not download the whole database.")
    polish = _node("To jest wcelu testowania.").with_ext(Language(code="pl"))
    captured: list[Sequence[Node]] = []

    registry = Registry()
    registry.add(Cleaner, "polish-fix", PolishFusedWordFixer, distribution="weft-clean")
    registry.add(Cleaner, "capture", _capture_factory(captured), distribution="weft-clean")
    engine = Runner(registry)
    pipeline = engine.resolve(
        (
            StageSpec(id="fix", contract=Cleaner, name="polish-fix"),
            StageSpec(id="capture", contract=Cleaner, name="capture"),
        ),
        tenant_id="tenant-a",
    )

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield [english, polish]

    # Act
    await engine.run(pipeline, batches(), _ctx())

    # Assert — the English node passed through byte-for-byte; only the Polish one changed.
    result = list(captured[0])
    assert result[0] is english
    assert result[1].content == "To jest w celu testowania."
