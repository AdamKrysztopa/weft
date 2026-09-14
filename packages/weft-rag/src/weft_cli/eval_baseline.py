"""`weft eval baseline` — ledger repair **R22.4c**: the procedure that produced the published
baseline, taken in process rather than by shelling out to `weft index`/`weft ask`.

`docs/09-release.md` §5.2 fails a release if reproducing its published number requires a
checkout: the deleted `eval/run_baseline.py` was exactly that requirement, a hand-run script that
existed only because `weft` had to be reached as a subprocess. Since R22.4a carried the scorer
(`weft_eval.baseline`), the question set reader (`weft_eval.question_set`) and the manifest reader
(`weft_eval.corpus_manifest`) into the installed `weft-rag` wheel, the one piece still living
outside it was the *procedure* — select a manifest's tiers, verify their bytes, stage them, index
them through a named pipeline, retrieve every scoreable question more than once, score, and write
a `BaselineReport` the published files' own reader already loads. This module is that procedure,
as an ordinary `weft` command: no `sys.path` manipulation, no second `asyncio.run` (this is not
`eval/`, so fitness function 7(a) does not apply to it, and there is exactly one already, at the
CLI's own entry point), no subprocess — the integration test patches `subprocess.run`/`Popen` to
raise, and the run still completes.

**Every refusal below happens before anything under `--workdir` is created.** Parsing `--tiers`
and `--depths`, checking an explicit `--out` for a collision, loading and verifying the manifest —
all four happen before `_stage_corpus` ever writes a byte, so a caller who mistyped a tier or
named an existing report never pays for a staged corpus it is about to refuse anyway.

**A store holding a passage this run did not stage is refused, not silently dropped.** The
deleted script quietly excluded a retrieved passage attributed to no staged document from
`Hit.documents`; that reads as a worse retrieval score when the real defect is a store an earlier
run left dirty. `BaselineStoreNotIsolatedError` refuses instead, at the first such passage, naming
it, the store plugin, and the remedy — point the store at a collection holding nothing but this
run's own corpus.

**The pipeline defaults to the shipped `baseline` document** (`pipelines/baseline.yaml`) —
single-vector top-k, `09` §4.3 V3's own definition of what a baseline measures: no fusion, no
rerank, no enhancement. A caller may name any other resolvable pipeline through `--pipeline`; this
module has no opinion beyond deriving its extractor, embedder and store stages generically, the
same walk `weft_cli.eval_scoring.score_pipeline` already performs for `weft eval run --questions`.

**The corpus digest is over manifest identity, not filesystem paths** —
`weft_eval.run_record.CorpusDigestBasis.MANIFEST_DIGESTS`, new at this repair: `f"{id}\t{sha256}"`
per document, those bytes already verified against that sha256 before the run. A resolved,
staged path (`CorpusDigestBasis.DOCUMENT_BYTES`, every other command's basis) would tie the digest
to *where this run happened to stage the corpus*; a manifest id is stable across any staging.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field

from weft_cli.ask import run_ask
from weft_cli.eval_commands import model_versions_of
from weft_cli.eval_scoring import PipelineNotRetrievableError
from weft_cli.ingest import corpus_documents, run_index_for
from weft_cli.installed_versions import active_distribution_versions
from weft_command.contract import Command, CommandResult
from weft_command.permission import PermissionClass
from weft_embed import Embedder
from weft_engine.registry_bootstrap import Dependencies
from weft_eval.baseline import (
    BaselineReport,
    DepthTooShallowError,
    Excluded,
    Hit,
    Unscoreable,
    aggregate_repetitions,
    measure,
)
from weft_eval.corpus_manifest import (
    CorpusManifest,
    DocumentStatus,
    ManifestDocument,
    Tier,
    load_manifest,
    verify_document,
)
from weft_eval.question_set import Question, load_questions, reproducible_questions
from weft_eval.run_record import CorpusDigestBasis, RunDurations, build_run_record, corpus_identity
from weft_extract import Extractor, SourceDoc
from weft_kernel.context import Context
from weft_kernel.discovery import PackRegistrar
from weft_kernel.errors import WeftError
from weft_kernel.payload import Node, Outcome, Produced
from weft_kernel.registry import Registry
from weft_kernel.resolution import ResolvedPipeline, ResolvedStage
from weft_store import NodeStore, Scored

_EVAL_BASELINE_HELP = (
    "take the baseline `09` §4.3 V3 asks for, in process: stage a manifest's tiers, verify "
    "their bytes, index them through a named pipeline (default: the shipped 'baseline' "
    "document), retrieve every scoreable question more than once and write a BaselineReport "
    "the published files' own reader loads — no checkout, no 'weft' subprocess"
)


class BaselineRunError(WeftError):
    """`weft eval baseline` cannot take the run it was asked for, and taking a different one
    silently would be worse — see the module docstring for the whole family of refusals this
    covers: an unknown tier, a document that fails its own manifest digest, a corpus with
    nothing to score.
    """


class BaselineStoreNotIsolatedError(BaselineRunError):
    """A retrieved passage traces to a source this run never staged.

    The store this run searched holds at least one document outside this run's own corpus, which
    changes the ranks — and so the number — for every question. See the module docstring's own
    paragraph on why this refuses rather than silently dropping the passage, as the deleted
    `eval/run_baseline.py` did.
    """


class BaselineOutputExistsError(BaselineRunError):
    """`--out`, or the name this run would otherwise choose, already names a file on disk.

    Refusing rather than overwriting: a baseline is a number somebody may already be comparing
    a later run against, and overwriting it silently would make that comparison retroactively
    describe a run that never happened.
    """


class EvalBaselineArgs(BaseModel):
    """`weft eval baseline <manifest> <questions>` — every field is `--help` text as well as a
    parameter; see the module docstring for what each one controls.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest: str = Field(
        description="the corpus manifest — the release archive ships it as 'corpus-manifest.toml'"
    )
    questions: str = Field(description="the directory of question-set TOML files")
    pipeline: str = Field(
        default="baseline",
        description=(
            "the pipeline document to resolve and index through — defaults to the shipped "
            "'baseline' document, '09' §4.3 V3's own single-vector-top-k definition"
        ),
    )
    tiers: str = Field(
        default="fetch",
        description="comma-separated corpus tiers to select from the manifest",
    )
    repeats: int = Field(
        default=3,
        ge=2,
        description=(
            "how many times to retrieve and score every question — fewer than two repetitions "
            "records no interval, so this is refused as an argument"
        ),
    )
    top_k: int = Field(default=10, ge=1, description="how many passages to retrieve per question")
    depths: str = Field(
        default="5,10", description="comma-separated k's to report metrics at, each at most --top-k"
    )
    workdir: str = Field(
        default=".weft-baseline", description="where this run stages the corpus it indexes"
    )
    out: str | None = Field(
        default=None,
        description=(
            "where to write the report — defaults to "
            "'baselines/<corpus-digest>-<date>[-unreproducible].json', the published files' own "
            "naming"
        ),
    )


class EvalBaselineCommandResult(CommandResult):
    """`weft eval baseline`'s whole answer — where the report landed, and the report itself."""

    path: str
    report: BaselineReport


def _parse_tiers(raw: str) -> tuple[Tier, ...]:
    """`--tiers fetch,operator` as members, in the order given, refusing an unknown name by
    listing every real one.
    """
    pieces = tuple(dict.fromkeys(piece.strip() for piece in raw.split(",")))
    tiers: list[Tier] = []
    for name in pieces:
        try:
            tiers.append(Tier(name))
        except ValueError as exc:
            message = (
                f"{name!r} is not a corpus tier. The manifest declares "
                f"{[tier.value for tier in Tier]}."
            )
            raise BaselineRunError(message) from exc
    return tuple(tiers)


def _parse_depths(raw: str, *, top_k: int) -> tuple[int, ...]:
    """`--depths 5,10` as sorted, de-duplicated integers, refused when one is deeper than
    `--top-k`, or when a piece is not an integer at all.
    """
    parsed: list[int] = []
    for piece in raw.split(","):
        text = piece.strip()
        try:
            parsed.append(int(text))
        except ValueError as exc:
            message = f"{text!r} in --depths {raw!r} is not an integer."
            raise BaselineRunError(message) from exc
    depths = tuple(sorted(dict.fromkeys(parsed)))
    too_deep = [depth for depth in depths if depth > top_k]
    if too_deep:
        message = (
            f"depths {too_deep} are deeper than --top-k {top_k}. A metric's name must state "
            f"the k it computed."
        )
        raise DepthTooShallowError(message)
    return depths


def _refuse_if_exists(path: Path) -> None:
    """`BaselineOutputExistsError`, naming `path`, when it already exists."""
    if path.exists():
        message = (
            f"'{path}' already exists. 'weft eval baseline' refuses to overwrite a published "
            f"run — remove it first, or point --out somewhere else."
        )
        raise BaselineOutputExistsError(message)


def _select_documents(
    manifest: CorpusManifest, *, tiers: Sequence[Tier]
) -> tuple[ManifestDocument, ...]:
    """Every manifest document whose tier is in `tiers`, in manifest order — refused if none."""
    wanted = frozenset(tiers)
    selected = tuple(document for document in manifest.documents if document.tier in wanted)
    if not selected:
        message = (
            f"no document in the manifest '{manifest.name}' is in tier(s) "
            f"{[tier.value for tier in tiers]}."
        )
        raise BaselineRunError(message)
    return selected


def _verify_selected(selected: Sequence[ManifestDocument]) -> None:
    """`BaselineRunError`, listing every document that does not verify against its own sha256."""
    failing = [
        (document, status)
        for document in selected
        if (status := verify_document(document)) is not DocumentStatus.OK
    ]
    if failing:
        listed = ", ".join(f"{document.id} ({status.value})" for document, status in failing)
        message = (
            f"{len(failing)} of {len(selected)} selected document(s) do not verify against the "
            f"manifest's own sha256: {listed}. The fetch tier is materialised by "
            f"'fetch_corpus.py fetch'; the operator tier is placed by hand."
        )
        raise BaselineRunError(message)


def _stage_corpus(
    selected: Sequence[ManifestDocument], workdir: Path
) -> tuple[Path, dict[str, str]]:
    """Copy each selected document under `workdir`, named by its manifest id, and hand back the
    corpus directory and a map from each staged path (resolved, as a string) to that id.
    """
    corpus_dir = workdir / "corpus"
    known: dict[str, str] = {}
    for document in selected:
        suffix = document.path.suffix
        target = (
            corpus_dir / suffix.lstrip(".") / document.id / f"{document.id}{suffix}"
        ).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.stat().st_size != document.path.stat().st_size:
            shutil.copyfile(document.path, target)
        known[str(target)] = document.id
    return corpus_dir, known


def _readable_ids(docs: Sequence[SourceDoc], *, known: Mapping[str, str]) -> tuple[str, ...]:
    """The manifest ids of every staged document the resolved pipeline actually reads, sorted."""
    ids = {
        known[resolved]
        for doc in docs
        if (resolved := str(Path(str(doc.source_id)).resolve())) in known
    }
    return tuple(sorted(ids))


def _kept_questions(
    questions: Sequence[Question],
    *,
    manifest: CorpusManifest,
    tiers: Sequence[Tier],
    readable: Sequence[str],
) -> tuple[Question, ...]:
    """Every question this run can honestly score: its tiers reproducible, and every document
    its ground truth names among what this run actually indexed.
    """
    tier_of = {document.id: document.tier.value for document in manifest.documents}
    reproducible = reproducible_questions(
        questions,
        tiers=tier_of,
        reproducible=frozenset(tier.value for tier in tiers),
    )
    readable_ids = frozenset(readable)
    return tuple(
        question
        for question in reproducible
        if frozenset(question.relevant_documents) <= readable_ids
    )


def _retrieval_stages(resolved: ResolvedPipeline) -> tuple[ResolvedStage, ResolvedStage]:
    """The one `Embedder` stage and the one `NodeStore` stage `resolved` names, or a refusal."""
    embed_stage = next((s for s in resolved.stages if s.contract == Embedder.__name__), None)
    store_stage = next((s for s in resolved.stages if s.contract == NodeStore.__name__), None)
    if embed_stage is None or store_stage is None:
        missing = "Embedder" if embed_stage is None else "NodeStore"
        raise PipelineNotRetrievableError(
            f"pipeline '{resolved.name}' has no stage registered under the {missing} contract, "
            f"so 'weft eval baseline' has nothing to retrieve against.",
            pipeline=resolved.name,
        )
    return embed_stage, store_stage


def _extractor_use(resolved: ResolvedPipeline) -> str:
    """The plugin name of the one `Extractor` stage `resolved` names."""
    stage = next((s for s in resolved.stages if s.contract == Extractor.__name__), None)
    return stage.use if stage is not None else ""


def _factory_config(config: object) -> object:
    """`config` narrowed to what a plugin's own factory actually expects — the identical
    narrowing `weft_cli.eval_scoring._factory_config`/`weft_cli.compile.to_specs` already carry,
    reimplemented here rather than imported: both are private to their own module.
    """
    return config if isinstance(config, BaseModel) else None


def _built_hits(
    hits: Sequence[Scored[Node]], *, known: Mapping[str, str], store_use: str
) -> tuple[Hit, ...]:
    """`hits`, ranked and reattributed to manifest ids — refusing at once, naming the source and
    the store, for a passage this run never staged. See the module docstring's own paragraph.
    """
    built: list[Hit] = []
    for index, hit in enumerate(hits):
        documents: list[str] = []
        for source in hit.value.lineage.sources:
            resolved = str(source)
            manifest_id = known.get(resolved)
            if manifest_id is None:
                message = (
                    f"a retrieved passage traces to {resolved!r}, which this run did not "
                    f"stage — the '{store_use}' store holds at least one document outside this "
                    f"run's own corpus, which changes every question's ranks. Point it at a "
                    f"collection holding nothing but this run's corpus (for Qdrant, "
                    f"'[packs.qdrant] collection')."
                )
                raise BaselineStoreNotIsolatedError(message)
            documents.append(manifest_id)
        built.append(
            Hit(
                rank=index + 1,
                node_id=str(hit.value.id),
                score=hit.score,
                documents=tuple(sorted(documents)),
                content=hit.value.content,
            )
        )
    return tuple(built)


async def _score_repetitions(
    questions: Sequence[Question],
    *,
    registry: Registry,
    ctx: Context,
    top_k: int,
    depths: Sequence[int],
    embed_stage: ResolvedStage,
    store_stage: ResolvedStage,
    known: Mapping[str, str],
    repeats: int,
) -> tuple[list[dict[str, float]], list[int], list[Excluded]]:
    """Retrieve and score every question, `repeats` times — the per-repetition means, how many
    questions each repetition scored, and every exclusion with its reason.
    """
    per_repetition: list[dict[str, float]] = []
    scored_counts: list[int] = []
    excluded: list[Excluded] = []
    for repetition in range(1, repeats + 1):
        totals: dict[str, float] = {}
        scored = 0
        for question in questions:
            hits = await run_ask(
                question.text,
                registry=registry,
                ctx=ctx,
                top_k=top_k,
                embedder=embed_stage.use,
                store=store_stage.use,
                embedder_config=_factory_config(embed_stage.config),
                store_config=_factory_config(store_stage.config),
            )
            built = _built_hits(hits, known=known, store_use=store_stage.use)
            result = measure(question, built, depths=depths, retrieval_depth=top_k)
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
            for metric, value in result.values.items():
                totals[metric] = totals.get(metric, 0.0) + value
        if not scored:
            message = f"repetition {repetition} of {repeats} scored no question at all."
            raise BaselineRunError(message)
        per_repetition.append({metric: total / scored for metric, total in totals.items()})
        scored_counts.append(scored)
    return per_repetition, scored_counts, excluded


def _default_out(report: BaselineReport) -> Path:
    """`baselines/<corpus-digest>-<date>[-unreproducible].json`, the published files' own naming."""
    day = report.recorded_at.split("T", 1)[0]
    label = "" if report.reproducible else "-unreproducible"
    return Path("baselines") / f"{report.record.corpus.digest[:12]}-{day}{label}.json"


class EvalBaselineCommand:
    """`weft eval baseline` — see the module docstring."""

    args_model: ClassVar[type[BaseModel]] = EvalBaselineArgs
    result_model: ClassVar[type[CommandResult]] = EvalBaselineCommandResult
    permission_class: ClassVar[PermissionClass] = PermissionClass.WRITE
    help: ClassVar[str] = _EVAL_BASELINE_HELP

    def __init__(self, config: object = None) -> None:
        del config

    async def run(self, args: BaseModel, ctx: Context) -> Outcome[CommandResult]:
        baseline_args = cast(EvalBaselineArgs, args)
        deps = ctx.require(Dependencies)
        started = time.monotonic()

        tiers = _parse_tiers(baseline_args.tiers)
        depths = _parse_depths(baseline_args.depths, top_k=baseline_args.top_k)
        explicit_out = Path(baseline_args.out) if baseline_args.out is not None else None
        if explicit_out is not None:
            _refuse_if_exists(explicit_out)

        manifest = load_manifest(Path(baseline_args.manifest))
        selected = _select_documents(manifest, tiers=tiers)
        _verify_selected(selected)

        workdir = Path(baseline_args.workdir)
        corpus_dir, known = _stage_corpus(selected, workdir)

        resolved, _specs, docs = corpus_documents(
            corpus_dir,
            pipeline=baseline_args.pipeline,
            registry=deps.registry,
            reports=deps.reports,
            contributions=deps.contributions,
        )
        readable = _readable_ids(docs, known=known)
        if not readable:
            message = (
                f"pipeline '{baseline_args.pipeline}' reads nothing under the staged corpus — "
                f"nothing this run indexed can be reported on."
            )
            raise BaselineRunError(message)

        all_questions = load_questions(Path(baseline_args.questions))
        kept = _kept_questions(all_questions, manifest=manifest, tiers=tiers, readable=readable)
        if not kept:
            message = (
                f"no question can be scored from tier(s) {[tier.value for tier in tiers]} and "
                f"the {len(readable)} document(s) '{baseline_args.pipeline}' actually reads."
            )
            raise BaselineRunError(message)

        embed_stage, store_stage = _retrieval_stages(resolved)
        extractor_use = _extractor_use(resolved)

        ingest_started = time.monotonic()
        # A wall-clock-timed ingest must not silently skip an unchanged document (ledger task
        # 17.0).
        await run_index_for(
            deps, corpus_dir, ctx=ctx, pipeline=baseline_args.pipeline, reprocess=True
        )
        ingest_seconds = time.monotonic() - ingest_started

        query_started = time.monotonic()
        per_repetition, scored_counts, excluded = await _score_repetitions(
            kept,
            registry=deps.registry,
            ctx=ctx,
            top_k=baseline_args.top_k,
            depths=depths,
            embed_stage=embed_stage,
            store_stage=store_stage,
            known=known,
            repeats=baseline_args.repeats,
        )
        query_seconds = time.monotonic() - query_started

        metrics = aggregate_repetitions(
            per_repetition, excluded=excluded, depths=depths, scored_counts=scored_counts
        )

        by_id = {document.id: document for document in selected}
        readable_documents = tuple(by_id[identifier] for identifier in readable)
        record = build_run_record(
            recorded_at=datetime.now(UTC).isoformat(),
            resolved_pipeline=resolved,
            corpus=corpus_identity(
                manifest.name,
                (f"{document.id}\t{document.sha256}" for document in readable_documents),
            ),
            corpus_digest_basis=CorpusDigestBasis.MANIFEST_DIGESTS,
            model_versions=model_versions_of(resolved, roles=deps.llm.roles),
            reports=deps.reports,
            distribution_versions=active_distribution_versions(deps.reports),
            durations=RunDurations(ingest_seconds=ingest_seconds, query_seconds=query_seconds),
        )

        reproducible = all(tier.reproducible for tier in tiers)
        report = BaselineReport(
            recorded_at=datetime.now(UTC).isoformat(timespec="seconds"),
            corpus_name=manifest.name,
            tiers=tuple(tier.value for tier in tiers),
            extractor=extractor_use,
            documents=readable,
            reproducible=reproducible,
            record=record,
            questions=tuple(sorted(question.id for question in kept)),
            repeats=baseline_args.repeats,
            retrieval_depth=baseline_args.top_k,
            wall_clock_seconds=round(time.monotonic() - started, 3),
            metrics=metrics,
            excluded=tuple(excluded),
        )

        out_path = explicit_out if explicit_out is not None else _default_out(report)
        _refuse_if_exists(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")

        return Produced(value=EvalBaselineCommandResult(path=str(out_path), report=report))


def register_eval_baseline_command(registrar: PackRegistrar) -> None:
    """Register `eval baseline` — called from `weft_cli.commands.register`, right after
    `register_eval_commands`, never from a second entry point.
    """
    registrar.add(Command, "eval baseline", EvalBaselineCommand)


__all__ = [
    "BaselineOutputExistsError",
    "BaselineRunError",
    "BaselineStoreNotIsolatedError",
    "EvalBaselineArgs",
    "EvalBaselineCommand",
    "EvalBaselineCommandResult",
    "register_eval_baseline_command",
]
