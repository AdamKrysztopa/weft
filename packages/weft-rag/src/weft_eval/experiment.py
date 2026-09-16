"""`eval/experiments/*.toml` — ledger task **38.0**: an experiment as a document.

Every experiment run in this tree so far has been its own script, with its own record shape and
its own arm-comparison rule invented on the spot. This module reads a **document** instead: the
arms, the question set, `repeats`, the metrics and the minimum detectable effect are all written
down before any run, so `weft eval experiment <path>` (`weft_cli.eval_experiment`) can run every
arm exactly as stated and refuse before indexing anything when two arms are not comparable.

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
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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
    }
)

#: Every key a `[[arm]]` table may carry — one-to-one onto `ExperimentArm`'s own fields.
_ARM_TABLE_KEYS: Final[frozenset[str]] = frozenset(
    {"name", "pipeline", "query_pipeline", "corpus", "questions"}
)


class ExperimentDocumentError(WeftError):
    """An experiment document could not be read as stated — missing, malformed TOML, an unknown
    key, or a value that cannot be run (`repeats < 2`, an empty `metrics`, two arms sharing one
    name...). The message names the file and the field that is wrong; see the module docstring.
    """


class ExperimentSchemaError(ExperimentDocumentError):
    """The document names a schema this `weft-rag` cannot read — newer than `EXPERIMENT_SCHEMA_
    VERSION`, or older than any release ever wrote (`< 1`). The message names the file, the
    schema it declares, the schema this release supports, and says to upgrade `weft-rag`.
    """


class ExperimentArm(BaseModel):
    """One arm of an experiment — a pipeline, and optionally its own corpus/questions/query
    pipeline. `corpus`/`questions` are `None` when the arm inherits the experiment's own, resolved
    absolute paths when the arm names its own — see `Experiment.corpus_for`/`questions_for`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    pipeline: str = Field(min_length=1)
    query_pipeline: str | None = None
    corpus: Path | None = None
    questions: Path | None = None


class Experiment(BaseModel):
    """An experiment, read from a document — see the module docstring. `digest` is a sha256 over
    the document's own bytes, computed by `load_experiment`, never over this resolved model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    digest: str = Field(min_length=1)
    questions: Path
    corpus: Path
    manifest: Path | None = None
    repeats: int = Field(ge=2)
    top_k: int = Field(ge=1)
    metrics: tuple[str, ...] = Field(min_length=1)
    minimum_detectable_effect: float = Field(gt=0)
    arms: tuple[ExperimentArm, ...]

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

    def corpus_for(self, arm: ExperimentArm) -> Path:
        """`arm`'s own corpus, or the experiment's, when the arm names none."""
        return arm.corpus if arm.corpus is not None else self.corpus

    def questions_for(self, arm: ExperimentArm) -> Path:
        """`arm`'s own question set, or the experiment's, when the arm names none."""
        return arm.questions if arm.questions is not None else self.questions


def _resolve(raw: object, *, root: Path) -> Path:
    return (root / str(raw)).resolve()


def _resolve_optional(raw: object, *, root: Path) -> Path | None:
    return None if raw is None else _resolve(raw, root=root)


def _refused_from(exc: ValidationError, path: Path) -> ExperimentDocumentError:
    """`exc`, narrowed to `ExperimentDocumentError`'s own field-naming shape — the first error
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
        corpus=_resolve_optional(entry.get("corpus"), root=root),
        questions=_resolve_optional(entry.get("questions"), root=root),
    )


def load_experiment(path: Path) -> Experiment:
    """Read `path` as an experiment document — see the module docstring for what each part
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
    if not isinstance(schema, int) or schema < 1 or schema > EXPERIMENT_SCHEMA_VERSION:
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

    try:
        arms = tuple(_build_arm(entry, root=root, path=path) for entry in arm_entries)
        return Experiment(
            name=str(experiment_table.get("name", "")),
            digest=digest,
            questions=_resolve(experiment_table.get("questions", ""), root=root),
            corpus=_resolve(experiment_table.get("corpus", ""), root=root),
            manifest=_resolve_optional(experiment_table.get("manifest"), root=root),
            repeats=experiment_table.get("repeats"),
            top_k=experiment_table.get("top_k"),
            metrics=tuple(experiment_table.get("metrics", ())),
            minimum_detectable_effect=experiment_table.get("minimum_detectable_effect"),
            arms=arms,
        )
    except ValidationError as exc:
        raise _refused_from(exc, path) from exc


__all__ = [
    "EXPERIMENT_SCHEMA_VERSION",
    "Experiment",
    "ExperimentArm",
    "ExperimentDocumentError",
    "ExperimentSchemaError",
    "load_experiment",
]
