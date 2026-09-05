"""Prerequisite **V3** (`docs/09-release.md` §4.3) and **V6** — measure the baseline, more than
once, and persist it as one of Phase 4's own runs.

Hand-run. It indexes one corpus tier through one named pipeline, asks every question it can
score, repeats the whole pass, and writes one file per run under `eval/baselines/`. What makes
the file worth having is V3's own clause: *"each metric carries the interval its own repetitions
produced"*, so a later run is judged against a tolerance this system measured about itself rather
than a number somebody chose — and, since task **4.8**, V6's own clause: *"the baseline is one of
Phase 4's persisted runs, carrying the resolved pipeline, corpus identity, model versions and the
active distribution set."* `BaselineReport.record` **is** a `weft_eval.run_record.RunRecord`,
the identical type `weft eval run`/`weft trace` read — not a second, harness-shaped copy of the
same facts.

**One extractor per baseline, and that is a scope decision, not an oversight.** A resolved
pipeline names exactly one stage registered under the `Extractor` contract (task 4.0's own
design, `weft_cli.ingest._extractor_name_of`); `corpus/manifest.toml`'s `fetch` tier mixes PDFs
(`arxiv/`) and text/markdown (`pl-wiki/`), which no single resolved pipeline can describe.
Building multi-extractor pipeline resolution is not this task's to invent, so a published
baseline instead names one extractor and the manifest documents that extractor actually claims —
`EXTRACTOR_SUFFIXES` below. This *narrows* the corpus a single published baseline covers; it does
not narrow what a baseline *could* cover — a second baseline over `pdf-text` is the identical
recipe, one flag different, and nothing here stops one being taken later.

**The published run record is built in this process, not read back from `weft eval run`.**
`weft eval run` (task 4.6) is a real command and this harness could shell out to it, but its own
`corpus_identity` call hashes `IndexResult.document_ids` — resolved *filesystem paths* under
whatever directory a run happened to stage its corpus in — which is a fact about where a machine
put the files, not about their bytes. Two byte-identical corpora staged under two different
working directories (a stranger's checkout, say) would then be handed two different digests
despite indexing the same documents, which would make a published baseline fail to reproduce for
exactly the reason V6 exists to rule out. `weft_eval.run_record.corpus_identity`'s own docstring
says it "does not care" what a document id is, only that the same set always produces the same
digest — so this is a caller's choice, not a defect in that function, and this harness already
had a content-derived identity for every document before this task: `corpus/manifest.toml`'s own
sha256. `build_baseline_record` below resolves the pipeline document and discovers the active
distribution set **synchronously, in this process** — resolving a document is data manipulation
over already-parsed structures, never I/O, so it needs no second `asyncio.run` (fitness function
7(a): `eval/` gets exactly zero) — and then calls `weft_eval.run_record.build_run_record`/
`corpus_identity` directly, over the manifest's own document identities, so the published
baseline's corpus digest is the *content* digest V3's own `corpus_id()` used to compute by hand,
now built through the shared convention 4.4 published rather than a second copy of it.

**`weft` still runs as a subprocess for the one thing that has to be a process: indexing and
asking.** Fitness function 7(a) permits exactly one `asyncio.run` in the tree, at the CLI's entry
point, and the walk covers `eval/` — so the actual pipeline execution stays out of process,
through `weft index --pipeline <name>` and `weft ask --retrieve-only`, exactly as before. Only
the *resolution* of what that invocation is about to do — a pure computation over the same
`weft.toml` and pipeline document the subprocess reads — happens here, ahead of the subprocess
call, so the record this harness writes describes what the next line actually runs.

**What it measures, stated plainly, because a number whose scope is unclear is worse than
none.** This is a **retrieval** baseline: single-vector top-k, no fusion, no rerank, no
enhancement, which is exactly what V3 asks the baseline to be. It drives `weft ask
--retrieve-only`, deliberately — Phase 3 task 3.11 made `weft ask` route to a generated, cited
answer by default, and that default cannot be this baseline's measurement even once a provider is
configured: V5 (`docs/09-release.md` §4.3) requires a deterministic subset that runs in CI with
no credentials and no network, and a `weft.toml` with no `[llm.roles]` table maps no role at all,
so routed generation refuses loudly rather than running. `--retrieve-only` is Phase 0's own
contract, kept reachable through task 3.11 for exactly this caller.

**The default embedder is `hash`, not a real semantic one — found by running the binary, not
guessed at.** `weft-openai` registers its one client under the literal name `"openai"` for both
`Embedder` and `LLMProvider` (`packages/weft-openai/src/weft_openai/__init__.py`); a pipeline
*document*'s bare `use: openai` cannot say which contract it means, and `weft_cli.compile.
contracts_for` — which must infer a stage's contract from the registry, since a document names no
contract (G1) — refuses with `AmbiguousStageContractError` rather than guess. That module's own
docstring already calls this an accepted cost with no remedy available to an operator ("the only
remedy is a rename inside a distribution that is not theirs"), so this harness does not attempt
one either. `[services] embed = "openai"` is unaffected — it supplies `Embedder` as the contract
directly (`weft_cli.ingest.index_specs`) and never asks the registry to infer it — so the
collision is specific to the *pipeline-document* path task 4.0 built, which is the one this
baseline now has to use for V6's resolved pipeline. `hash` is the one `Embedder` registered under
no other contract, so it is what a *document* can name today; it is also the deterministic,
no-network, no-credential default this whole project treats as first-class (`weft_cli.services`'s
own docstring), which makes the published baseline reproducible by a stranger with no vendor
account at all — a stronger property than the openai-embedded baseline this harness used to take,
not a weaker one, even though it is not a semantic embedding. `--embedder openai` still works for
a caller who only wants `weft ask --retrieve-only`'s own reading of `[services]`, but cannot be
combined with `--pipeline`'s resolved form until the name collision above has an owner.

**Configuration is written, not assumed.** The run writes the `weft.toml` and the pipeline
document it then runs against, into its own working directory, and records what it wrote. A
baseline that depended on the operator's ambient configuration would be a number nobody else
could reproduce even holding the same corpus.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from check_questions import Question, load_questions, reproducible_questions
from metrics import (
    Excluded,
    ExclusionKind,
    Hit,
    MetricRecord,
    Scores,
    Unscoreable,
    mean_of,
    measure,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator

from weft_cli.ask import AskResult
from weft_cli.compile import contracts_for
from weft_cli.pipeline_catalogue import full_catalogue
from weft_cli.registry_bootstrap import build_dependencies
from weft_eval.run_record import RunRecord, build_run_record, corpus_identity
from weft_kernel.resolution import ResolvedPipeline, resolve

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

# `scripts/` holds the manifest reader an operator actually runs, and this file must not become
# a second one — the same rule `pyproject.toml`'s `pythonpath` states for the test run, which is
# the only other place these modules are imported from. Running by hand has no pytest to arrange
# it, so the harness arranges it for itself, here rather than in a `PYTHONPATH=` a stranger
# reproducing the baseline would have to be told about.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from fetch_corpus import (  # noqa: E402 — needs the line above to resolve
    MANIFEST,
    Document,
    Status,
    Tier,
    load_manifest,
    verify_one,
)

#: Where a written run lands. Tracked — V3's artefact is a file, not terminal output.
BASELINES_DIR: Final[Path] = REPO_ROOT / "eval" / "baselines"

#: `weft_embed.hash_embedder`'s own default `dimension`, which a Qdrant collection has to be
#: told before the first vector is written (`weft_qdrant.settings.QdrantSettings.vector_size`).
#: Matches the `--embedder` default below (`hash`); override both together for a real one.
DEFAULT_VECTOR_SIZE: Final[int] = 64

#: Which suffixes each registered `Extractor` this harness knows how to name actually claims —
#: see the module docstring's *"one extractor per baseline"* paragraph. A baseline picks one key
#: of this mapping and the manifest documents it covers are exactly the ones whose suffix is in
#: the matching value.
EXTRACTOR_SUFFIXES: Final[Mapping[str, tuple[str, ...]]] = {
    "text": (".md", ".txt"),
    "pdf-text": (".pdf",),
}

#: Seconds one `weft` invocation may take before the run gives up on it and records the failure.
_INDEX_TIMEOUT_SECONDS: Final[int] = 3600
_ASK_TIMEOUT_SECONDS: Final[int] = 180

#: `weft_cli.render._render_eval_run`'s own opening words — unused here (this harness builds its
#: own record rather than reading `weft eval run`'s, see the module docstring), kept only as a
#: comment marking why `weft index` is called instead.


class BaselineError(Exception):
    """The run cannot be taken as asked, and taking a different one silently would be worse."""


class BaselineReport(BaseModel):
    """One baseline: what was measured, over what, how many times, and the persisted run it
    measured against.

    `record` is a real `weft_eval.run_record.RunRecord` — the same type `weft eval run`,
    `weft eval compare` and `weft trace` all read — so a later `weft eval compare` between this
    run and one taken through the shipped CLI is comparing two instances of one type, not two
    shapes that happen to look similar. Refuses fewer than two repetitions at construction, which
    is V3's own failure clause — *"or the baseline was run once, in which case it records no
    interval and no later run can be judged against it"* — enforced where the file is built, so
    the file cannot exist.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded_at: str = Field(min_length=1)
    #: The corpus name and manifest tiers this run selected — harness bookkeeping that sits
    #: beside `record.corpus` rather than duplicating it: `record.corpus.digest` is the one
    #: digest (`test_baseline_shape.py` recomputes it from `documents` below through the same
    #: `weft_eval.run_record.corpus_identity` this harness calls), and `tiers`/`documents` are
    #: what let a reader — and a gate test — say *which* manifest entries it is a digest of.
    corpus_name: str = Field(min_length=1)
    tiers: tuple[str, ...]
    #: The one `Extractor` this baseline's pipeline named — see `EXTRACTOR_SUFFIXES`.
    extractor: str = Field(min_length=1)
    documents: tuple[str, ...]
    #: Derived from the tiers, never declared: false the moment an `operator` document is in.
    reproducible: bool
    record: RunRecord
    questions: tuple[str, ...]
    repeats: int = Field(ge=2)
    #: What the store was asked for per question. Every `@k` metric's `k` is within it.
    retrieval_depth: int = Field(ge=1)
    wall_clock_seconds: float = Field(ge=0.0)
    metrics: tuple[MetricRecord, ...]
    #: Every measurement that produced no value, with the reason it produced none.
    excluded: tuple[Excluded, ...] = ()

    @model_validator(mode="after")
    def _every_metrics_exclusions_are_the_ones_this_run_gave_reasons_for(self) -> BaselineReport:
        """V4's *"aggregates... report how many were excluded"*, joined back to the reasons."""
        disagreeing = sorted(
            record.metric for record in self.metrics if record.n_excluded != len(self.excluded)
        )
        if disagreeing:
            raise ValueError(
                f"metrics whose n_excluded is not the {len(self.excluded)} exclusion(s) this run "
                f"recorded reasons for: {disagreeing}"
            )
        return self

    def metric(self, name: str) -> MetricRecord | None:
        """The record for `name`, or `None` when this run did not measure it."""
        return next((record for record in self.metrics if record.metric == name), None)


def load_run(path: Path) -> BaselineReport:
    """One written baseline, refused if anything in it disagrees with itself."""
    return BaselineReport.model_validate_json(path.read_text(encoding="utf-8"))


def selected_documents(
    tiers: Sequence[Tier], *, extractor: str
) -> tuple[str, tuple[Document, ...], tuple[Document, ...]]:
    """The corpus name, the documents in `tiers` that `extractor` claims, and every manifest entry.

    All three, because the question subset is derived from the tier of *every* document a
    question names — including the ones this run excludes, which is the mechanism that keeps an
    operator-tier paper out of a published number. Refused unless every selected document is on
    this machine and matches its digest: guarding against exactly the failure where a loader
    catches a corrupt corpus file and skips it, silently shrinking what the benchmark ran over.
    """
    suffixes = EXTRACTOR_SUFFIXES.get(extractor)
    if suffixes is None:
        message = (
            f"'{extractor}' names no extractor this harness knows how to stage a corpus for. "
            f"A resolved pipeline names exactly one Extractor stage (task 4.0), so a published "
            f"baseline picks one of {sorted(EXTRACTOR_SUFFIXES)} rather than mixing formats."
        )
        raise BaselineError(message)
    name, entries = load_manifest(MANIFEST)
    wanted = tuple(
        entry for entry in entries if entry.tier in tiers and entry.path.suffix in suffixes
    )
    if not wanted:
        message = f"no document '{extractor}' claims is in tier(s) {[tier.value for tier in tiers]}"
        raise BaselineError(message)
    absent = tuple(entry for entry in wanted if verify_one(entry).status is not Status.OK)
    if absent:
        listed = ", ".join(f"{entry.id} ({verify_one(entry).status.value})" for entry in absent)
        message = (
            f"{len(absent)} of {len(wanted)} documents are missing or do not match their digest: "
            f"{listed}. Run `python scripts/fetch_corpus.py fetch` for the reproducible tiers; "
            f"the operator tier is placed by hand. A baseline over part of a corpus names the "
            f"whole one and measures something else"
        )
        raise BaselineError(message)
    return name, wanted, tuple(entries)


def staged_path(document: Document, workdir: Path) -> Path:
    """Where this run puts one corpus document, and therefore what its `SourceId` will be.

    One function, because two things have to agree exactly: what `stage_corpus` copies, and what
    the scorer resolves a retrieved passage's source back to. A retrieved passage attributed to
    no document scores as a miss against every question, which reads as bad retrieval.
    """
    return (
        workdir
        / "corpus"
        / document.path.suffix.lstrip(".")
        / document.id
        / f"{document.id}{document.path.suffix}"
    ).resolve()


def stage_corpus(documents: Sequence[Document], workdir: Path) -> None:
    """Copy each selected document into a directory of its own, named by its manifest id.

    The corpus is staged rather than indexed where it lies because a `SourceId` is the file's
    resolved path: naming the file after the manifest id is what lets a retrieved passage be
    attributed to a corpus document without a second mapping to keep true.
    """
    for document in documents:
        target = staged_path(document, workdir)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != document.path.stat().st_size:
            shutil.copyfile(document.path, target)


def write_config(
    workdir: Path, *, embedder: str, store: str, collection: str, vector_size: int
) -> Path:
    """Write the `weft.toml` this run is measured through, and hand back its path.

    `[services]` still names `embedder`/`store` — read by `weft ask --retrieve-only`, which does
    not take `--pipeline` (it needs no resolved pipeline to persist) — while indexing itself goes
    through the pipeline document `write_pipeline_document` writes beside this file, so both
    commands name the identical plugins by two different, necessary routes.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    config = workdir / "weft.toml"
    config.write_text(
        "# Written by eval/run_baseline.py. Every value is recorded in the run this produced.\n"
        "[services]\n"
        f'embed = "{embedder}"\n'
        f'store = "{store}"\n'
        "\n"
        "[packs.openai]\n"
        'api_key = "${env:OPENAI_API_KEY}"\n'
        "\n"
        "[packs.qdrant]\n"
        f'collection = "{collection}"\n'
        f"vector_size = {vector_size}\n",
        encoding="utf-8",
    )
    return config


def write_pipeline_document(
    workdir: Path, *, name: str, extractor: str, embedder: str, store: str
) -> Path:
    """Write the project-local pipeline document `weft index --pipeline` and this harness's own
    in-process resolution both read.

    A document, not `--extract`/`[services]` alone, because a `weft_kernel.resolution.
    ResolvedPipeline` — V6's own required field — only exists for a *named* pipeline (task 4.0):
    the default four-stage path builds its stages as Python constants and never calls `resolve`.
    """
    directory = workdir / "pipelines"
    directory.mkdir(parents=True, exist_ok=True)
    document = directory / f"{name}.yaml"
    document.write_text(
        "# Written by eval/run_baseline.py. Named so 'weft index --pipeline' resolves a real,\n"
        "# persistable pipeline for this baseline rather than the default, unresolved path.\n"
        f"name: {name}\n"
        "stages:\n"
        f"  - {{id: extract, use: {extractor}}}\n"
        "  - {id: chunk, use: fixed-size}\n"
        f"  - {{id: embed, use: {embedder}}}\n"
        f"  - {{id: store, use: {store}}}\n",
        encoding="utf-8",
    )
    return document


def run_indexing(*, corpus_dir: Path, pipeline_name: str, workdir: Path) -> None:
    """`weft index <corpus_dir> --pipeline <pipeline_name>`, once, over the whole staged corpus."""
    completed = _weft(
        ["index", str(corpus_dir), "--pipeline", pipeline_name],
        workdir=workdir,
        timeout=_INDEX_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        message = (
            f"`weft index {corpus_dir} --pipeline {pipeline_name}` exited "
            f"{completed.returncode}: {completed.stderr.strip()[-500:]}"
        )
        raise BaselineError(message)
    print(f"  indexed: {completed.stdout.strip()}", file=sys.stderr)


def build_baseline_record(
    *, corpus_name: str, pipeline_name: str, workdir: Path, documents: Sequence[Document]
) -> RunRecord:
    """The `RunRecord` `run_indexing` above just ran under — resolved and assembled in this
    process. See the module docstring's *"the published run record is built in this process"*
    paragraph for why this does not read `weft eval run`'s own persisted file.
    """
    deps = build_dependencies(workdir / "weft.toml")
    catalogue = full_catalogue(directory=workdir / "pipelines", reports=deps.reports)
    document = catalogue.get(pipeline_name)
    if document is None:
        message = (
            f"'{pipeline_name}' is not under {workdir / 'pipelines'} — this harness just wrote "
            f"it, so this is this module's own bug rather than an operator's. Known: "
            f"{sorted(catalogue)}"
        )
        raise BaselineError(message)
    contracts = contracts_for(document, registry=deps.registry, parents=catalogue)
    resolved: ResolvedPipeline = resolve(
        document, registry=deps.registry, contracts=contracts, parents=catalogue
    )
    identity = corpus_identity(corpus_name, (f"{doc.id}\t{doc.sha256}" for doc in documents))
    return build_run_record(
        recorded_at=datetime.now(UTC).isoformat(),
        resolved_pipeline=resolved,
        corpus=identity,
        model_versions=_model_versions(resolved),
        reports=deps.reports,
    )


def _model_versions(resolved_pipeline: ResolvedPipeline) -> dict[str, str]:
    """Every stage whose own resolved config names a `model`, as `use:model`.

    The same generic, no-hand-maintained-table idea task 4.7 built for `weft eval run`
    (`weft_cli.eval_commands._model_versions`), re-derived here rather than imported: this
    harness assembles its own `RunRecord` in-process instead of calling that command.
    """
    versions: dict[str, str] = {}
    for stage in resolved_pipeline.stages:
        config = stage.config
        model: object | None
        if isinstance(config, BaseModel):
            model = getattr(config, "model", None)
        elif isinstance(config, Mapping):
            mapping = cast("Mapping[str, object]", config)
            model = mapping.get("model")
        else:
            model = None
        if isinstance(model, str):
            versions[stage.id] = f"{stage.use}:{model}"
    return versions


def ask(question: Question, *, workdir: Path, top_k: int) -> AskResult | str:
    """One `weft ask --retrieve-only`, parsed — or the reason this measurement did not happen.

    `--retrieve-only` (task 3.11) is load-bearing here, not incidental: `weft ask` routes to a
    generated answer by default since that task, and this harness needs the deterministic,
    model-free retrieval V3 asks the baseline to be — see the module docstring's own paragraph.

    A failure comes back as a string rather than as an empty result, because "the command
    failed" and "nothing matched" are different facts and only one of them may reach a mean.
    """
    completed = _weft(
        ["ask", question.text, "--retrieve-only", "--top-k", str(top_k), "--format", "json"],
        workdir=workdir,
        timeout=_ASK_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        return f"`weft ask` exited {completed.returncode}: {completed.stderr.strip()[-300:]}"
    try:
        return AskResult.model_validate_json(completed.stdout.strip())
    except ValueError as exc:
        return f"`weft ask` answered something this harness could not read: {exc}"


def hits_of(result: AskResult, *, known: Mapping[str, str]) -> tuple[Hit, ...]:
    """The retrieved passages, with each `SourceId` resolved to the corpus document it staged.

    A source this run did not stage is dropped from `documents` rather than guessed at: it can
    only come from an index somebody else wrote, and inventing an id for it would attribute a
    passage to a document that was never asked about.
    """
    return tuple(
        Hit(
            rank=hit.rank,
            node_id=hit.node_id,
            score=hit.score,
            documents=tuple(sorted({known[source] for source in hit.sources if source in known})),
            content=hit.content,
        )
        for hit in result.hits
    )


def aggregate(
    per_repetition: Sequence[Mapping[str, float]],
    *,
    excluded: Sequence[Excluded],
    depths: Sequence[int],
    scored_counts: Sequence[int],
) -> tuple[MetricRecord, ...]:
    """Turn per-repetition means into one record per metric, carrying the interval they span.

    The mean of a repetition is a mean over the questions that *were* scored in it; a question
    excluded in one repetition and scored in another therefore moves the value, which is
    correct — it is variability of the measurement, and hiding it inside a fixed denominator
    is how a noisy system reports a narrow interval.
    """
    names = sorted({name for values in per_repetition for name in values})
    records: list[MetricRecord] = []
    for name in names:
        values = tuple(repetition[name] for repetition in per_repetition if name in repetition)
        depth = int(name.rsplit("@", 1)[1])
        if depth not in depths:
            message = f"metric {name!r} was produced at a depth this run did not ask for"
            raise BaselineError(message)
        records.append(
            MetricRecord(
                metric=name,
                depth=depth,
                values=values,
                mean=mean_of(values),
                low=min(values),
                high=max(values),
                n_scored=sum(scored_counts),
                n_excluded=len(excluded),
            )
        )
    return tuple(records)


def _weft(
    arguments: Sequence[str], *, workdir: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    """One `weft` invocation, in `workdir`, so the `weft.toml` this run wrote is what it reads.

    The console script rather than `-m`, because the surface being measured is the one a user
    has: a run that reached the CLI by a path no operator takes would be measuring something
    slightly different from what it publishes.
    """
    executable = shutil.which("weft")
    if executable is None:
        message = (
            "no `weft` on PATH. The baseline is measured through the shipped command, so it "
            "needs the workspace installed — `uv run python eval/run_baseline.py …`"
        )
        raise BaselineError(message)
    return subprocess.run(  # noqa: S603 — a resolved executable and arguments this module builds
        [executable, *arguments],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_tiers(raw: str) -> tuple[Tier, ...]:
    """`--tiers fetch,operator` as members, refusing an unknown name by listing the real ones."""
    wanted: list[Tier] = []
    for piece in raw.split(","):
        name = piece.strip()
        try:
            wanted.append(Tier(name))
        except ValueError as exc:
            message = (
                f"unknown corpus tier {name!r}; the manifest declares "
                f"{[tier.value for tier in Tier]}"
            )
            raise BaselineError(message) from exc
    return tuple(dict.fromkeys(wanted))


def parse_depths(raw: str, *, top_k: int) -> tuple[int, ...]:
    """`--depths 5,10` as integers, refused when one is deeper than the retrieval feeding it."""
    depths = tuple(sorted({int(piece.strip()) for piece in raw.split(",")}))
    too_deep = [depth for depth in depths if depth > top_k]
    if too_deep:
        message = (
            f"depths {too_deep} are deeper than --top-k {top_k}. A metric's name must state the "
            f"k it computed (`docs/09-release.md` §4.3, V4)"
        )
        raise BaselineError(message)
    return depths


def build_parser() -> argparse.ArgumentParser:
    """The options a baseline run takes. Every one of them is recorded in the file it writes."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--tiers", default=Tier.FETCH.value, help="corpus tiers, comma separated")
    parser.add_argument(
        "--extractor",
        default="text",
        choices=sorted(EXTRACTOR_SUFFIXES),
        help="the one Extractor this baseline's pipeline names — see EXTRACTOR_SUFFIXES",
    )
    parser.add_argument("--repeats", type=int, default=3, help="how many times to run the pass")
    parser.add_argument("--top-k", type=int, default=10, dest="top_k")
    parser.add_argument("--depths", default="5,10", help="the k's to report at, comma separated")
    parser.add_argument(
        "--embedder",
        default="hash",
        help=(
            "`[services] embed`, and the pipeline document's own 'embed' stage. Defaults to "
            "'hash', not a real semantic embedder — see the module docstring's own paragraph "
            "on `AmbiguousStageContractError`: `weft-openai` registers 'openai' under both "
            "Embedder and LLMProvider, so no pipeline *document* can name it for an embed "
            "stage today, only `[services] embed` (which supplies its own contract and never "
            "hits this)."
        ),
    )
    parser.add_argument("--store", default="qdrant", help="`[services] store`")
    parser.add_argument("--vector-size", type=int, default=DEFAULT_VECTOR_SIZE, dest="vector_size")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=REPO_ROOT / ".baseline-run",
        help="where the staged corpus, the written weft.toml and the pipeline document live",
    )
    parser.add_argument("--out", type=Path, default=None, help="where to write the run")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Take the baseline and write it, or say what stopped it and write nothing."""
    args = build_parser().parse_args(argv)
    if args.repeats < 2:
        print(
            f"--repeats is {args.repeats}. `docs/09-release.md` §4.3: a baseline run once "
            f"'records no interval and no later run can be judged against it', so this refuses "
            f"to write a file at all rather than write one nothing can be compared to.",
            file=sys.stderr,
        )
        return 2

    try:
        return _run(args)
    except BaselineError as exc:
        print(f"run_baseline: {exc}", file=sys.stderr)
        return 1


def _run(args: argparse.Namespace) -> int:
    """The measurement itself, once the options are known to be coherent."""
    started = time.monotonic()
    tiers = parse_tiers(args.tiers)
    depths = parse_depths(args.depths, top_k=args.top_k)
    name, documents, declared = selected_documents(tiers, extractor=args.extractor)
    reproducible = all(tier.reproducible for tier in tiers)

    # The subset this run can score, derived from the manifest exactly as
    # `tests/docs/test_question_set.py` derives the published one: a question resting on a
    # document outside the selected tiers cannot be scored here, and which documents those are
    # is a fact about the corpus rather than anything written on a question.
    # `reproducible_questions` alone answers "which tier is this document in", not "was this
    # document actually indexed" — a question whose ground truth names an arxiv PDF is still
    # `fetch`-tier-reproducible even when this run's own `--extractor` only staged `pl-wiki`'s
    # text/markdown. Scoring it anyway would credit or blame this pipeline for documents it was
    # never given to index, which is exactly the "a number whose scope is unclear" failure the
    # module docstring opens with — so this run additionally keeps only the questions whose
    # ground truth rests entirely on documents this run's own corpus actually contains.
    # Unanswerable questions name none and are unaffected, per `reproducible_questions`'s own
    # docstring.
    indexed_ids = frozenset(document.id for document in documents)
    questions = tuple(
        question
        for question in reproducible_questions(
            load_questions(),
            tiers={document.id: document.tier.value for document in declared},
            reproducible=frozenset(tier.value for tier in tiers),
        )
        if set(question.relevant_documents) <= indexed_ids
    )
    if not questions:
        message = f"no question can be scored from tier(s) {[tier.value for tier in tiers]}"
        raise BaselineError(message)

    workdir = Path(args.workdir).resolve()
    identifier = "-".join(sorted(document.id for document in documents))[:12]
    collection = f"weft_baseline_{args.extractor}_{identifier}"
    write_config(
        workdir,
        embedder=args.embedder,
        store=args.store,
        collection=collection,
        vector_size=args.vector_size,
    )
    pipeline_name = "baseline"
    write_pipeline_document(
        workdir,
        name=pipeline_name,
        extractor=args.extractor,
        embedder=args.embedder,
        store=args.store,
    )
    stage_corpus(documents, workdir)
    known = {str(staged_path(document, workdir)): document.id for document in documents}

    print(f"indexing {len(documents)} documents via '{pipeline_name}'", file=sys.stderr)
    run_indexing(corpus_dir=workdir / "corpus", pipeline_name=pipeline_name, workdir=workdir)
    record = build_baseline_record(
        corpus_name=name, pipeline_name=pipeline_name, workdir=workdir, documents=documents
    )

    per_repetition: list[Mapping[str, float]] = []
    scored_counts: list[int] = []
    excluded: list[Excluded] = []
    for repetition in range(1, args.repeats + 1):
        print(f"repetition {repetition} of {args.repeats}", file=sys.stderr)
        totals: dict[str, float] = {}
        scored = 0
        for question in questions:
            answer = ask(question, workdir=workdir, top_k=args.top_k)
            if isinstance(answer, str):
                excluded.append(
                    Excluded(
                        question_id=question.id,
                        repetition=repetition,
                        kind=ExclusionKind.MEASUREMENT_FAILED,
                        detail=answer,
                    )
                )
                continue
            result = measure(
                question,
                hits_of(answer, known=known),
                depths=depths,
                retrieval_depth=args.top_k,
            )
            if isinstance(result, Unscoreable):
                excluded.append(
                    Excluded(
                        question_id=question.id,
                        repetition=repetition,
                        kind=result.kind,
                        detail=result.detail,
                    )
                )
                continue
            scored += 1
            _accumulate(totals, result)
        if not scored:
            message = f"repetition {repetition} scored no question at all; nothing to average"
            raise BaselineError(message)
        per_repetition.append({metric: total / scored for metric, total in totals.items()})
        scored_counts.append(scored)

    report = BaselineReport(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        corpus_name=name,
        tiers=tuple(tier.value for tier in tiers),
        extractor=args.extractor,
        documents=tuple(sorted(document.id for document in documents)),
        reproducible=reproducible,
        record=record,
        questions=tuple(sorted(question.id for question in questions)),
        repeats=args.repeats,
        retrieval_depth=args.top_k,
        wall_clock_seconds=round(time.monotonic() - started, 3),
        metrics=aggregate(
            per_repetition, excluded=excluded, depths=depths, scored_counts=scored_counts
        ),
        excluded=tuple(excluded),
    )
    out = Path(args.out) if args.out else _default_out(report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


def _accumulate(totals: dict[str, float], scores: Scores) -> None:
    """Add one question's scores into the running totals for this repetition."""
    for metric, value in scores.values.items():
        totals[metric] = totals.get(metric, 0.0) + value


def _default_out(report: BaselineReport) -> Path:
    """`<corpus_digest>-<date>.json`, with an unreproducible run saying so in its own name."""
    day = report.recorded_at.split("T", 1)[0]
    label = "" if report.reproducible else "-unreproducible"
    return BASELINES_DIR / f"{report.record.corpus.digest[:12]}-{day}{label}.json"


if __name__ == "__main__":
    raise SystemExit(main())
