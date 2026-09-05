"""`weft render` — extract a directory and hand the result back as one readable document.

Ledger task **8.9**, and it is a driver for a contract that had none. `weft_extract.contract.
Renderer` is `Stage[Sequence[Node], Rendition]` and describes itself as *"an ordinary `Stage`
terminus"* whose output *"leaves the pipeline for a human or another system"*. Two renderers
have been registered since task 2.27 — `plain` and `markdown` — and **nothing in the tree ever
took a `Rendition` out**: `weft index` returns an `IndexResult` built from the run summary and
the store's own count, and no other command produced one at all. So task 2.27's own exit
demonstration, *"an operator's PDF becomes readable"*, was not reachable from the CLI, and
fitness function 16 carried both names in its waiver because a document ending in one would
resolve, run, and discard its only product.

**Why a command rather than a flag on `weft index`.** They answer different questions. `index`
asks *"what should the corpus hold?"* and its result is in the store; this asks *"what does
this file actually look like once Weft has read it?"*, and its result is on stdout. Folding the
second into the first would give `index` a mode in which it stores nothing, which is the shape
`03`'s command surface keeps apart — and it would put a `Rendition` inside `IndexCommandResult`
for every run that did not want one.

**It resolves a document like every other pipeline path**, through `full_catalogue` and
`weft_cli.compile`, and reaches `Runner.run_once` rather than `Runner.run` for the reason that
method's own docstring gives: `run` returns counts and reason strings, and here *the payload is
the point*. That is the same call the query path makes, one payload shape over.

**Nothing here decides what "readable" means.** Which renderer runs, and how it separates nodes,
is the document's business — `preview-plain` and `preview-markdown` ship, and a pack that
registers a `docx` renderer is selectable by writing its name in a document, with no edit here.
This module knows the `Renderer` contract only well enough to insist the document ends in one.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from weft_cli.compile import contracts_for, to_specs
from weft_cli.pipeline_catalogue import UnknownPipelineNameError, full_catalogue
from weft_extract.accept import claimed_extensions, present_suffixes
from weft_extract.contract import Extractor, Renderer
from weft_extract.payload import Rendition
from weft_extract.text import discover_source_docs
from weft_kernel.context import Context
from weft_kernel.discovery import PackReport
from weft_kernel.errors import UnresolvedNameError
from weft_kernel.payload import Failed, NothingToProduce, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.resolution import Contribution, resolve
from weft_kernel.runner import PipelineResolutionError, Runner, StageSpec


class PipelineMissingRenderStageError(PipelineResolutionError, UnresolvedNameError):
    """`--pipeline` named a document whose last stage is not a `Renderer`.

    Refused before anything runs, and by the same argument `weft_cli.ingest.
    PipelineMissingExtractStageError` makes for its own contract: a document that cannot
    possibly produce the thing this command exists to print is a fact about the document, not
    an empty result. Running it anyway would hand back a `Sequence[Node]` where a `Rendition`
    was expected and fail as a type confusion with nothing in it naming the real mistake.

    Fitness function 12's family: `valid_options` is every stage id the document does resolve,
    so an operator who meant a different document sees what this one actually contains. The
    `__init__` is spelled out for the same reason `PipelineMissingExtractStageError`'s is —
    `PipelineResolutionError` and `UnresolvedNameError` each own part of the signature, and
    neither knows about the other's half.
    """

    def __init__(
        self,
        message: str,
        *,
        valid_options: tuple[str, ...],
        pipeline: str | None = None,
        remedy: str = "",
    ) -> None:
        PipelineResolutionError.__init__(self, message, pipeline=pipeline, remedy=remedy)
        self.valid_options = valid_options


async def run_render(
    directory: Path,
    *,
    pipeline: str,
    registry: Registry,
    ctx: Context,
    reports: Sequence[PackReport] = (),
    contributions: tuple[Contribution, ...] = (),
) -> Rendition | None:
    """Every file under `directory` an extractor claims, rendered by `pipeline`'s own terminus.

    `None` for an empty directory — the same distinction `weft_cli.ingest.run_index` draws and
    for the same reason: there is nothing whose format needs an extractor, so there is nothing
    to choose and nothing to render, and that is a fact about the filesystem rather than a
    failure. The caller says so in its own words; this function does not invent a `Rendition`
    with empty text, which would be indistinguishable from a corpus that rendered to nothing.

    Raises `UnknownPipelineNameError` for a name the catalogue does not hold,
    `PipelineMissingRenderStageError` for a document that does not end in a `Renderer`, and
    every `weft_kernel.runner.PipelineResolutionError` a malformed document or an unregistered
    plugin raises, unchanged — the same set `run_index` documents for its own resolution.
    """
    catalogue = full_catalogue(reports=reports)
    document = catalogue.get(pipeline)
    if document is None:
        options = tuple(sorted(catalogue))
        raise UnknownPipelineNameError(
            f"'{pipeline}' is not a pipeline this project knows — checked the project's own "
            f"'pipelines' directory and every installed pack's own contribution. Known "
            f"pipelines: {', '.join(options) or '(none)'}.",
            valid_options=options,
            pipeline=pipeline,
            remedy=f"use one of: {', '.join(options) or '(none — no pipeline is known yet)'}.",
        )
    contracts = contracts_for(
        document, registry=registry, parents=catalogue, contributions=contributions
    )
    resolved = resolve(
        document,
        registry=registry,
        contracts=contracts,
        parents=catalogue,
        contributions=contributions,
    )
    specs = to_specs(resolved, registry=registry)
    _refuse_without_a_render_terminus(specs, pipeline=pipeline)

    # Written as three named steps, not one expression, and that is a property rather than a
    # style: fitness function 5(a) traces the `extensions=` argument back to `claimed_extensions`
    # by following assignments, and an inline `present_suffixes(...) & _extensions_of(...)` is
    # opaque to it. The check is right to refuse what it cannot trace — filtering on a pack's
    # own constant is how `.pdf` became silently invisible to ingest at ledger 2.27, nine PDFs
    # walked and none matched, exit 0 reporting success — so the derivation is spelled out here
    # exactly as `weft_cli.ingest.run_index` spells out its own.
    claims = claimed_extensions(registry)
    accepted = _extensions_of(specs, claims=claims)
    readable = present_suffixes(directory) & accepted
    docs = discover_source_docs(directory, extensions=readable)
    if not docs:
        return None

    runner = Runner(registry)
    runnable = runner.resolve(specs, tenant_id=ctx.tenant_id)
    outcome: Outcome[object] = await runner.run_once(runnable, docs, ctx)
    if isinstance(outcome, Produced) and isinstance(outcome.value, Rendition):
        return outcome.value
    raise PipelineResolutionError(
        f"pipeline '{pipeline}' did not produce a rendition: {_why(outcome)}",
        pipeline=pipeline,
        remedy=(
            "read the reason above — a renderer that declined or failed says why, and the "
            "stage that did so is named in the message."
        ),
    )


def _why(outcome: Outcome[object]) -> str:
    """What a non-`Produced` outcome actually said, relayed rather than flattened.

    `NothingToProduce` and `Failed` are different facts — *"there was nothing here"* against
    *"I could not"* — and a caller that collapsed them into one sentence would be the silent
    fallback this project refuses. A `Produced` carrying the wrong type is a third thing again,
    and it is a defect in whatever registered that plugin under `Renderer`.
    """
    if isinstance(outcome, NothingToProduce):
        return f"nothing to produce ({outcome.reason})"
    if isinstance(outcome, Failed):
        return f"failed ({outcome.reason})"
    return (
        f"produced a {type(getattr(outcome, 'value', outcome)).__name__} rather than a "
        f"Rendition, which means the plugin at the last stage is registered under Renderer "
        f"and does not satisfy it"
    )


def _refuse_without_a_render_terminus(specs: Sequence[StageSpec], *, pipeline: str) -> None:
    """The document's **last** stage must be a `Renderer` — not merely contain one.

    Position matters here in a way it does not for `run_index`'s extract check. A `Renderer`
    returns a `Rendition`, which no `Stage` takes as input, so a document with one in the
    middle cannot compose at all and `resolve` has already refused it. What is left for this
    function to catch is the document that composes perfectly and simply ends somewhere else —
    an ingest document, say — whose terminus is a `Sequence[Node]` this command has no use for.
    """
    if specs and specs[-1].contract is Renderer:
        return
    ids = tuple(spec.id for spec in specs)
    raise PipelineMissingRenderStageError(
        f"pipeline '{pipeline}' does not end in a stage registered under the Renderer "
        f"contract, so it produces nodes rather than a document to read. Its stages: "
        f"{', '.join(ids) or '(none)'}.",
        valid_options=ids,
        pipeline=pipeline,
        remedy=(
            f"name a pipeline whose last stage renders — 'preview-plain' and "
            f"'preview-markdown' ship — or add one to '{pipeline}'."
        ),
    )


def _extensions_of(
    specs: Sequence[StageSpec], *, claims: Mapping[str, tuple[str, ...]]
) -> frozenset[str]:
    """What the document's own extractor claims, so discovery narrows to exactly that.

    The same derivation `weft_cli.ingest.run_index` makes, restated here rather than imported:
    that function's helper is built around `--extract` narrowing a *default* pipeline, and this
    path has no default and no flag. What both share is the rule — the formats a run will read
    come from the extractor that will actually run, never from a fixed list — and it is the
    rule that matters, not the helper. `claims` is passed in rather than computed here so the
    derivation stays visible at the call site, where fitness function 5(a) reads it.

    **`claims` is keyed by *suffix*, not by plugin name** — `weft_extract.accept.
    claimed_extensions` maps `".txt" -> ("text",)`, because the question it answers for its
    original caller is *"who can read this file I found?"*. This function asks the inverse,
    *"what may this plugin read?"*, so it filters on the values. The first draft did
    `claims.get(spec.name)`, looking a plugin name up as though it were a suffix: always empty,
    so `weft render` reported "nothing to render" over a directory of readable files and exited
    0. Found by running the binary — every test passed, because each one supplied its own
    fixture rather than deriving from the real registry.
    """
    for spec in specs:
        if spec.contract is Extractor:
            return frozenset(suffix for suffix, names in claims.items() if spec.name in names)
    return frozenset()
