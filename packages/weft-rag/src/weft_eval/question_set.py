"""Prerequisite **V2** (`docs/09-release.md` §4.3) — the question set, and what may be believed.

V2 wants *"questions with relevance judgements for retrieval and reference answers for
generation; the provenance of each answer recorded (who wrote it, from which passage); and
unanswerable questions included"*, and it states its own failure condition: *"ground truth is
missing for any question and the harness scores it anyway."* This module — since repair
**R22.4a** part of the installed `weft-rag` wheel — is the schema and the reader of that set;
`eval/check_questions.py` keeps the quote-verification checks that need the corpus on disk, and
every rule below exists because the set can be wrong in a way nobody notices.

**Self-verification is not evidence, and that is measured rather than assumed.** These questions
were written in two rounds by agents that had read the document they cite, each verifying its own
quotes; an independent mechanical re-check still rejected 4 of 287 quotes as appearing nowhere in
the file they named — one of them attributing a table from one paper to another. So the check runs
in the gate, over the corpus that is actually on disk, and it is the *only* reason to believe a
quote. `tests/docs/test_question_set.py` drives it, through `eval/check_questions.py`'s
`quote_coverage`/`unmatched_quotes`/`misplaced_quotes` — this module holds no `main()` — see the
bottom of this docstring for why.

**A judgement is pinned to `(document, quote)`, never to a node id.** A `NodeId` is a content
digest over the chunker's output, so a judgement pinned to one is invalidated by any chunking
change — the failure mode that pushes an evaluator toward a paper-level fallback and inflates
precision toward 1.0 (`09` §4.2). A literal span survives re-chunking and resolves, at scoring
time, to whatever units the pipeline under test actually retrieved.

**The quote check is meant to be able to fail.** `weft-pdf` ships two backends that produce
visibly different text from the same page, so a quote taken from one may stop matching under the
other, and a re-rendered Wikipedia revision moves the Polish spans. That failure is information:
it says this ground truth no longer describes what the pipeline reads, and a tolerant match —
normalised whitespace, fuzzy ratio — would hide exactly the drift the check exists to surface.
Five Polish quotes and five page numbers were already stale when this module's predecessor was
written, against a corpus repaired one commit earlier, and nothing but an exact match would have
said so.

**A tier is a fact about a document, so a question never states one.** Which questions a stranger
can reproduce follows from the tiers of the documents they name — `reproducible_questions` derives
it — and the file a question lives in is the round it was written in, nothing more. An earlier
draft carried `tier` on the question itself and it disagreed with the manifest for 24 of the 136,
which is what a second copy of someone else's fact does.

**This module is now the one question model — task 38.10.** `Question` used to describe only the
136 hand-written questions, every field present. It now also holds an *imported* set that cannot
supply some of them (a legacy JSON `--questions` list was converted into it until `weft-rag`
3.0.0, task 43.38). A
missing field is legal only when the file says, once, which fields it cannot supply and why
(`absent`/`absent_reason`); a field that is merely missing and unexplained is refused exactly as
it always was, naming the field.

**The question file is a persisted format now, and gets a version marker of its own** — a surface
`S5`'s six (the `ext` map, the store's table, the filter AST, pipeline documents, `RunRecord`,
`weft.toml`) did not name, as `S11`'s blob root was not. A file carrying no `[question_set]` table
reads exactly as it always has — schema 1, every field required, no axes. `schema = 2` opts a file
into stated absences and per-file axes. Anything newer is refused, upgrade-or-refuse like every
other surface `S5` already binds: the message names the file, the version it declares, and the
version this `weft-rag` supports.

**There is no `main()` here, and that is forced rather than an omission.** Verifying a quote
means reading the text an `Extractor` produces, every contract method is `async def` (G6), and
`asyncio.run` may appear exactly once in the whole tree (fitness function 7(a), asserted by
path). A second bridge here to make a CLI convenient is precisely what that check exists to
refuse. So the async half lives in the gate test, which is also how the quote checks are run by
hand: `uv run pytest tests/docs/test_question_set.py`.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from weft_eval.contract import QueryModality
from weft_kernel.errors import WeftError

#: The version marker a question file's own `[question_set]` table names. No table at all is
#: schema 1 — today's rules exactly, unmarked because nothing needed a marker until this task.
QUESTION_SET_SCHEMA_VERSION: Final[int] = 2

_QUESTION_SET_TABLE_KEYS: Final[frozenset[str]] = frozenset(
    {"schema", "absent", "absent_reason", "axes"}
)


class QuestionSetError(WeftError):
    """A question file cannot be read or a question breaks its own invariant.

    A `WeftError`, since R22.4a: this module ships in the installed `weft-rag` wheel and any
    caller holding it — not only the hand-run harness — can reach a malformed question file, so
    the refusal is one a CLI can render like any other engine failure.
    """


class QuestionSetSchemaError(QuestionSetError):
    """A question file's own `[question_set] schema` is newer than this `weft-rag` reads.

    Upgrade-or-refuse, `S5`'s own posture: silence is refusal, never a best-effort parse of a
    table shape this version has never seen.
    """


class Kind(StrEnum):
    """What a question asks for — the axis a baseline slices its results along.

    `UNANSWERABLE` is the member V2 names outright: *"a RAG engine that cannot say 'not in this
    corpus' is untested for its most damaging failure."* It is also the one member with a
    structural consequence, checked below rather than trusted — such a question has no relevant
    document and no quote, because there is nothing in the corpus to point at.
    """

    DEFINITIONAL = "definitional"
    METHODOLOGICAL = "methodological"
    QUANTITATIVE = "quantitative"
    COMPARATIVE = "comparative"
    LIMITATION = "limitation"
    CROSS_DOCUMENT = "cross-document"
    UNANSWERABLE = "unanswerable"


class Difficulty(StrEnum):
    """How much of the document a question makes a retriever reach for.

    The author's own estimate, and recorded as one: nothing here checks it, and it is carried
    because a baseline that scores 0.9 on `EASY` and 0.3 on `HARD` has said something a single
    mean cannot.
    """

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionField(StrEnum):
    """A field a question may state absent, rather than silently default — task 38.10.

    Values equal the TOML keys a `[question_set]` table's `absent` list names, and the keys a
    question entry is refused for supplying directly (`absent`/`absent_reason` belong to the
    file, never to one question).
    """

    KIND = "kind"
    DIFFICULTY = "difficulty"
    QUOTE = "quote"
    REFERENCE_ANSWER = "reference_answer"
    NOTES = "notes"


#: The order these are checked in matters: a question missing more than one of them is refused
#: naming the first, and `kind` is checked first because a caller reading "kind" in the message
#: should never have to wonder whether a later field was silently skipped.
_STATABLE_SCALAR_FIELDS: Final[tuple[QuestionField, ...]] = (
    QuestionField.KIND,
    QuestionField.DIFFICULTY,
    QuestionField.REFERENCE_ANSWER,
    QuestionField.NOTES,
)


class Quote(BaseModel):
    """One literal span of a document's extracted text, and where in that document it is.

    `page` is `0` for a document that has no pages — a Wikipedia article is one stream of text and
    inventing a page for it would be a number nothing could check. For a PDF it is 1-based and
    verified against the extractor's own page boundaries, so it is a checked fact rather than an
    annotation, in the shape `corpus/manifest.toml` already uses for `math_blocks_dropped`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document: str = Field(min_length=1)
    page: int = Field(ge=0)
    text: str = Field(min_length=1)

    @field_validator("text", mode="after")
    @classmethod
    def _without_toml_s_own_newlines(cls, text: str) -> str:
        """Drop the newlines TOML's multi-line form adds, and nothing else.

        A `\"\"\"…\"\"\"` value written over several lines carries a trailing newline that belongs
        to the closing delimiter and not to the passage. Leading and trailing *spaces* are left
        exactly as authored: a rendering that lost one is the drift this whole module exists to
        catch, and a `.strip()` here would swallow it.
        """
        return text.strip("\n")


class Question(BaseModel):
    """The unit a question set is scored in, checked as it loads so a bad entry names itself.

    One question, its reference answer, and the spans that support it — or a stated reason it
    carries none of these.

    Every per-question invariant V2 implies is refused here rather than asserted somewhere else,
    so a malformed question fails at the moment it is read and names itself while doing it. The
    set-level properties — ids unique across files, documents known to the manifest, the corpus
    covered — need more than one question to state and live in `tests/docs/test_question_set.py`.

    `kind`, `difficulty`, `reference_answer`, `notes` and `quote` may each be missing, but only
    when that field is in `absent`, for a reason in `absent_reason` — a field that is merely
    missing is refused, naming itself, exactly as it always was.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    #: BCP-47, matching `corpus/manifest.toml`'s `language`. A fact about the ask.
    language: str = Field(min_length=1)
    #: What kind of query produced this question — task 9.12's own axis, defaulted to `TEXT` so
    #: every question written before that task keeps loading unchanged.
    modality: QueryModality = QueryModality.TEXT
    kind: Kind | None = None
    difficulty: Difficulty | None = None
    #: The documents an answer must be drawn from — the retrieval judgement. Empty exactly when
    #: the question is unanswerable, or (`kind` absent) when it names nothing to retrieve.
    relevant_documents: tuple[str, ...] = ()
    reference_answer: str | None = Field(default=None, min_length=1)
    #: V2's *"the provenance of each answer recorded (who wrote it, from which passage)"*. Prose
    #: rather than a sub-table because it carries the reasoning as well as the attribution — what
    #: was searched for and not found is most of what makes an unanswerable question believable.
    notes: str | None = Field(default=None, min_length=1)
    quote: tuple[Quote, ...] = ()
    #: Which of the fields above this question cannot supply — stated, never inferred from
    #: absence alone, so a field missing by accident is still refused.
    absent: frozenset[QuestionField] = frozenset()
    #: Why `absent` is non-empty. Required whenever `absent` is, so an importer's silence is
    #: never mistaken for a fact this module checked.
    absent_reason: str | None = None
    #: Free-form facts a question carries in place of a field it cannot supply — `axes["kind"]`
    #: for a question whose source labels a kind this module does not enumerate, for instance.
    #: A file's `[question_set] axes` declares which names are legal; see `load_questions`.
    axes: Mapping[str, str] = Field(default_factory=dict)

    @field_serializer("absent")
    def _serialise_absent(self, value: frozenset[QuestionField]) -> list[str]:
        """Sorted, so `question_set_digest` never depends on a frozenset's iteration order."""
        return sorted(member.value for member in value)

    @property
    def answerable(self) -> bool:
        """Whether the corpus contains an answer.

        Derived from `kind` when it is stated, so no field can disagree with it; derived from
        `relevant_documents` when `kind` is absent, because that is the only fact left that
        could say so — a question naming a document to retrieve is a claim the corpus answers it.
        """
        if self.kind is not None:
            return self.kind is not Kind.UNANSWERABLE
        return bool(self.relevant_documents)

    def _is_stated_empty(self, field: QuestionField) -> bool:
        if field is QuestionField.QUOTE:
            return self.quote == ()
        return getattr(self, field.value) is None

    @model_validator(mode="after")
    def _absences_are_stated_and_honest(self) -> Question:
        """Every gap is a stated fact, and every stated fact is a real gap.

        Two directions, because each is a different lie: a field silently missing (never in
        `absent`) is scored as if it were data nobody wrote, and a field claimed absent that the
        question actually supplies hides real ground truth behind a fabricated excuse.
        """
        for field in _STATABLE_SCALAR_FIELDS:
            if self._is_stated_empty(field) and field not in self.absent:
                raise ValueError(
                    f"{self.id}: '{field.value}' is missing but not named in [question_set] "
                    f"absent — state it absent with a reason, or supply it"
                )
        for field in self.absent:
            if not self._is_stated_empty(field):
                raise ValueError(
                    f"{self.id}: '{field.value}' is stated absent but this question supplies it"
                )
        if self.absent and not (self.absent_reason and self.absent_reason.strip()):
            raise ValueError(
                f"{self.id}: fields are stated absent with no reason — [question_set] needs an "
                f"absent_reason"
            )
        if "kind" in self.axes and QuestionField.KIND not in self.absent:
            raise ValueError(
                f"{self.id}: axis 'kind' is refused while 'kind' is a field this question "
                f"carries — an axis named kind only stands in for the field when it is absent"
            )
        return self

    @model_validator(mode="after")
    def _ground_truth_agrees_with_the_stance(self) -> Question:
        """The failure V2 names: ground truth missing while the harness scores the question anyway.

        Both directions, because each is a different lie. An answerable question with no quote
        would be scored against nothing and count as a miss for every pipeline. An unanswerable
        one carrying a relevant document says the corpus answers it after all, and the stance
        metric — the one generation-side number that needs no judge — would then be measured
        against a question that is not what it claims to be.

        The quote-shaped checks are skipped when `quote` is stated absent — an imported set that
        never carried quotes has nothing to check them against — and the cross-document rule
        applies only once `kind` is stated, since it is a fact about `kind`'s own vocabulary.
        """
        stance = self.kind.value if self.kind is not None else "answerable"
        if self.answerable:
            self._answerable_ground_truth_is_present(stance)
        else:
            self._unanswerable_carries_no_ground_truth()
        if self.kind is not None:
            self._kind_matches_the_document_count(self.kind)
        return self

    def _answerable_ground_truth_is_present(self, stance: str) -> None:
        if not self.relevant_documents:
            raise ValueError(f"{self.id}: {stance} but names no relevant document")
        if QuestionField.QUOTE in self.absent:
            return
        if not self.quote:
            raise ValueError(f"{self.id}: {stance} but carries no supporting quote")
        quoted = {quote.document for quote in self.quote}
        stray = sorted(quoted - set(self.relevant_documents))
        if stray:
            raise ValueError(f"{self.id}: quotes a document it does not call relevant: {stray}")
        silent = sorted(set(self.relevant_documents) - quoted)
        if silent:
            raise ValueError(
                f"{self.id}: calls a document relevant but quotes nothing from it: {silent}"
            )

    def _unanswerable_carries_no_ground_truth(self) -> None:
        if self.relevant_documents:
            raise ValueError(
                f"{self.id}: unanswerable, yet names {list(self.relevant_documents)} as "
                f"relevant — an unanswerable question is one the corpus does not answer"
            )
        if self.quote:
            raise ValueError(
                f"{self.id}: unanswerable, yet carries {len(self.quote)} supporting quote(s)"
            )

    def _kind_matches_the_document_count(self, kind: Kind) -> None:
        multi = len(set(self.relevant_documents)) > 1
        if multi != (kind is Kind.CROSS_DOCUMENT):
            raise ValueError(
                f"{self.id}: kind is {kind.value} over "
                f"{len(set(self.relevant_documents))} document(s); "
                f"'{Kind.CROSS_DOCUMENT.value}' means more than one and nothing else means it"
            )


def _question_set_table(
    raw: dict[str, Any], *, path: Path
) -> tuple[frozenset[QuestionField], str | None, tuple[str, ...]]:
    """Read `[question_set]`, or the schema-1 defaults when the file carries none."""
    table: object = raw.get("question_set")
    if table is None:
        return frozenset(), None, ()
    if not isinstance(table, dict):
        raise QuestionSetError(f"{path.name}: [question_set] must be a table")
    table = cast("dict[str, Any]", table)

    unknown = set(table) - _QUESTION_SET_TABLE_KEYS
    if unknown:
        raise QuestionSetError(
            f"{path.name}: [question_set] carries unknown key(s) {sorted(unknown)}. "
            f"Valid keys: {', '.join(sorted(_QUESTION_SET_TABLE_KEYS))}"
        )
    if "schema" not in table:
        raise QuestionSetError(f"{path.name}: [question_set] names no 'schema'")
    schema = table["schema"]
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        raise QuestionSetError(
            f"{path.name}: [question_set] schema must be a positive integer, found {schema!r}"
        )
    if schema > QUESTION_SET_SCHEMA_VERSION:
        raise QuestionSetSchemaError(
            f"{path.name}: schema {schema} is newer than the {QUESTION_SET_SCHEMA_VERSION} this "
            f"weft-rag reads — upgrade weft-rag to read it"
        )

    try:
        absent = frozenset(QuestionField(value) for value in table.get("absent", ()))
    except ValueError as exc:
        raise QuestionSetError(
            f"{path.name}: [question_set] absent names an unknown field: {exc}. "
            f"Valid fields: {', '.join(field.value for field in QuestionField)}"
        ) from exc
    absent_reason = table.get("absent_reason")
    if absent_reason is not None and not isinstance(absent_reason, str):
        raise QuestionSetError(f"{path.name}: [question_set] absent_reason must be a string")
    declared_axes = tuple(table.get("axes", ()))
    return absent, absent_reason, declared_axes


def _read_toml_questions(path: Path) -> tuple[Question, ...]:
    """Every question `path` holds, reading its own `[question_set]` table first."""
    try:
        with path.open("rb") as handle:
            raw: dict[str, Any] = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise QuestionSetError(f"{path.name}: {exc}") from exc

    file_absent, file_absent_reason, declared_axes = _question_set_table(raw, path=path)
    declared_axes_set = set(declared_axes)

    questions: list[Question] = []
    for index, raw_entry in enumerate(raw.get("question", ())):
        entry: dict[str, Any] = dict(raw_entry)
        if "absent" in entry or "absent_reason" in entry:
            raise QuestionSetError(
                f"{path.name}, question {index}: 'absent'/'absent_reason' belong to "
                f"[question_set], not to a question entry"
            )
        entry_axes = entry.pop("axes", {})
        if set(entry_axes) != declared_axes_set:
            disagreeing = sorted(set(entry_axes) ^ declared_axes_set)
            identifier = entry.get("id", f"<question {index}>")
            raise QuestionSetError(
                f"{path.name}, question {index} ({identifier}): axes {disagreeing} disagree "
                f"with the file's declared axes {sorted(declared_axes_set)}"
            )
        try:
            questions.append(
                Question.model_validate(
                    {
                        **entry,
                        "absent": file_absent,
                        "absent_reason": file_absent_reason,
                        "axes": entry_axes,
                    }
                )
            )
        except ValueError as exc:
            message = f"{path.name}, question {index}: {exc}"
            raise QuestionSetError(message) from exc
    return tuple(questions)


def load_questions(directory: Path) -> tuple[Question, ...]:
    """Every question under `directory`, in file then declaration order.

    A parse or validation failure names the file it came from. `tomllib` reports a syntax error by
    byte offset and pydantic reports a field error by index, and neither says which of many files
    is meant — in a set of 136 questions that is most of the work still to do.
    """
    questions: list[Question] = []
    for path in sorted(directory.glob("*.toml")):
        questions.extend(_read_toml_questions(path))
    return tuple(questions)


class QuestionSetFormat(StrEnum):
    """Which shape `read_question_set` found on disk.

    Carried rather than inferred a second time from the path, so a caller can report it without
    re-deriving it from the suffix.
    """

    TOML = "toml"


class QuestionSet(BaseModel):
    """A question set as read off disk — its questions, the shape they came from, and its digest.

    `format` is the shape it was read from; TOML is the only one since task 43.38 removed the
    JSON reader, and the field stays because `weft eval run --json` reports it.
    """

    model_config = ConfigDict(frozen=True)

    questions: tuple[Question, ...]
    format: QuestionSetFormat

    @property
    def digest(self) -> str:
        """`question_set_digest` over `questions` — derived, so no stored copy can disagree."""
        return question_set_digest(self.questions)


def question_set_digest(questions: Iterable[Question]) -> str:
    """A sha256 identifying the question set `questions` is, independent of file order.

    **Canonical, and nothing positional.** Each question is serialised as its own JSON object
    with sorted keys, the per-question strings are sorted, and the digest is taken over the
    join — so a file re-ordered is the same question set and a file with one question changed
    is not.

    **The canonical form is derived from `Question`, never hand-listed.** Every field the model
    carries is in it, so a version that learns a scoring-relevant field produces a different
    digest — which is correct rather than a gap: the same file scored by a version that reads a
    field the old one ignored *is* a different measurement.
    """
    canonical = sorted(
        json.dumps(question.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        for question in questions
    )
    return hashlib.sha256("\n".join(canonical).encode("utf-8")).hexdigest()


def read_question_set(path: Path) -> QuestionSet:
    """A question set from `path` — a directory or one `.toml` file.

    A directory reads exactly as `load_questions` always has. A lone `.toml` file is the same
    reader over one file, so a set that happens to live in one file digests identically to the
    same content spread over several. Anything else — a missing path, an unrecognised suffix,
    and the JSON list read until `weft-rag` 3.0.0 (task 43.38) — is refused naming the path.
    """
    if path.is_dir():
        questions = load_questions(path)
        return QuestionSet(
            questions=questions,
            format=QuestionSetFormat.TOML,
        )
    if not path.exists():
        raise QuestionSetError(f"{path.name}: no such file or directory")
    if path.suffix == ".toml":
        questions = _read_toml_questions(path)
        return QuestionSet(
            questions=questions,
            format=QuestionSetFormat.TOML,
        )
    raise QuestionSetError(
        f"{path.name}: unsupported question file suffix {path.suffix!r}. "
        "Valid: a directory, or a file ending .toml (a .json list was read until weft-rag 3.0.0)"
    )


def read_question_sets(paths: Sequence[Path]) -> QuestionSet:
    """The union of every question set `paths` names, each file's questions in file order.

    Each path is read exactly as `read_question_set` reads one, and the sets are concatenated in
    the order `paths` names them. A question id appearing in two named files is refused, naming
    the id and both files — an experiment scoring the union silently on one copy of a shared id
    would score the other file's own question against nobody's ground truth. The digest is
    `question_set_digest` over the union, already order-independent by design, so one file named
    alone keeps the digest every existing record carries and reordering many files leaves it
    unchanged.
    """
    seen: dict[str, Path] = {}
    questions: list[Question] = []
    for path in paths:
        for question in read_question_set(path).questions:
            first_path = seen.get(question.id)
            if first_path is not None:
                raise QuestionSetError(
                    f"question id '{question.id}' is in both {first_path.name} and {path.name}"
                )
            seen[question.id] = path
            questions.append(question)
    return QuestionSet(questions=tuple(questions), format=QuestionSetFormat.TOML)


def reproducible_questions(
    questions: Iterable[Question], *, tiers: Mapping[str, str], reproducible: frozenset[str]
) -> tuple[Question, ...]:
    """The questions a stranger can score, given which corpus tiers they can obtain.

    **This is the subset a published baseline is measured on**, and the reason is Phase 6's exit:
    the release is reproduced by someone who is not us, and a question resting on a paper under
    publisher copyright is one they cannot obtain at any price. Measuring the published number
    over the whole set would make it a number only this machine can produce.

    Derived from the manifest's own tier labels rather than from anything written on a question,
    so adding a document to the operator tier moves the subset without anyone editing this file.
    Unanswerable questions name no document and are therefore always in — which is right, and
    worth saying: they are the subset's hardest members and the only ones that need no corpus at
    all to be judged.

    As of the commit that introduced this, 95 of 136 questions are reproducible. That number is
    stated as a measurement, not pinned as a constant: `tests/docs/test_question_set.py` asserts
    the properties that must hold whatever it becomes.
    """
    tier_of = dict(tiers)
    return tuple(
        question
        for question in questions
        if all(tier_of[document] in reproducible for document in question.relevant_documents)
    )
