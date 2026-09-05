"""Task 1.8 — a language-specific stage applies per **node**, never per run.

`docs/02-extension-model.md` §3 → *Language, and what a var is for*: two different things
wear the word "language", and gating two cleaning steps on `config.language == 'pl'`, a
**run-wide** setting, is uniformly wrong for one document in a mixed corpus, with no
signal, and lets a 243-word Polish exception set fire on English text.
`02` §3's fix is "the source language is a fact about a **node**", and this module is the
proof that the fix actually holds once both halves of it are run together.

**This file adds no new kernel mechanism.** Both halves already exist, built by earlier
tasks for reasons unrelated to language: task 1.6 gave every stage `applies_to`, evaluated
per node at the seam (`weft_kernel.runner._run_stage`); tasks 1.1/1.3/1.5 gave every `with:`
value `${var:NAME}` substitution against a pipeline's merged `vars:`, resolved once per
pipeline (`weft_kernel.resolution._substitute_vars`). What had not been demonstrated before
this task is that the two compose the way `02` §3 claims: a mixed corpus resolved and run
*once* treats each node correctly by its own fact, while the pipeline-wide decision a var
carries — here, a translation target — never leaks into that per-node decision. That is a
property of the *composition*, not of either mechanism alone, which is why it needed its own
test rather than an extra case appended to `test_resolution.py` or `test_runner.py`.

**The three plugins below tell `02` §3's cleaning-chain story, at the smallest size
that still tells it honestly.** `_Detect` stands in for "the extractor or an ordinary
`detect` stage" `02` §3 names as the source of the fact — a deliberate no-op, since every
fixture here attaches (or withholds) `_Language` directly; its only job is to make "some
earlier stage provides this" **structural**, the resolution check `_Translate.requires`
below needs to pass at all. `_PolishFix` stands in for the 243-word fused-word exception set
(`docs/02-extension-model.md` §3's own citation): `applies_to = (Applies(_Language,
code="pl"),)` narrows it to Polish nodes exactly, and it does nothing at all to a node the
fact does not match — flowing an English node, or a node with no `_Language` fact yet, past
it *is* the "unknown language flows past" rule, not a case this test's fixture code has to
simulate separately. `_Translate` is deliberately **not** a translator — `02` §3: "Translation
itself needs no new concept: a stage that requires the language, rewrites the text and
provides the new one" — so it stands in for that shape with a trivial, obviously-fake rewrite
(`f"[{target}] {content}"`) and narrows `applies_to` to *any* `_Language` fact at all
(`Applies(_Language)`, no `code=` constraint), which is what "everything after it sees a single
language" costs a stage that has one: it still has to know a source language exists before it
can act, it just does not care which one.

**The var is `target_lang`, read off `with: {target_lang: "${var:target_lang}"}`, exactly
`02` §3's own worked example** (`base-de.yaml`) — a translation target is the section's own
motivating case for what a var is *for*, so this file's var is not a fresh example invented
for the test, it is the specification's.

`test_a_var_sharing_the_applicability_constraint_s_value_never_retargets_it` is
this file's load-bearing test. A var carrying a value unrelated to `"pl"` proves nothing about
whether a var *could* reach `applies_to` — it would look identical whether or not the wiring
existed. Resolving the identical pipeline twice, with `target_lang` set to `"en"` and then to
the one string `_PolishFix`'s own constraint narrows on, `"pl"`, and asserting the fixer's own
routing decision is byte-identical either way, is a test that a real leak would actually fail.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from weft_kernel import resolution, runner
from weft_kernel.context import Context
from weft_kernel.payload import Applies, ExtModel, MediaType, Node, Outcome, Produced, Property
from weft_kernel.pipeline import Pipeline, StageDeclaration
from weft_kernel.registry import Registry
from weft_kernel.runner import Stage

_FIXED_MARKER = "[pl-fixed] "


class _NodeStage(Stage[Sequence[Node], Sequence[Node]], Protocol):
    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]: ...


class _Language(ExtModel):
    """The source-language fact `02` §3 means: "provided per node by the extractor or by an
    ordinary `detect` stage." Test-local — `02` §3 assigns no pack this namespace yet, and
    a real `detect` stage is later work this task does not need: every fixture below attaches
    (or withholds) this fact directly, standing in for whatever upstream stage would have.
    """

    __namespace__ = "weft-test-pack"
    __schema_version__ = "1.0.0"

    code: str


class _PolishFix:
    """Stand-in for a Polish fused-word exception set — narrowed, never guessing.

    `applies_to` names the one fact this stage's own logic needs (`_Language` with
    `code="pl"`); nothing in `run` branches on a node's content or language, so if an
    English or unknown-language node ever came out changed, the only place that could have
    happened is `weft_kernel.runner` routing it here regardless — exactly the property
    `test_runner.py`'s own `_NaiveSplitter` proves for tables, applied here to language.
    """

    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()
    applies_to = (Applies(_Language, code="pl"),)

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        fixed: list[Node] = []
        for node in payload:
            # Guaranteed present — `applies_to` above already routed only matching nodes
            # here — read defensively anyway rather than asserted, the same caution
            # `weft_kernel.resolution`'s own defensive `getattr` reads apply throughout.
            language = node.ext_as(_Language)
            new_node = node.derive(content=f"{_FIXED_MARKER}{node.content}")
            if language is not None:
                new_node = new_node.with_ext(language)
            fixed.append(new_node)
        return Produced(value=fixed)


class _Detect:
    """Stand-in for "an ordinary `detect` stage" — `02` §3's own second source of the
    language fact, the extractor being the first. A no-op on purpose: every fixture in this
    file attaches (or withholds) `_Language` directly, standing in for whatever a real
    detector decided, so this class's only job is to make that decision **structural** —
    `provides = (_Language,)` is what lets `_Translate`'s `requires = (_Language,)` resolve
    at all (`02` §3's third resolution check: "the stage's `requires` are produced by some
    upstream stage"). `provides` is a promise about the *pipeline*, never a guarantee about
    every node — a detector that could not decide for a given node is exactly the "unknown
    language" case `_node(..., code=None)` fixtures below construct, and it is still
    correctly wired downstream: this class's `run` never invents a fact it cannot support.
    """

    requires: tuple[type[ExtModel], ...] = ()
    provides = (_Language,)
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()

    def __init__(self, config: object) -> None: ...

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        return Produced(value=payload)


class _TranslateConfig(BaseModel):
    """`_Translate`'s typed `with:` model — task 1.5's mechanism, carrying the one var this
    file is about. `02` §3's own words for what it holds: "a translation target, a reply
    language."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_lang: str


class _Translate:
    """A trivial, deliberately-fake stand-in for `02` §3's translation stage — not a
    translator. "A stage that requires the language, rewrites the text and provides the new
    one" is the whole shape; this class's rewrite (`f"[{target}] ..."`) exists only so a test
    can see which `target_lang` a run actually used, never to translate anything for real.
    `applies_to = (Applies(_Language),)` — presence only, no `code=` — is what "everything
    after it sees a single language" costs this stage: it still needs *a* source language
    fact to have been decided before it runs, so a node with none (language undetected) flows
    past it exactly as it flows past `_PolishFix`, for the identical safe-side reason.
    """

    requires = (_Language,)
    provides = (_Language,)
    intact: tuple[type[Property], ...] = ()
    destroys: tuple[type[Property], ...] = ()
    applies_to = (Applies(_Language),)
    config_model = _TranslateConfig

    def __init__(self, config: _TranslateConfig) -> None:
        self._target = config.target_lang

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        translated = [
            node.derive(content=f"[{self._target}] {node.content}").with_ext(
                _Language(code=self._target)
            )
            for node in payload
        ]
        return Produced(value=translated)


class _Capture:
    """An identity stage that records the batch it was handed, on `test_runner.py`'s own
    precedent: `Runner.run` returns only counts, so a test that needs the resulting nodes
    puts a stage after the ones under test whose only job is to remember what it saw.
    """

    lifetime = runner.Lifetime.RUN
    requires: tuple[type[ExtModel], ...] = ()
    provides: tuple[type[ExtModel], ...] = ()

    def __init__(self, captured: list[Sequence[Node]]) -> None:
        self._captured = captured

    async def run(self, payload: Sequence[Node], ctx: Context) -> Outcome[Sequence[Node]]:
        self._captured.append(payload)
        return Produced(value=payload)


def _capture_factory(captured: list[Sequence[Node]]) -> Callable[[object], _Capture]:
    def factory(config: object) -> _Capture:
        return _Capture(captured)

    return factory


def _node(content: str, *, code: str | None = None) -> Node:
    """A synthetic node, optionally carrying a source-language fact.

    `code=None` is the "unknown language" case — no `_Language` ext at all, never a fact
    present with some placeholder value — because `02` §3's "unknown language flows past" is
    about a fact that was never decided, not a decided-and-empty one.
    """
    node = Node.synthetic(content=content, media_type=MediaType.TEXT, reason="1.8 fixture")
    if code is not None:
        node = node.with_ext(_Language(code=code))
    return node


def _ctx() -> Context:
    return Context(tenant_id="tenant-a", run_id="run-1", trace_id="trace-1", locale="en")


def _contents(nodes: Sequence[Node]) -> list[str]:
    return [node.content for node in nodes]


def _registry(captured: list[Sequence[Node]]) -> Registry:
    registry = Registry()
    registry.add(_NodeStage, "detect", _Detect, distribution="weft-test-pack")
    registry.add(_NodeStage, "polish-fix", _PolishFix, distribution="weft-test-pack")
    registry.add(_NodeStage, "translate", _Translate, distribution="weft-test-pack")
    registry.add(_NodeStage, "capture", _capture_factory(captured), distribution="weft-test-pack")
    return registry


_CONTRACTS: dict[str, type[object]] = {
    "detect": _NodeStage,
    "fix": _NodeStage,
    "translate": _NodeStage,
}
_STAGES = (
    StageDeclaration(id="detect", use="detect"),
    StageDeclaration(id="fix", use="polish-fix"),
    StageDeclaration(id="translate", use="translate", config={"target_lang": "${var:target_lang}"}),
)


async def _resolve_and_run(target_lang: str, batch: Sequence[Node]) -> list[Node]:
    """Resolve `_STAGES` against `target_lang`, then run `batch` through the runnable result.

    The bridge from `resolution.ResolvedPipeline` to `runner.RunnablePipeline` is not a
    kernel API yet — `weft_kernel.resolution`'s own module docstring: "Building a
    `RunnablePipeline` from a `ResolvedPipeline`... is a later step's job, not this one's."
    So this helper does it by hand, the way a caller with both pieces already in scope would:
    each `ResolvedStage.use` and its already-var-substituted `config` become a `StageSpec`
    against the same `contracts` mapping `resolve()` was given.
    """
    captured: list[Sequence[Node]] = []
    registry = _registry(captured)
    document = Pipeline(name="base", vars={"target_lang": target_lang}, stages=_STAGES)
    resolved = resolution.resolve(document, registry=registry, contracts=_CONTRACTS)
    specs = [
        runner.StageSpec(
            id=stage.id, contract=_CONTRACTS[stage.id], name=stage.use, config=stage.config
        )
        for stage in resolved.stages
    ]
    specs.append(runner.StageSpec(id="capture", contract=_NodeStage, name="capture"))

    engine = runner.Runner(registry)
    pipeline = engine.resolve(tuple(specs), tenant_id="tenant-a")

    async def batches() -> AsyncIterator[Sequence[Node]]:
        yield batch

    await engine.run(pipeline, batches(), _ctx())
    return list(captured[0])


async def test_a_mixed_corpus_gets_each_language_specific_stage_only_where_it_applies() -> None:
    # Arrange — one Polish node, one English node, one node whose language was never
    # decided at all, in one batch, run through both language-aware stages in one pass.
    polish = _node("komputer", code="pl")
    english = _node("hello", code="en")
    unknown = _node("mystery")

    # Act
    result = await _resolve_and_run("en", [polish, english, unknown])

    # Assert — the fixer touched only the Polish node; the translator touched every node
    # whose language *was* decided, whatever it was, and left the undecided one alone.
    assert _contents(result) == ["[en] [pl-fixed] komputer", "[en] hello", "mystery"]


async def test_an_unknown_language_node_flows_past_every_language_aware_stage_untouched() -> None:
    # Arrange — the safe-side case stated on its own: no `_Language` fact means no
    # language-aware stage in the pipeline ever claims this node, not merely the one
    # narrowed to a specific code.
    unknown = _node("mystery")

    # Act
    result = await _resolve_and_run("de", [unknown])

    # Assert — identity preserved, not merely equal content: the seam never called either
    # stage's `run` on it at all, the same way `test_runner.py`'s own applicability test
    # asserts `result[2] is table` rather than merely comparing values.
    assert result[0] is unknown


async def test_a_var_reaches_a_stage_s_with_block_through_resolution() -> None:
    # Arrange — `${var:target_lang}` in `translate`'s `with:` block, `target_lang: 'de'` in
    # the pipeline's own `vars:` — `02` §3's own shape, resolved with no `extends` involved.
    registry = _registry([])
    document = Pipeline(name="base", vars={"target_lang": "de"}, stages=_STAGES)

    # Act
    resolved = resolution.resolve(document, registry=registry, contracts=_CONTRACTS)

    # Assert — the *validated* config object, not the raw `${var:...}` string, is what the
    # resolved stage carries; `_TranslateConfig(target_lang="de")` compares by value.
    translate_stage = next(stage for stage in resolved.stages if stage.id == "translate")
    assert translate_stage.config == _TranslateConfig(target_lang="de")


def test_a_child_overriding_the_var_retargets_translation_in_two_lines() -> None:
    # Arrange — `02` §3's own `base-de.yaml`: "extends: base" and "vars: {target_lang: de}"
    # are the entire file. `base` sets no var of its own to prove the child's is what wins.
    registry = _registry([])
    base = Pipeline(name="base", vars={"target_lang": "en"}, stages=_STAGES)
    base_de = Pipeline(name="base-de", extends="base", vars={"target_lang": "de"})

    # Act
    resolved = resolution.resolve(
        base_de, registry=registry, contracts=_CONTRACTS, parents={"base": base}
    )

    # Assert
    translate_stage = next(stage for stage in resolved.stages if stage.id == "translate")
    assert translate_stage.config == _TranslateConfig(target_lang="de")


async def test_a_var_sharing_the_applicability_constraint_s_value_never_retargets_it() -> None:
    # Arrange — the sharpest case `02` §3's "vars never participate in applicability" has:
    # `target_lang` set to `"pl"`, the exact literal `_PolishFix`'s own `applies_to` narrows
    # on. A wiring bug that let a var reach `applies_to` would be invisible under any value
    # that does *not* collide with the constraint — this is the one value it cannot hide
    # behind.
    polish = _node("komputer", code="pl")
    english = _node("hello", code="en")
    unknown = _node("mystery")

    # Act
    targeting_english = await _resolve_and_run("en", [polish, english, unknown])
    targeting_polish = await _resolve_and_run("pl", [polish, english, unknown])

    # Assert — `_PolishFix`'s own routing decision (who gets the `[pl-fixed]` marker) is
    # identical either way: only the actually-Polish node, in both runs. Only the
    # translation target the var controls actually changes.
    assert [_FIXED_MARKER in node.content for node in targeting_english] == [True, False, False]
    assert [_FIXED_MARKER in node.content for node in targeting_polish] == [True, False, False]
    assert _contents(targeting_english) == ["[en] [pl-fixed] komputer", "[en] hello", "mystery"]
    assert _contents(targeting_polish) == ["[pl] [pl-fixed] komputer", "[pl] hello", "mystery"]


def test_a_var_token_written_as_an_applies_constraint_value_is_never_substituted() -> None:
    # Arrange — `weft_kernel.payload.applicability`'s own module docstring: "there is no
    # `${var:NAME}` token for `weft_kernel.resolution`'s substitution to ever reach." Proven
    # directly here, independent of any pipeline document or resolution call at all: even a
    # plugin author who wrote the token itself as a literal `code=` value gets no
    # substitution — `Applies.matches` treats it as an ordinary, opaque string.
    applies = Applies(_Language, code="${var:target_lang}")
    an_ordinary_polish_node = _node("x", code="pl")
    a_node_whose_fact_is_the_literal_token_text = _node("x", code="${var:target_lang}")

    # Act / Assert
    assert applies.matches(an_ordinary_polish_node) is False
    assert applies.matches(a_node_whose_fact_is_the_literal_token_text) is True
