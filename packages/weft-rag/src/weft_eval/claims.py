"""A `Claim` — one rung's measured standing against a baseline — and the loader for its TOML file.

Tasks **44.30** and **44.34**. A claim is the unit `manual/evidence.md` §3 is made of and an
`evidence-policy` rule cites. It states a rung's `status` against a `baseline` on a `metric`, the
runtime-observable `regime` it holds in, the `population` it was measured on, and where the numbers
come from. **Every number a reader sees is derived, never typed**: `weft eval claims check`
recomputes the interval, `n` and cost from the records the claim's `source` names, so the file
carries only what a person must say — which comparison, which regime, and what they conclude.

The two halves of "where it holds" are separate tables on purpose. `regime` is feature predicates a
router can observe at run time (`corpus.fits_context`); `population` is what the evidence was
gathered on (`benchmark`, `language`) and is never routed on, since a rule keyed to one benchmark's
phrasing wins there and nowhere else. A population key in the regime is refused by name.

`basis = "records"` rests on committed run records; `basis = "ledger"` is evidence nobody can
recompute (a phase measured before records were kept), names the ledger entry it rests on, and is
rendered as not reproducible from committed records.
"""

import re
import tomllib
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from weft_eval.fingerprint import ClaimFingerprint
from weft_eval.verdict import ClaimStatus, EffectVerdict
from weft_kernel.errors import UnresolvedNameError, WeftError
from weft_retrieve.profile import DECLARED_FEATURES, is_declared_feature
from weft_retrieve.routing import Condition

CLAIM_SCHEMA_VERSION: Final[int] = 2

#: The verdicts an automatic router may act on. `positive-below-margin` is a real effect the
#: experiment pre-registered as too small to be worth its cost, so it is not among them.
ROUTING_ADOPTION_VERDICTS: Final[frozenset[EffectVerdict]] = frozenset({EffectVerdict.WORTHWHILE})

_CLAIM_TABLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "id",
        "rung",
        "baseline",
        "arm",
        "baseline_arm",
        "metric",
        "status",
        "verdict",
        "basis",
        "margin",
        "ledger",
        "regime",
        "population",
        "source",
        "fingerprint",
        "untested",
    }
)
_REGIME_KEYS: Final[frozenset[str]] = frozenset({"when"})

#: The `corpus.*` features that say whether the corpus is whole, rather than describe it.
BASE_COMPLETE_FEATURE: Final[str] = "corpus.base_complete"
_COMPLETENESS_FEATURES: Final[frozenset[str]] = frozenset(
    {BASE_COMPLETE_FEATURE, "corpus.sources_pending", "corpus.sources_failed"}
)
_UNTESTED_KEYS: Final[frozenset[str]] = frozenset({"regimes"})


class ClaimDocumentError(WeftError):
    """A claim file could not be read as stated; the message names the file and the field."""


class UnknownClaimFeatureError(WeftError, UnresolvedNameError):
    """A claim's regime tests a feature the profilers do not declare."""

    def __init__(self, message: str, *, valid_options: tuple[str, ...]) -> None:
        super().__init__(message)
        self.valid_options = valid_options


class ClaimBasis(StrEnum):
    """What a claim rests on."""

    RECORDS = "records"
    LEDGER = "ledger"


class ClaimPopulation(BaseModel):
    """What the evidence was gathered on. Never routed on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark: str = Field(min_length=1)
    language: str = Field(min_length=1)
    question_sets: tuple[str, ...]


class ClaimSource(BaseModel):
    """The committed experiment and invocation a records claim is recomputed from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: str = Field(min_length=1)
    invocation: str = Field(min_length=1)
    #: Where the records live when they are not beside the experiment document.
    runs: str | None = None


class Claim(BaseModel):
    """One rung against one baseline on one metric — see the module docstring."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    rung: str = Field(min_length=1)
    baseline: str = Field(min_length=1)
    #: The experiment arms that ran `rung` and `baseline`, when naming the pipeline is ambiguous or
    #: the experiment's pipeline carries a different name from the rung it measures.
    arm: str | None = Field(default=None, min_length=1)
    baseline_arm: str | None = Field(default=None, min_length=1)
    metric: str = Field(min_length=1)
    status: ClaimStatus
    #: The reading beneath `status`: `helps` is both `worthwhile` and `positive-below-margin`, and
    #: only the first justifies routing. `None` for the statuses no interval gives.
    verdict: EffectVerdict | None = None
    basis: ClaimBasis
    #: The pre-registered effect size a difference must clear; read against the interval.
    margin: float | None = Field(default=None, gt=0)
    ledger: str | None = None
    regime: tuple[Condition, ...] = ()
    population: ClaimPopulation
    source: ClaimSource | None = None
    #: What the claim was validated against, pinned by `weft eval claims pin`; `None` until then.
    fingerprint: ClaimFingerprint | None = None
    untested: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _a_corpus_regime_states_whether_the_base_is_complete(self) -> "Claim":
        """A claim about corpus size or enrichment says which state of the corpus it holds in.

        A size or a readiness is a fact about a corpus the index has finished with; a Fast Track
        corpus still indexing can show the same number for a part of it. The profiler already
        states no extent until the base is complete, and this is the explicit half: the claim
        names the state it was measured in, so a rule carrying its regime inherits it.
        """
        about_corpus = any(
            condition.feature.startswith("corpus.")
            and condition.feature not in _COMPLETENESS_FEATURES
            for condition in self.regime
        )
        states_it = any(condition.feature == BASE_COMPLETE_FEATURE for condition in self.regime)
        if about_corpus and not states_it:
            raise ValueError(
                f"the regime tests the corpus but not whether its base is complete: add "
                f'{{ feature = "{BASE_COMPLETE_FEATURE}", op = "eq", value = true }} (or false, '
                f"for a claim measured on a corpus still indexing)"
            )
        return self

    @model_validator(mode="after")
    def _the_verdict_is_the_one_the_status_reads_from(self) -> "Claim":
        if self.status in {ClaimStatus.WRONG_QUESTIONS, ClaimStatus.NEVER}:
            if self.verdict is not None:
                raise ValueError(
                    f"status '{self.status}' is not read from an interval, so it carries no "
                    f"'verdict'; remove it"
                )
            return self
        readings = sorted(v.value for v in EffectVerdict if v.status is self.status)
        if self.verdict is None:
            raise ValueError(
                f"status '{self.status}' hides which verdict it stands for; state 'verdict' as one "
                f"of: {', '.join(readings)}"
            )
        if self.verdict.status is not self.status:
            raise ValueError(
                f"verdict '{self.verdict}' reads as status '{self.verdict.status}', not "
                f"'{self.status}'; state one of: {', '.join(readings)}"
            )
        return self

    @property
    def adoptable_for_routing(self) -> bool:
        """Whether an automatic router may cite this claim.

        A verdict in `ROUTING_ADOPTION_VERDICTS`, on committed records: a ledger claim cannot be
        recomputed, so nothing could notice it going stale.
        """
        return self.verdict in ROUTING_ADOPTION_VERDICTS and self.basis is ClaimBasis.RECORDS

    @model_validator(mode="after")
    def _basis_decides_what_it_must_name(self) -> "Claim":
        if self.basis is ClaimBasis.RECORDS:
            if self.source is None:
                raise ValueError(
                    "a records claim names the committed records it rests on: add [claim.source]"
                )
            if self.ledger is not None:
                raise ValueError(
                    "a records claim carries no 'ledger' entry; that is for basis = \"ledger\""
                )
        else:
            if self.source is not None:
                raise ValueError("a ledger claim has no records to name: remove [claim.source]")
            if not self.ledger:
                raise ValueError("a ledger claim names the ledger entry it rests on: add 'ledger'")
        return self


def _refused_from(exc: ValidationError, path: Path) -> ClaimDocumentError:
    first = exc.errors()[0]
    field = ".".join(str(part) for part in first["loc"]) or "(the document)"
    return ClaimDocumentError(f"{path.name}: {field}: {first['msg']}")


def _table(raw: object, *, name: str, path: Path, valid: frozenset[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ClaimDocumentError(f"{path.name}: [{name}] must be a table.")
    table = cast("dict[str, Any]", raw)
    unknown = sorted(set(table) - valid)
    if unknown:
        extra = ""
        if name == "claim.regime":
            extra = (
                f" '{unknown[0]}' is not runtime-observable; what a claim was measured on goes "
                f"in [claim.population], which a rule never tests."
            )
        raise ClaimDocumentError(
            f"{path.name}: [{name}] names an unknown key '{unknown[0]}'. "
            f"Valid keys: {', '.join(sorted(valid))}.{extra}"
        )
    return table


def _read_schema(table: dict[str, Any], path: Path) -> None:
    schema = table.get("schema")
    if schema is None:
        raise ClaimDocumentError(f"{path.name}: [claim] states no 'schema'.")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema < 1:
        raise ClaimDocumentError(f"{path.name}: 'schema' must be a positive integer.")
    if schema < CLAIM_SCHEMA_VERSION:
        raise ClaimDocumentError(
            f"{path.name}: declares schema {schema}, which states no 'verdict'; add the verdict "
            f"beneath 'status' (`weft eval claims check` prints each one) and set schema = "
            f"{CLAIM_SCHEMA_VERSION}."
        )
    if schema > CLAIM_SCHEMA_VERSION:
        raise ClaimDocumentError(
            f"{path.name}: declares schema {schema}; this weft-rag reads up to "
            f"{CLAIM_SCHEMA_VERSION} — upgrade weft-rag."
        )


def load_claim(path: Path) -> Claim:
    """Read one claim file, refusing anything it does not state plainly."""
    if not path.is_file():
        raise ClaimDocumentError(f"no claim document at {path}.")
    try:
        document = tomllib.loads(path.read_bytes().decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise ClaimDocumentError(f"{path.name}: not valid TOML: {exc}") from exc
    stray = sorted(set(document) - {"claim"})
    if stray or "claim" not in document:
        raise ClaimDocumentError(
            f"{path.name}: the only top-level table is [claim]; found {stray or 'none'}."
        )
    table = _table(document["claim"], name="claim", path=path, valid=_CLAIM_TABLE_KEYS)
    _read_schema(table, path)
    regime = _table(table.get("regime", {}), name="claim.regime", path=path, valid=_REGIME_KEYS)
    untested = _table(
        table.get("untested", {}), name="claim.untested", path=path, valid=_UNTESTED_KEYS
    )
    fields = {
        key: value for key, value in table.items() if key not in {"schema", "regime", "untested"}
    }
    try:
        claim = Claim.model_validate(
            {**fields, "regime": regime.get("when", []), "untested": untested.get("regimes", [])}
        )
    except ValidationError as exc:
        raise _refused_from(exc, path) from exc
    if path.stem != claim.id:
        raise ClaimDocumentError(
            f"{path.name}: the file must be named '{claim.id}.toml', after its id."
        )
    for condition in claim.regime:
        if not is_declared_feature(condition.feature):
            options = (
                *sorted(DECLARED_FEATURES),
                "corpus.layer.<name>.ready",
                "corpus.fits_context.<role>",
            )
            raise UnknownClaimFeatureError(
                f"{path.name}: the regime tests '{condition.feature}', which neither profiler "
                f"declares. Valid features: {', '.join(options)}.",
                valid_options=options,
            )
    return claim


_TABLE_HEADER_RE: Final[re.Pattern[str]] = re.compile(r"^\[")
_PIN_HEADER: Final[str] = "[claim.fingerprint]"


def _fingerprint_block(fingerprint: ClaimFingerprint) -> str:
    fields = fingerprint.model_dump(exclude_none=True)
    return (
        "\n".join([_PIN_HEADER, *(f'{name} = "{value}"' for name, value in fields.items())]) + "\n"
    )


def pin_claim(path: Path, fingerprint: ClaimFingerprint) -> None:
    """Write `fingerprint` into the claim file at `path`, replacing any pin it already holds.

    Text surgery on the one table, so a person's comments and the order of everything else survive
    and the diff is the pin and nothing more. `fingerprint` carries only digests and a version, so
    no value needs quoting.
    """
    kept: list[str] = []
    inside = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == _PIN_HEADER:
            inside = True
            continue
        if inside and _TABLE_HEADER_RE.match(line):
            inside = False
        if not inside:
            kept.append(line)
    body = "\n".join(kept).rstrip("\n")
    path.write_text(f"{body}\n\n{_fingerprint_block(fingerprint)}", encoding="utf-8")


def shipped_claims_dir() -> Path:
    """The claim documents this install carries: the wheel's copy, else the checkout's own.

    `hatch_build.py` copies `eval/claims/*.toml` into `weft_eval/shipped_claims/` when it builds, so
    an installed wheel holds them; a source checkout (editable, or running the tests) has no such
    copy and reads `eval/claims/` at the repository root. Neither existing is refused by name, since
    a router that cites evidence cannot be held to claims that are not there.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "shipped_claims", here.parents[3] / "eval" / "claims"):
        if candidate.is_dir():
            return candidate
    raise ClaimDocumentError(
        "this install carries no evidence claim documents: expected weft_eval/shipped_claims/ in a "
        "built wheel or eval/claims/ in a source checkout."
    )


def load_claims(directory: Path) -> tuple[Claim, ...]:
    """Every `*.toml` claim in `directory`, in id order; two files sharing an id are refused."""
    if not directory.is_dir():
        raise ClaimDocumentError(f"no claims directory at {directory}.")
    claims = sorted((load_claim(path) for path in directory.glob("*.toml")), key=lambda c: c.id)
    return tuple(claims)


__all__ = [
    "BASE_COMPLETE_FEATURE",
    "CLAIM_SCHEMA_VERSION",
    "ROUTING_ADOPTION_VERDICTS",
    "Claim",
    "ClaimBasis",
    "ClaimDocumentError",
    "ClaimPopulation",
    "ClaimSource",
    "UnknownClaimFeatureError",
    "load_claim",
    "load_claims",
    "pin_claim",
    "shipped_claims_dir",
]
