"""Prerequisite **V3** (`docs/09-release.md` §4.3) — measure the baseline, more than once.

Hand-run. It indexes the corpus tiers it is given, asks every question they can score, repeats
the whole pass, and writes one file per run under `eval/baselines/`. What makes the file worth
having is the last part of V3's clause: *"each metric carries the interval its own repetitions
produced"*, so a later run is judged against a tolerance this system measured about itself
rather than against a number somebody chose.

**Two artefacts, never one.** A run over the `fetch` (and `gate`) tiers is **reproducible** —
its documents are fetchable by a pinned, checksummed script, and Phase 6's exit is a stranger
repeating the number. A run that includes the `operator` tier is **not**, because those papers
are held under publisher copyright and cannot be obtained at any price; such a run is written
with `reproducible: false` and every reader of the file is expected to carry the label with the
number. `.phase2-findings.md` §15: reporting a figure over the whole set as though it were
reproducible would be the reference's `gold_node_id_map` defect in a new costume. The flag is
**derived from the manifest's tiers** (`Tier.reproducible`), never passed in.

**`weft` runs as a subprocess, and that is forced twice over.** Fitness function 7(a) permits
exactly one `asyncio.run` in the tree, at the CLI's entry point, and the walk covers `eval/` —
so an in-process harness fails the gate. It is also the better measurement: the baseline is
taken through the exact surface a user has, with a real distribution set and a real process
boundary, and no private path exists here to drift from the shipped one.

**What it measures, stated plainly, because a number whose scope is unclear is worse than
none.** This is a **retrieval** baseline: single-vector top-k, no fusion, no rerank, no
enhancement, which is exactly what V3 asks the baseline to be. It drives `weft ask
--retrieve-only`, deliberately — Phase 3 task 3.11 made `weft ask` route to a generated,
cited answer by default, and that default cannot be this baseline's measurement even once a
provider is configured: V5 (`docs/09-release.md` §4.3) requires a deterministic subset that
runs in CI with no credentials and no network, and a `weft.toml` with no `[llm.roles]` table
maps no role at all (`weft_llm.roles.LLMRoles`'s own "no silent default" clause), so routed
generation refuses loudly rather than running. `--retrieve-only` is Phase 0's own contract,
kept reachable through task 3.11 for exactly this caller — see `docs/build-ledger.md`'s 3.11
entry. The generation-side number V3's neighbours will want — stance accuracy on the
unanswerable subset — needs a generator and is not attempted here; those 17 questions are
excluded by name and counted, never scored as zero.

**Configuration is written, not assumed.** The run writes the `weft.toml` it then runs against,
into its own working directory, and records what it wrote. A baseline that depended on the
operator's ambient configuration would be a number nobody else could reproduce even holding the
same corpus — and `.phase2-findings.md` finding 9 requires swapping a parser to be exactly this:
a configuration edit, visible in the file and recorded in the run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final

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

from weft_chunk import FixedSizeChunkerConfig
from weft_cli.ask import AskResult
from weft_openai.embedder import DEFAULT_MODEL

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

#: The native width of `text-embedding-3-small`, which a Qdrant collection has to be told
#: before the first vector is written (`weft_qdrant.settings.QdrantSettings.vector_size`).
#: Overridable, because naming a different model is a configuration edit and this width moves
#: with it.
DEFAULT_VECTOR_SIZE: Final[int] = 1536

#: Which registered `Extractor` reads each corpus format. **The same names
#: `tests/docs/test_question_set.py` verified the quotes through** — a baseline indexed by one
#: backend and ground-truthed against another scores every span as a miss and reports it as bad
#: retrieval. Options rather than constants, per `.phase2-findings.md` finding 9.
DEFAULT_EXTRACTORS: Final[Mapping[str, str]] = {".pdf": "pdf-text", ".txt": "text", ".md": "text"}

#: Seconds one `weft` invocation may take before the run gives up on it and records the failure.
#: Generous: a first `weft index` over 25 papers embeds every chunk through a vendor API.
_INDEX_TIMEOUT_SECONDS: Final[int] = 3600
_ASK_TIMEOUT_SECONDS: Final[int] = 180


class BaselineError(Exception):
    """The run cannot be taken as asked, and taking a different one silently would be worse."""


class StageRecord(BaseModel):
    """One stage of what actually ran, with the settings that decide what it produced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str = Field(min_length=1)
    plugin: str = Field(min_length=1)
    settings: Mapping[str, str] = {}


class DistributionRecord(BaseModel):
    """An installed distribution and its version, as the environment that ran reported them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: str = Field(min_length=1)


class CorpusRecord(BaseModel):
    """Which corpus this is, in a form two runs can be compared by.

    `corpus_id` is a digest over `(document id, sha256)` for every document in the declared
    tiers, so two corpora with the same bytes have the same id however they are laid out, and
    one document changing gives a different id — which is what makes V3's *"a baseline from a
    different corpus"* a checkable fact rather than a promise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    tiers: tuple[str, ...]
    documents: tuple[str, ...]


class BaselineRun(BaseModel):
    """One baseline: what was measured, over what, how many times, and what it spanned.

    Refuses fewer than two repetitions at construction, which is V3's own failure clause —
    *"or the baseline was run once, in which case it records no interval and no later run can
    be judged against it"* — enforced where the file is built, so the file cannot exist.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recorded_at: str = Field(min_length=1)
    corpus: CorpusRecord
    #: Derived from the tiers, never declared: false the moment an `operator` document is in.
    reproducible: bool
    questions: tuple[str, ...]
    repeats: int = Field(ge=2)
    #: What the store was asked for per question. Every `@k` metric's `k` is within it.
    retrieval_depth: int = Field(ge=1)
    pipeline: tuple[StageRecord, ...]
    #: sha256 over the pipeline record above — V3's *"a different pipeline"*, made checkable.
    pipeline_sha256: str = Field(min_length=1)
    models: Mapping[str, str]
    distributions: tuple[DistributionRecord, ...]
    wall_clock_seconds: float = Field(ge=0.0)
    metrics: tuple[MetricRecord, ...]
    #: Every measurement that produced no value, with the reason it produced none. Recorded once
    #: here rather than on each metric, because the same question is excluded from all of them —
    #: and the validator below is what stops that convenience becoming a count nothing backs.
    excluded: tuple[Excluded, ...] = ()

    @model_validator(mode="after")
    def _every_metrics_exclusions_are_the_ones_this_run_gave_reasons_for(self) -> BaselineRun:
        """V4's *"aggregates... report how many were excluded"*, joined back to the reasons.

        Uniform by construction today: a question carries judgements at both granularities or at
        neither, and a failed `weft ask` takes every metric with it. If a metric ever excludes a
        different set from the rest, this is the check that says so instead of a file quietly
        reporting a count no list supports.
        """
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


def load_run(path: Path) -> BaselineRun:
    """One written baseline, refused if anything in it disagrees with itself."""
    return BaselineRun.model_validate_json(path.read_text(encoding="utf-8"))


def corpus_id(documents: Iterable[Document]) -> str:
    """The identity of a document set: a digest over each document's id and its own digest."""
    lines = sorted(f"{document.id}\t{document.sha256}" for document in documents)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def pipeline_digest(stages: Sequence[StageRecord]) -> str:
    """A digest over the resolved stage list, so "a different pipeline" is a comparison."""
    dumped = json.dumps([stage.model_dump() for stage in stages], sort_keys=True)
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def selected_documents(
    tiers: Sequence[Tier],
) -> tuple[str, tuple[Document, ...], tuple[Document, ...]]:
    """The corpus name, the documents in `tiers`, and every document the manifest declares.

    All three, because the question subset is derived from the tier of *every* document a
    question names — including the ones this run excludes, which is the whole mechanism that
    keeps an operator-tier paper out of a published number. Refused unless every selected
    document is on this machine and matches its digest: reference defect 7 by name, whose loader
    caught a corrupt corpus file and skipped it, silently shrinking what the benchmark ran over.
    """
    name, entries = load_manifest(MANIFEST)
    wanted = tuple(entry for entry in entries if entry.tier in tiers)
    if not wanted:
        message = f"no document in the manifest is in tier(s) {[tier.value for tier in tiers]}"
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

    **One directory per document**, which is not tidiness. `weft index` hands everything it
    finds under a directory to the runner as a single batch, and `weft-qdrant` writes a batch in
    one request: sixteen papers at once came to more than Qdrant's 32 MiB request limit, which
    it refuses with HTTP 400 — surfacing as `'store' failed:` with **no reason at all**, because
    the driver's exception stringifies to nothing. Indexing a document at a time keeps every
    write small; the empty reason is `weft-qdrant`'s to fix and is recorded, not worked around
    silently.
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

    Written rather than assumed: the run has to be reproducible by someone whose own project
    configuration is different, and `weft.toml` is resolved relative to the working directory,
    so a file here is the whole of what the subprocess sees.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    config = workdir / "weft.toml"
    config.write_text(
        "# Written by eval/run_baseline.py. Every value is recorded in the run this produced.\n"
        "[services]\n"
        f'embed = "{embedder}"\n'
        f'store = "{store}"\n'
        "\n"
        "[packs.weft-openai]\n"
        'api_key = "${env:OPENAI_API_KEY}"\n'
        "\n"
        "[packs.weft-qdrant]\n"
        f'collection = "{collection}"\n'
        f"vector_size = {vector_size}\n",
        encoding="utf-8",
    )
    return config


def index_corpus(
    documents: Sequence[Document], *, workdir: Path, extractors: Mapping[str, str]
) -> None:
    """Run `weft index` once per staged document, through the extractor named for its format.

    One invocation per document rather than one per format — see `staged_path` for the store
    request limit that decides it. The extractor is named rather than left to be derived,
    because two backends claim `.pdf` deliberately and the quotes this run is scored against
    were verified through one of them.
    """
    for document in documents:
        suffix = document.path.suffix
        extractor = extractors.get(suffix)
        if extractor is None:
            message = (
                f"no extractor named for {suffix!r}; the corpus holds a format this run was not "
                f"told how to read. Known: {sorted(extractors)}"
            )
            raise BaselineError(message)
        directory = staged_path(document, workdir).parent
        completed = _weft(
            ["index", str(directory), "--extract", extractor],
            workdir=workdir,
            timeout=_INDEX_TIMEOUT_SECONDS,
        )
        if completed.returncode != 0:
            message = (
                f"`weft index {directory} --extract {extractor}` exited "
                f"{completed.returncode}: {completed.stderr.strip()[-500:]}"
            )
            raise BaselineError(message)
        print(f"  indexed {document.id}: {completed.stdout.strip()}", file=sys.stderr)


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


def active_distributions(workdir: Path) -> tuple[DistributionRecord, ...]:
    """What `weft plugins list` reports, with each distribution's installed version.

    Read through the shipped command rather than by importing the discovery machinery, for the
    same reason the measurement is a subprocess: the set that mattered is the one the process
    that answered the questions actually had.
    """
    completed = _weft(["plugins", "list"], workdir=workdir, timeout=_ASK_TIMEOUT_SECONDS)
    if completed.returncode != 0:
        message = f"`weft plugins list` exited {completed.returncode}: {completed.stderr.strip()}"
        raise BaselineError(message)
    records: list[DistributionRecord] = []
    for line in completed.stdout.splitlines():
        name, _, rest = line.partition(":")
        status = rest.strip().split(" ", 1)[0]
        if not name or not status:
            continue
        try:
            installed = version(name.strip())
        except PackageNotFoundError:
            installed = "not-installed"
        records.append(DistributionRecord(name=name.strip(), version=installed, status=status))
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
    parser.add_argument("--repeats", type=int, default=3, help="how many times to run the pass")
    parser.add_argument("--top-k", type=int, default=10, dest="top_k")
    parser.add_argument("--depths", default="5,10", help="the k's to report at, comma separated")
    parser.add_argument("--embedder", default="openai", help="`[services] embed`")
    parser.add_argument("--store", default="qdrant", help="`[services] store`")
    parser.add_argument("--vector-size", type=int, default=DEFAULT_VECTOR_SIZE, dest="vector_size")
    parser.add_argument("--pdf-extractor", default=DEFAULT_EXTRACTORS[".pdf"], dest="pdf_extractor")
    parser.add_argument(
        "--text-extractor", default=DEFAULT_EXTRACTORS[".txt"], dest="text_extractor"
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=REPO_ROOT / ".baseline-run",
        help="where the staged corpus and the written weft.toml live",
    )
    parser.add_argument(
        "--reuse-index",
        action="store_true",
        dest="reuse_index",
        help="skip indexing and ask against whatever is already in the collection",
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
    tiers = parse_tiers(args.tiers)
    depths = parse_depths(args.depths, top_k=args.top_k)
    name, documents, declared = selected_documents(tiers)
    identity = corpus_id(documents)
    reproducible = all(tier.reproducible for tier in tiers)

    # The subset this run can score, derived from the manifest exactly as
    # `tests/docs/test_question_set.py` derives the published one: a question resting on a
    # document outside the selected tiers cannot be scored here, and which documents those are
    # is a fact about the corpus rather than anything written on a question.
    questions = reproducible_questions(
        load_questions(),
        tiers={document.id: document.tier.value for document in declared},
        reproducible=frozenset(tier.value for tier in tiers),
    )
    if not questions:
        message = f"no question can be scored from tier(s) {[tier.value for tier in tiers]}"
        raise BaselineError(message)

    workdir = Path(args.workdir).resolve()
    collection = f"weft_baseline_{identity[:12]}"
    write_config(
        workdir,
        embedder=args.embedder,
        store=args.store,
        collection=collection,
        vector_size=args.vector_size,
    )
    stage_corpus(documents, workdir)
    extractors = {
        ".pdf": args.pdf_extractor,
        ".txt": args.text_extractor,
        ".md": args.text_extractor,
    }
    known = {str(staged_path(document, workdir)): document.id for document in documents}

    started = time.monotonic()
    if not args.reuse_index:
        print(f"indexing {len(documents)} documents into {collection}", file=sys.stderr)
        index_corpus(documents, workdir=workdir, extractors=extractors)

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

    stages = _stage_records(
        extractors=extractors,
        embedder=args.embedder,
        store=args.store,
        collection=collection,
        top_k=args.top_k,
    )
    run = BaselineRun(
        recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        corpus=CorpusRecord(
            name=name,
            corpus_id=identity,
            tiers=tuple(tier.value for tier in tiers),
            documents=tuple(sorted(document.id for document in documents)),
        ),
        reproducible=reproducible,
        questions=tuple(sorted(question.id for question in questions)),
        repeats=args.repeats,
        retrieval_depth=args.top_k,
        pipeline=stages,
        pipeline_sha256=pipeline_digest(stages),
        models={"embed": f"{args.embedder}:{DEFAULT_MODEL}"},
        distributions=active_distributions(workdir),
        wall_clock_seconds=round(time.monotonic() - started, 3),
        metrics=aggregate(
            per_repetition, excluded=excluded, depths=depths, scored_counts=scored_counts
        ),
        excluded=tuple(excluded),
    )
    out = Path(args.out) if args.out else _default_out(run)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(run.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    return 0


def _accumulate(totals: dict[str, float], scores: Scores) -> None:
    """Add one question's scores into the running totals for this repetition."""
    for metric, value in scores.values.items():
        totals[metric] = totals.get(metric, 0.0) + value


def _stage_records(
    *,
    extractors: Mapping[str, str],
    embedder: str,
    store: str,
    collection: str,
    top_k: int,
) -> tuple[StageRecord, ...]:
    """What ran, as the digest-able record of it.

    The chunker's settings are read off the pack's own configuration model rather than retyped:
    `weft index` resolves `fixed-size` with no `with:` block, so its defaults *are* what ran, and
    a default that moves moves this record with it.
    """
    chunk = FixedSizeChunkerConfig()
    return (
        StageRecord(
            stage="extract",
            plugin=",".join(f"{suffix}={name}" for suffix, name in sorted(extractors.items())),
        ),
        StageRecord(
            stage="chunk",
            plugin="fixed-size",
            settings={"size": str(chunk.size), "overlap": str(chunk.overlap)},
        ),
        StageRecord(stage="embed", plugin=embedder),
        StageRecord(stage="store", plugin=store, settings={"collection": collection}),
        StageRecord(stage="search", plugin="vector-top-k", settings={"top_k": str(top_k)}),
    )


def _default_out(run: BaselineRun) -> Path:
    """`<corpus_id>-<date>.json`, with an unreproducible run saying so in its own name."""
    day = run.recorded_at.split("T", 1)[0]
    label = "" if run.reproducible else "-unreproducible"
    return BASELINES_DIR / f"{run.corpus.corpus_id[:12]}-{day}{label}.json"


if __name__ == "__main__":
    raise SystemExit(main())
