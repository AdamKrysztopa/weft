"""`eval/experiments/*.toml` — ledger task **38.0**: an experiment as a document.

Every experiment run in this tree so far has been its own script, with its own record shape and
its own arm-comparison rule invented on the spot. This module reads a **document** instead: the
arms, the question set, `repeats`, the metrics, the minimum detectable effect and an optional
`index_batch_size` are all written down before any run, so `weft eval experiment <path>`
(`weft_cli.eval_experiment`) can run every arm exactly as stated, index each distinct pipeline and
corpus once rather than once per arm, and refuse before indexing anything when two arms are not
comparable or a metric no run would record is named.

**A file on disk is data at rest, and it carries a version marker from its first release**, the
identical reasoning `weft_eval.question_set.QuestionSetFormat` and `weft_eval.corpus_manifest`'s
own module docstring already give for the files they read: a schema this module cannot read yet
is refused loudly, naming both versions, rather than misread as an older shape and silently
dropping a field the newer document actually stated.

**The digest is over the file's own bytes, never over the resolved model.** A resolved `corpus`/
`questions`/`manifest` path names the machine that loaded the document — the same committed file
checked out at two paths must still digest identically, which is exactly `weft_eval.run_record.
CorpusIdentity`'s own lesson (`docs/internal/lessons.md` `L17.2`) applied one layer up: a docstring
claiming a digest is "content-derived" while it is actually a path is how that survived being
written down the first time.

**Paths resolve against the document's own directory, not the caller's cwd** — `corpus/
manifest.toml`'s own footing (`weft_eval.corpus_manifest.load_manifest`): an experiment document is
committed and run from anywhere, so a relative `corpus =` line means "beside this file", never
"beside whatever directory the operator happened to be standing in".

**Unknown keys are refused, naming them, rather than silently ignored.** A `[experiment]` or
`[[arm]]` table is validated against exactly the keys this module reads; a typo in a field name
(`--questions` renamed to `question` by a slipped finger) would otherwise silently fall back to
this document's own defaults and run something other than what was written — `01` requirement 5's
rule, applied to a document rather than a CLI flag.

**What this module does not do.** It does not run a pipeline, index a corpus, or decide whether two
arms are comparable — that refusal needs a resolved pipeline and a corpus digest neither of which
this module can compute, and it is `weft_cli.eval_experiment`'s own job (ledger task 38.0's other
half). This module only reads the document and hands back a frozen, validated `Experiment`.
"""

from __future__ import annotations

import hashlib
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from weft_kernel.errors import WeftError

#: The schema this release of `weft-rag` reads. A document naming a higher number was written by
#: a newer `weft-rag` than this one — see `ExperimentSchemaError`.
EXPERIMENT_SCHEMA_VERSION: Final[int] = 1

#: Every key a `[experiment]` table may carry — `schema` is consumed here and carried on no
#: field of `Experiment` itself, the rest map one-to-one onto its fields.
_EXPERIMENT_TABLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "name",
        "questions",
        "corpus",
        "manifest",
        "repeats",
        "top_k",
        "metrics",
        "minimum_detectable_effect",
        "index_batch_size",
    }
)

#: Every key a `[[arm]]` table may carry — one-to-one onto `ExperimentArm`'s own fields.
_ARM_TABLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "name",
        "pipeline",
        "query_pipeline",
        "router",
        "corpus",
        "questions",
        "repeats",
        "capture_pool",
        "pool",
        "layers",
    }
)

#: Every top-level table a document may declare — see `load_experiment`'s own unknown-table
#: refusal. `[decision]`'s own keys are validated by `Decision` itself, the same way `[[arm]]`'s
#: are by `_ARM_TABLE_KEYS`/`ExperimentArm` together.
_TOP_LEVEL_TABLES: Final[frozenset[str]] = frozenset({"experiment", "arm", "decision"})


class ExperimentDocumentError(WeftError):
    """Stops an experiment before anything runs when its document is wrong.

    An experiment document could not be read as stated — missing, malformed TOML, an unknown
    key, or a value that cannot be run (`repeats < 2`, an empty `metrics`, two arms sharing one
    name...). The message names the file and the field that is wrong; see the module docstring.
    """


class ExperimentSchemaError(ExperimentDocumentError):
    """Tells the user to upgrade `weft-rag` rather than misread an experiment file.

    The document names a schema this `weft-rag` cannot read — newer than `EXPERIMENT_SCHEMA_
    VERSION`, or older than any release ever wrote (`< 1`). The message names the file, the
    schema it declares, the schema this release supports, and says to upgrade `weft-rag`.
    """


class Direction(StrEnum):
    """Which way a pre-registered decision's metric is better — see `Decision`."""

    HIGHER_IS_BETTER = "higher-is-better"
    LOWER_IS_BETTER = "lower-is-better"


class Decision(BaseModel):
    """An experiment's own pre-registered decision — task **44.8**.

    Which metric decides, the margin a difference must clear, and which direction is better —
    declared in a document's optional `[decision]` table, before anything runs. `weft_eval.
    evidence.render_evidence_table` reads this to print `weft_eval.verdict.verdict`'s reading of
    that metric's own paired interval, computed from the records rather than chosen after they
    are seen — see that module's own docstring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: str = Field(min_length=1)
    margin: float = Field(gt=0)
    direction: Direction


class ExperimentArm(BaseModel):
    """One variant under comparison, able to override the corpus, questions and repeats.

    One arm of an experiment — a pipeline, and optionally its own corpus/questions/query
    pipeline. `corpus`/`questions` are `None` when the arm inherits the experiment's own, resolved
    absolute paths when the arm names its own — see `Experiment.corpus_for`/`questions_for`.
    `repeats` is `None` when the arm inherits the document's own `repeats` — see
    `Experiment.repeats_for` (task **38.13**): a deterministic arm reaching no model declares its
    own `repeats = 1` rather than paying for repetitions that cannot vary.

    `capture_pool` (task **40.2**) marks this arm's run to write a `weft_eval.pool.PoolManifest`
    beside its record — refused by `weft_cli.eval_experiment` before anything runs unless
    `query_pipeline` ends in a `ContextPacker`, since a pool is what a retrieval rung packed.

    `pool` (task **40.2**'s second half) names a manifest this arm replays instead of indexing
    and retrieving — resolved against the document's own directory, `corpus`/`questions`' own
    footing. Refused alongside `capture_pool` on the identical arm: a replay reads a pool, it
    never writes one.

    `questions` (task **43.51**) is one or more resolved absolute paths, in the order named — see
    `Experiment.questions_for`.

    `router` (task **44.5**) names a `RoutingPolicy` document instead of a query rung: the arm
    answers each question through that router rather than through a fixed `query_pipeline`, and
    its record carries which rung answered each question. An arm names one or the other, never
    both — see `_router_and_query_pipeline_are_exclusive`.

    `layers` (task **44.55a**) names the layer pipelines this arm reads — a RAPTOR rung's summary
    tier, built by `weft index --layers` after the base index. Every arm shares one store and a
    layer once built stays in it for every arm scored after, so an arm naming fewer layers than an
    earlier one would read summaries it never asked for; `Experiment`'s own validator refuses a
    document whose arms do not name layers in a non-decreasing order. Empty for an arm reading
    none, and refused together with `pool`, since a replay reads a captured pool and no index.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    pipeline: str = Field(min_length=1)
    query_pipeline: str | None = None
    router: str | None = None
    corpus: Path | None = None
    questions: tuple[Path, ...] | None = None
    repeats: int | None = Field(default=None, ge=1)
    capture_pool: bool = False
    pool: Path | None = None
    layers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _capture_and_replay_are_exclusive(self) -> ExperimentArm:
        """Refuse an arm that both captures a pool and replays one.

        An arm cannot both `capture_pool` and name a `pool` to replay — see the class
        docstring's own paragraph. Checked here, at load, rather than left for `weft_cli.
        eval_experiment` to notice mid-run: a replay reads a pool, it never writes one, so the
        two keys on one arm can never both be honoured.
        """
        if self.capture_pool and self.pool is not None:
            raise ValueError(
                f"arm '{self.name}' sets both capture_pool and pool — a replay reads a pool, "
                "it never writes one. Remove one of the two keys."
            )
        return self

    @model_validator(mode="after")
    def _router_and_query_pipeline_are_exclusive(self) -> ExperimentArm:
        """Refuse an arm that names both a router and a query pipeline — ledger task **44.5**.

        An arm answers through one or the other: a fixed `query_pipeline`, or a `router` that
        picks one per question. Naming both would leave `weft_cli.eval_experiment` to pick
        silently, which is exactly the ambiguity this module refuses at load rather than at run.
        """
        if self.router is not None and self.query_pipeline is not None:
            raise ValueError(
                f"arm '{self.name}' names both a router and a query_pipeline — an arm answers "
                "through one or the other."
            )
        return self

    @model_validator(mode="after")
    def _layers_are_named_once_each(self) -> ExperimentArm:
        """Refuse an arm naming one layer twice — ledger task **44.55a**."""
        seen: set[str] = set()
        for layer in self.layers:
            if layer in seen:
                raise ValueError(f"arm '{self.name}' names layer '{layer}' more than once.")
            seen.add(layer)
        return self

    @model_validator(mode="after")
    def _pool_and_layers_are_exclusive(self) -> ExperimentArm:
        """Refuse an arm that both replays a pool and names layers — ledger task **44.55a**.

        A replay reads a captured pool and no index, so a layer it names would never be read.
        """
        if self.pool is not None and self.layers:
            raise ValueError(
                f"arm '{self.name}' sets both pool and layers — a replay reads a pool and no "
                "index, so the layers it names would never be read."
            )
        return self


class Experiment(BaseModel):
    """An experiment, read from a document — see the module docstring.

    `digest` is a sha256 over the document's own bytes, computed by `load_experiment`, never over
    this resolved model.

    `questions` (task **43.51**) is one or more resolved absolute paths, in the order the
    document names them — a document writing one path keeps today's single-file shape exactly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    questions: tuple[Path, ...] = Field(min_length=1)
    corpus: Path
    manifest: Path | None = None
    repeats: int = Field(ge=2)
    top_k: int = Field(ge=1)
    cutoffs: tuple[int, ...] = Field(min_length=1)
    metrics: tuple[str, ...] = Field(min_length=1)
    minimum_detectable_effect: float = Field(gt=0)
    index_batch_size: int | None = Field(default=None, ge=1)
    arms: tuple[ExperimentArm, ...]
    decision: Decision | None = None

    @model_validator(mode="before")
    @classmethod
    def _cutoffs_from_top_k(cls, data: Any) -> Any:
        """A document writes only `top_k` — an int names one cutoff, a list names several.

        This expands either spelling into the declared `top_k` (the largest, and so the retrieval
        depth every question's ranking is collapsed to) plus `cutoffs` (every declared depth, sorted
        ascending and de-duplicated) before field validation runs. A document may not write
        `cutoffs` itself; `extra="forbid"` still refuses it.
        """
        if not isinstance(data, dict):
            return data
        document = cast("dict[str, Any]", data)
        if "top_k" not in document:
            return document
        raw: Any = document["top_k"]
        if raw is None or isinstance(raw, bool):
            return document
        if isinstance(raw, int):
            return {**document, "cutoffs": (raw,)}
        if isinstance(raw, (list, tuple)):
            entries = cast("list[Any] | tuple[Any, ...]", raw)
            if not entries:
                raise ValueError("top_k names no cutoff — declare at least one retrieval depth.")
            cutoffs: list[int] = []
            for value in entries:
                if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                    raise ValueError(
                        f"top_k names {value!r} as a cutoff, and every cutoff must be a "
                        f"positive integer."
                    )
                cutoffs.append(value)
            ordered = tuple(sorted(set(cutoffs)))
            return {**document, "top_k": max(ordered), "cutoffs": ordered}
        return document

    @field_validator("arms")
    @classmethod
    def _at_least_two_distinctly_named_arms(
        cls, arms: tuple[ExperimentArm, ...]
    ) -> tuple[ExperimentArm, ...]:
        if len(arms) < 2:
            raise ValueError(
                "an experiment needs at least two arms — with one arm there is nothing to "
                "compare it against"
            )
        seen: set[str] = set()
        for arm in arms:
            if arm.name in seen:
                raise ValueError(f"two arms are both named '{arm.name}'")
            seen.add(arm.name)
        return arms

    @model_validator(mode="after")
    def _decision_names_a_measured_metric(self) -> Experiment:
        """`[decision]`'s own `metric` must be one the experiment actually measures.

        A pre-registered decision over a metric no run will score can never be read — task
        **44.8**. Checked here, after `metrics` and `decision` have each validated on their own,
        since the refusal names both.
        """
        if self.decision is not None and self.decision.metric not in self.metrics:
            raise ValueError(
                f"[decision] names metric '{self.decision.metric}', which is not among the "
                f"experiment's own metrics: {', '.join(self.metrics)}."
            )
        return self

    @model_validator(mode="after")
    def _layers_only_grow_across_arms(self) -> Experiment:
        """Refuse an arm naming fewer layers than an earlier arm — ledger task **44.55a**.

        Every non-pool arm shares one store, and a layer once built stays there for every arm
        scored after it — `vector-top-k` does not filter derived nodes out. So walking the arms
        in document order, the set of layers named must only grow; an arm falling short of an
        earlier arm's layers would read a layer it never asked for.
        """
        built_by: dict[str, str] = {}
        for arm in self.arms:
            if arm.pool is not None:
                continue
            named = set(arm.layers)
            for layer, earlier in built_by.items():
                if layer not in named:
                    raise ValueError(
                        f"arm '{arm.name}' does not name layer '{layer}', which arm "
                        f"'{earlier}' builds before it — arms share one store, so every arm "
                        f"reads every layer already built there. Order the arms so the layers "
                        f"each names only grow."
                    )
            for layer in arm.layers:
                built_by.setdefault(layer, arm.name)
        return self

    def corpus_for(self, arm: ExperimentArm) -> Path:
        """`arm`'s own corpus, or the experiment's, when the arm names none."""
        return arm.corpus if arm.corpus is not None else self.corpus

    def questions_for(self, arm: ExperimentArm) -> tuple[Path, ...]:
        """`arm`'s own question files, or the experiment's, when the arm names none."""
        return arm.questions if arm.questions is not None else self.questions

    def repeats_for(self, arm: ExperimentArm) -> int:
        """The repetition count that applies to `arm`.

        `arm`'s own repetition count, or the experiment's, when the arm names none — the one
        place every loop and completeness check reads (task **38.13**).
        """
        return arm.repeats if arm.repeats is not None else self.repeats


def _resolve(raw: object, *, root: Path) -> Path:
    return (root / str(raw)).resolve()


def _resolve_optional(raw: object, *, root: Path) -> Path | None:
    return None if raw is None else _resolve(raw, root=root)


def _resolve_questions(raw: object, *, root: Path, path: Path) -> tuple[Path, ...]:
    """`questions =` as one path or a list of them — always a non-empty tuple, in file order.

    A bare string names one file, the shape every experiment document wrote before task
    **43.51**. A list names several, read as their union (`weft_eval.question_set.
    read_question_sets`); an empty list is refused here, naming the field, rather than reaching
    `read_question_sets` as a set of nothing to score.
    """
    if isinstance(raw, list):
        entries = cast("list[Any]", raw)
        if not entries:
            raise ExperimentDocumentError(
                f"{path.name}: 'questions' names no question file — state at least one path."
            )
        return tuple(_resolve(entry, root=root) for entry in entries)
    return (_resolve(raw, root=root),)


def _resolve_optional_questions(raw: object, *, root: Path, path: Path) -> tuple[Path, ...] | None:
    return None if raw is None else _resolve_questions(raw, root=root, path=path)


def _refused_from(exc: ValidationError, path: Path) -> ExperimentDocumentError:
    """Narrow `exc` to `ExperimentDocumentError`'s field-naming shape.

    `exc`, narrowed to `ExperimentDocumentError`'s own field-naming shape — the first error
    pydantic reports, since one refusal at a time is what a document author can act on.
    """
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "(the document)"
    return ExperimentDocumentError(f"{path.name}: {field}: {first['msg']}")


def _build_arm(entry: dict[str, Any], *, root: Path, path: Path) -> ExperimentArm:
    unknown = set(entry) - _ARM_TABLE_KEYS
    if unknown:
        key = sorted(unknown)[0]
        raise ExperimentDocumentError(
            f"{path.name}: [[arm]] names an unknown key '{key}'. Valid keys: "
            f"{', '.join(sorted(_ARM_TABLE_KEYS))}."
        )
    return ExperimentArm(
        name=str(entry.get("name", "")),
        pipeline=str(entry.get("pipeline", "")),
        query_pipeline=entry.get("query_pipeline"),
        router=entry.get("router"),
        corpus=_resolve_optional(entry.get("corpus"), root=root),
        questions=_resolve_optional_questions(entry.get("questions"), root=root, path=path),
        repeats=entry.get("repeats"),
        capture_pool=bool(entry.get("capture_pool", False)),
        pool=_resolve_optional(entry.get("pool"), root=root),
        layers=tuple(entry.get("layers", ())),
    )


def _build_decision(decision_table: dict[str, Any] | None) -> Decision | None:
    if decision_table is None:
        return None
    return Decision.model_validate(decision_table)


def _build_experiment(
    experiment_table: Any,
    arm_entries: list[dict[str, Any]],
    decision_table: dict[str, Any] | None,
    *,
    digest: str,
    root: Path,
    path: Path,
) -> Experiment:
    """The `Experiment` the document's tables describe; pydantic's refusal propagates."""
    arms = tuple(_build_arm(entry, root=root, path=path) for entry in arm_entries)
    return Experiment(
        name=str(experiment_table.get("name", "")),
        digest=digest,
        questions=_resolve_questions(experiment_table.get("questions", ""), root=root, path=path),
        corpus=_resolve(experiment_table.get("corpus", ""), root=root),
        manifest=_resolve_optional(experiment_table.get("manifest"), root=root),
        repeats=experiment_table.get("repeats"),
        top_k=experiment_table.get("top_k"),
        cutoffs=(),  # derived from `top_k` by `_cutoffs_from_top_k`
        metrics=tuple(experiment_table.get("metrics", ())),
        minimum_detectable_effect=experiment_table.get("minimum_detectable_effect"),
        index_batch_size=experiment_table.get("index_batch_size"),
        arms=arms,
        decision=_build_decision(decision_table),
    )


def load_experiment(path: Path) -> Experiment:
    """Parse and digest an experiment file, so its records can be matched to this exact text.

    Read `path` as an experiment document — see the module docstring for what each part
    means and what is refused.

    Raises `ExperimentDocumentError` for a missing file, malformed TOML, an unknown key, or a
    value that cannot be run; `ExperimentSchemaError` (a subclass) for a schema this release does
    not read. Every refusal names `path.name` and the field, key or schema version that is wrong.
    """
    if not path.is_file():
        raise ExperimentDocumentError(f"no experiment document at '{path.name}'.")

    raw_bytes = path.read_bytes()
    digest = hashlib.sha256(raw_bytes).hexdigest()
    try:
        raw = tomllib.loads(raw_bytes.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ExperimentDocumentError(f"{path.name} is not valid TOML: {exc}") from exc

    unknown_tables = set(raw) - _TOP_LEVEL_TABLES
    if unknown_tables:
        name = sorted(unknown_tables)[0]
        raise ExperimentDocumentError(
            f"{path.name} names an unknown table '[{name}]'. Valid tables: "
            f"{', '.join(f'[{t}]' for t in sorted(_TOP_LEVEL_TABLES))}."
        )

    try:
        experiment_table = raw["experiment"]
    except KeyError as exc:
        raise ExperimentDocumentError(f"{path.name} has no [experiment] table.") from exc

    if "schema" not in experiment_table:
        raise ExperimentDocumentError(
            f"{path.name} names no 'schema' in [experiment] — every experiment document states "
            f"the schema version it was written for."
        )
    schema = experiment_table["schema"]
    if isinstance(schema, bool) or not isinstance(schema, int) or schema < 1:
        raise ExperimentDocumentError(
            f"{path.name}: schema {schema!r} is not a schema any release of weft-rag has ever "
            f"written — a schema is a positive integer."
        )
    if schema > EXPERIMENT_SCHEMA_VERSION:
        raise ExperimentSchemaError(
            f"{path.name} names schema {schema}, and this weft-rag reads schema "
            f"{EXPERIMENT_SCHEMA_VERSION} — upgrade weft-rag to read a document written for a "
            f"different schema."
        )

    unknown = set(experiment_table) - _EXPERIMENT_TABLE_KEYS
    if unknown:
        key = sorted(unknown)[0]
        raise ExperimentDocumentError(
            f"{path.name}: [experiment] names an unknown key '{key}'. Valid keys: "
            f"{', '.join(sorted(_EXPERIMENT_TABLE_KEYS))}."
        )

    root = path.resolve().parent
    arm_entries = raw.get("arm", [])
    decision_table = raw.get("decision")

    try:
        return _build_experiment(
            experiment_table,
            arm_entries,
            decision_table,
            digest=digest,
            root=root,
            path=path,
        )
    except ValidationError as exc:
        raise _refused_from(exc, path) from exc


__all__ = [
    "EXPERIMENT_SCHEMA_VERSION",
    "Decision",
    "Direction",
    "Experiment",
    "ExperimentArm",
    "ExperimentDocumentError",
    "ExperimentSchemaError",
    "load_experiment",
]
